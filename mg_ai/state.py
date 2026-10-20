import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mg_ai.errors import MGError
from mg_ai.capacity import Capacity


class State:
    """SQLite is the single-host admission and durable execution-result journal."""

    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS usage (
                client TEXT, window TEXT, count INTEGER NOT NULL,
                PRIMARY KEY(client, window));
            CREATE TABLE IF NOT EXISTS executions (
                client TEXT, key_hash TEXT, body_hash TEXT, status TEXT, request_id TEXT,
                updated REAL, result_json TEXT, error_code TEXT,
                PRIMARY KEY(client,key_hash));
            CREATE TABLE IF NOT EXISTS health (
                model TEXT PRIMARY KEY, status TEXT, cooldown REAL, failures INTEGER,
                last_success REAL, last_failure REAL, latency_ms REAL);
            CREATE TABLE IF NOT EXISTS provider_capacity (
                provider TEXT, account TEXT, observation TEXT NOT NULL,
                PRIMARY KEY(provider,account));
            CREATE TABLE IF NOT EXISTS provider_control (
                provider TEXT PRIMARY KEY, enabled INTEGER NOT NULL,
                actor TEXT NOT NULL, reason TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS provider_control_audit (
                id INTEGER PRIMARY KEY, provider TEXT NOT NULL, enabled INTEGER NOT NULL,
                actor TEXT NOT NULL, reason TEXT NOT NULL, updated REAL NOT NULL);
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(executions)")}
        if "result_json" not in columns:
            self.db.execute("ALTER TABLE executions ADD COLUMN result_json TEXT")
        if "error_code" not in columns:
            self.db.execute("ALTER TABLE executions ADD COLUMN error_code TEXT")

    def provider_enabled(self, provider: str) -> bool:
        row = self.db.execute("SELECT enabled FROM provider_control WHERE provider=?",
                              (provider,)).fetchone()
        return row is None or row[0] == 1

    def set_provider_enabled(self, provider: str, enabled: bool, actor: str, reason: str) -> None:
        if not actor.strip() or not reason.strip():
            raise ValueError("owner actor and reason required")
        values = (provider, int(enabled), actor, reason, time.time())
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute("INSERT OR REPLACE INTO provider_control VALUES (?,?,?,?,?)", values)
            self.db.execute("INSERT INTO provider_control_audit "
                            "(provider,enabled,actor,reason,updated) VALUES (?,?,?,?,?)", values)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def save_capacity(self, snapshot: Capacity) -> None:
        self.db.execute("INSERT INTO provider_capacity VALUES (?,?,?) ON CONFLICT(provider,account) "
                        "DO UPDATE SET observation=excluded.observation",
                        (snapshot.provider, snapshot.account, snapshot.model_dump_json()))

    def capacity(self, provider: str, account: str) -> Capacity | None:
        row = self.db.execute("SELECT observation FROM provider_capacity WHERE provider=? "
                              "AND account=?", (provider, account)).fetchone()
        return Capacity.model_validate(json.loads(row[0])) if row else None

    def admit(self, client: str, rpm: int, monthly: int | None, key: str | None,
              body: bytes, request_id: str, now: float | None = None) -> str | None:
        now = now if now is not None else time.time()
        digest = hashlib.sha256(key.encode()).hexdigest() if key else None
        body_hash = hashlib.sha256(body).hexdigest()
        windows = [(f"minute:{int(now // 60)}", rpm)]
        if monthly is not None:
            month = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m")
            windows.append((f"month:{month}", monthly))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if digest:
                row = self.db.execute("SELECT * FROM executions WHERE client=? AND key_hash=?",
                                      (client, digest)).fetchone()
                if row:
                    if row["body_hash"] != body_hash:
                        raise MGError("IDEMPOTENCY_CONFLICT", 409)
                    raise MGError("EXECUTION_ALREADY_RECORDED", 409,
                                  reconciliation=row["status"] in {"DISPATCHED", "AMBIGUOUS"})
            for window, limit in windows:
                row = self.db.execute("SELECT count FROM usage WHERE client=? AND window=?",
                                      (client, window)).fetchone()
                if row and row["count"] >= limit:
                    raise MGError("REQUEST_BUDGET_EXHAUSTED" if window.startswith("month")
                                  else "CLIENT_RATE_LIMITED", 429, retryable=True)
            for window, _ in windows:
                self.db.execute("INSERT INTO usage VALUES (?,?,1) ON CONFLICT(client,window) "
                                "DO UPDATE SET count=count+1", (client, window))
            if digest:
                self.db.execute(
                    "INSERT INTO executions "
                    "(client,key_hash,body_hash,status,request_id,updated,result_json,error_code) "
                    "VALUES (?,?,?,?,?,?,NULL,NULL)",
                    (client, digest, body_hash, "ADMITTED", request_id, now),
                )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return digest

    def check_duplicate(self, client: str, key: str, body: bytes) -> None:
        row = self.db.execute("SELECT * FROM executions WHERE client=? AND key_hash=?",
                              (client, hashlib.sha256(key.encode()).hexdigest())).fetchone()
        if row:
            if row["body_hash"] != hashlib.sha256(body).hexdigest():
                raise MGError("IDEMPOTENCY_CONFLICT", 409)
            raise MGError("EXECUTION_ALREADY_RECORDED", 409,
                          reconciliation=row["status"] in {"DISPATCHED", "AMBIGUOUS"})

    def execution(self, client: str, digest: str | None, status: str) -> None:
        if digest:
            self.db.execute("UPDATE executions SET status=?,updated=? WHERE client=? AND key_hash=?",
                            (status, time.time(), client, digest))

    def complete(self, client: str, digest: str | None, result: dict[str, Any]) -> None:
        if digest:
            self.db.execute(
                "UPDATE executions SET status='SUCCESS',result_json=?,error_code=NULL,updated=? "
                "WHERE client=? AND key_hash=?",
                (json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                 time.time(), client, digest),
            )

    def fail(self, client: str, digest: str | None, status: str, code: str) -> None:
        if digest:
            self.db.execute(
                "UPDATE executions SET status=?,error_code=?,updated=? "
                "WHERE client=? AND key_hash=?",
                (status, code, time.time(), client, digest),
            )

    def reconcile(self, client: str, key: str) -> dict[str, Any]:
        digest = hashlib.sha256(key.encode()).hexdigest()
        row = self.db.execute(
            "SELECT status,request_id,result_json,error_code,updated FROM executions "
            "WHERE client=? AND key_hash=?", (client, digest),
        ).fetchone()
        if not row:
            return {"status": "NOT_FOUND"}
        status = row["status"]
        base = {"request_id": row["request_id"], "updated_at": row["updated"]}
        if status == "SUCCESS" and row["result_json"]:
            return {**base, "status": "COMPLETED", "result": json.loads(row["result_json"])}
        if status in {"ADMITTED", "DISPATCHED"}:
            return {**base, "status": "PROCESSING"}
        if status in {"TERMINAL", "SAFE_FAILURE"}:
            return {**base, "status": "FAILED", "error_code": row["error_code"] or status}
        return {**base, "status": "RECONCILIATION_REQUIRED"}

    def health(self, model: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM health WHERE model=?", (model,)).fetchone()
        return dict(row) if row else {"status": "DEGRADED", "cooldown": 0, "failures": 0,
                                     "latency_ms": 0, "last_success": None, "last_failure": None}

    def record(self, model: str, outcome: str, latency: float, retry_after: float = 60) -> None:
        previous = self.health(model)
        now = time.time()
        success = outcome == "SUCCESS"
        failures = 0 if success else previous["failures"] + 1
        status = ("HEALTHY" if success else "RATE_LIMITED" if outcome == "RATE_LIMITED_SAFE"
                  else "UNAVAILABLE" if failures >= 3 else "DEGRADED")
        cooldown = 0 if success else now + min(max(retry_after, 1), 3600)
        self.db.execute("INSERT OR REPLACE INTO health VALUES (?,?,?,?,?,?,?)",
                        (model, status, cooldown, failures,
                         now if success else previous["last_success"],
                         previous["last_failure"] if success else now, latency))
