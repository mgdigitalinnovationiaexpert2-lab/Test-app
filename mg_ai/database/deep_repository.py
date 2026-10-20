"""Durable task-scoped DEEP continuity with one conservative execution claim."""
import hashlib
import time
import uuid
from typing import Any

from mg_ai.common.errors import MGError
from mg_ai.database.gateway_repository import GatewayRepository

TERMINAL_RELEASE_STATES = {"NOT_DISPATCHED", "COMPLETED", "FAILED_DETERMINISTIC"}
UNCERTAIN_STATES = {"DISPATCHED", "EXECUTION_AMBIGUOUS"}
RECONCILIATION_OUTCOMES = {
    "CONFIRMED_NOT_EXECUTED", "CONFIRMED_FAILED", "CONFIRMED_COMPLETED", "UNRESOLVED"
}
DEEP_SETTLEMENT_SECONDS = 240
DEEP_CONTEXT_MAX_CHARS = 120_000
DEEP_CONTEXT_VERSION = "mg-deep-transcript-v1"


class DeepRepository(GatewayRepository):
    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS deep_control (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                enabled INTEGER NOT NULL, session_ready INTEGER NOT NULL);
            INSERT OR IGNORE INTO deep_control VALUES (1,0,0);
            CREATE TABLE IF NOT EXISTS deep_control_audit (
                id INTEGER PRIMARY KEY, action TEXT, actor TEXT, reason TEXT, updated REAL);
            CREATE TABLE IF NOT EXISTS deep_runs (
                execution_id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL,
                thread_id TEXT NOT NULL, body_hash TEXT NOT NULL, status TEXT NOT NULL,
                response_id TEXT, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS deep_claim (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), execution_id TEXT NOT NULL);
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(deep_runs)")}
        for name, kind in (("task_id", "TEXT"), ("attempt", "INTEGER"),
                           ("created", "REAL"), ("dispatched_at", "REAL"),
                           ("settle_after", "REAL"), ("reconciliation_outcome", "TEXT")):
            if name not in columns:
                self.db.execute(f"ALTER TABLE deep_runs ADD COLUMN {name} {kind}")
        self.db.executescript("""
            UPDATE deep_runs SET task_id=conversation_id WHERE task_id IS NULL;
            UPDATE deep_runs SET attempt=1 WHERE attempt IS NULL;
            UPDATE deep_runs SET created=updated WHERE created IS NULL;
            UPDATE deep_runs SET status='COMPLETED' WHERE status='SUCCESS';
            UPDATE deep_runs SET status='EXECUTION_AMBIGUOUS' WHERE status='AMBIGUOUS';
            CREATE TABLE IF NOT EXISTS deep_conversations (
                conversation_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                thread_id TEXT NOT NULL, previous_response_id TEXT,
                last_attempt INTEGER NOT NULL, status TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL,
                context_version TEXT NOT NULL DEFAULT 'mg-deep-transcript-v1');
            INSERT OR IGNORE INTO deep_conversations
                (conversation_id,task_id,thread_id,previous_response_id,last_attempt,status,created,updated)
                SELECT conversation_id,task_id,thread_id,response_id,attempt,status,created,updated
                FROM deep_runs;
            CREATE UNIQUE INDEX IF NOT EXISTS deep_task_conversation_attempt
                ON deep_runs(task_id,conversation_id,attempt);
            CREATE TABLE IF NOT EXISTS deep_reconciliation_audit (
                id INTEGER PRIMARY KEY, execution_id TEXT NOT NULL, outcome TEXT NOT NULL,
                actor TEXT NOT NULL, evidence TEXT NOT NULL, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS deep_turns (
                execution_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                conversation_id TEXT NOT NULL, attempt INTEGER NOT NULL,
                user_content TEXT NOT NULL, assistant_content TEXT,
                privacy_class TEXT NOT NULL CHECK(privacy_class='PUBLIC'),
                created REAL NOT NULL, completed REAL);
            CREATE UNIQUE INDEX IF NOT EXISTS deep_conversation_turn_order
                ON deep_turns(task_id,conversation_id,attempt);
            CREATE TABLE IF NOT EXISTS deep_dispatch_attempts (
                execution_id TEXT NOT NULL, internal_attempt INTEGER NOT NULL,
                mode TEXT NOT NULL, outcome TEXT NOT NULL,
                provider_dispatch_possible INTEGER NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL,
                PRIMARY KEY(execution_id,internal_attempt));
        """)
        conversation_columns = {
            row[1] for row in self.db.execute("PRAGMA table_info(deep_conversations)")
        }
        if "context_version" not in conversation_columns:
            self.db.execute("ALTER TABLE deep_conversations ADD COLUMN context_version TEXT")
        self.db.execute(
            "UPDATE deep_conversations SET context_version=? WHERE context_version IS NULL",
            (DEEP_CONTEXT_VERSION,),
        )
        self.db.execute(
            "UPDATE deep_runs SET dispatched_at=created,settle_after=updated+? "
            "WHERE status IN ('DISPATCHED','EXECUTION_AMBIGUOUS') AND settle_after IS NULL",
            (DEEP_SETTLEMENT_SECONDS,),
        )

    def control(self) -> dict[str, bool]:
        row = self.db.execute(
            "SELECT enabled,session_ready FROM deep_control WHERE singleton=1"
        ).fetchone()
        return {"enabled": bool(row[0]), "session_ready": bool(row[1])}

    def configure(self, action: str, actor: str, reason: str) -> None:
        changes = {"enable": ("enabled", 1), "disable": ("enabled", 0),
                   "session-ready": ("session_ready", 1),
                   "session-unavailable": ("session_ready", 0)}
        if action not in changes or not actor.strip() or not reason.strip():
            raise ValueError("explicit owner action, actor and reason required")
        column, value = changes[action]
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(f"UPDATE deep_control SET {column}=? WHERE singleton=1", (value,))
            self.db.execute(
                "INSERT INTO deep_control_audit(action,actor,reason,updated) VALUES (?,?,?,?)",
                (action, actor, reason, time.time()),
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def claim(self, execution_id: str, task_id: str, conversation_id: str,
              attempt: int, body: bytes, user_content: str = "") -> dict[str, Any]:
        now = time.time()
        body_hash = hashlib.sha256(body).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT body_hash,status FROM deep_runs WHERE execution_id=?", (execution_id,)
            ).fetchone()
            if existing:
                conflict = existing["body_hash"] != body_hash
                raise MGError("IDEMPOTENCY_CONFLICT" if conflict else "EXECUTION_ALREADY_RECORDED",
                              409, reconciliation=existing["status"] in UNCERTAIN_STATES)
            active = self.db.execute(
                "SELECT r.status FROM deep_claim c JOIN deep_runs r "
                "ON c.execution_id=r.execution_id"
            ).fetchone()
            if active:
                raise MGError("DEEP_BUSY", 409, reconciliation=active[0] in UNCERTAIN_STATES)
            if not self.control()["enabled"] or not self.provider_enabled("omniroute"):
                raise MGError("DEEP_DISABLED", 503)
            if not self.control()["session_ready"]:
                raise MGError("DEEP_SESSION_UNAVAILABLE", 503)
            conversation = self.db.execute(
                "SELECT * FROM deep_conversations WHERE conversation_id=?", (conversation_id,)
            ).fetchone()
            if conversation and conversation["task_id"] != task_id:
                raise MGError("CONVERSATION_TASK_CONFLICT", 409)
            if conversation and conversation["status"] == "RECONCILIATION_REQUIRED":
                raise MGError("DEEP_RECONCILIATION_REQUIRED", 409, reconciliation=True)
            expected_attempt = conversation["last_attempt"] + 1 if conversation else 1
            if attempt != expected_attempt:
                raise MGError("ATTEMPT_CONFLICT", 409)
            history = [dict(row) for row in self.db.execute(
                "SELECT t.execution_id,t.attempt,t.user_content,t.assistant_content "
                "FROM deep_turns t JOIN deep_runs r ON r.execution_id=t.execution_id "
                "WHERE t.task_id=? AND t.conversation_id=? AND r.status='COMPLETED' "
                "AND t.assistant_content IS NOT NULL ORDER BY t.attempt,t.execution_id",
                (task_id, conversation_id),
            )]
            completed_count = self.db.execute(
                "SELECT COUNT(*) FROM deep_runs WHERE task_id=? AND conversation_id=? "
                "AND status='COMPLETED'", (task_id, conversation_id),
            ).fetchone()[0]
            if completed_count != len(history):
                raise MGError("DEEP_TRANSCRIPT_INCOMPLETE", 409)
            context_chars = len(user_content) + sum(
                len(row["user_content"]) + len(row["assistant_content"]) for row in history
            )
            if context_chars > DEEP_CONTEXT_MAX_CHARS:
                raise MGError("DEEP_CONTEXT_LIMIT_EXCEEDED", 413)
            thread_id = conversation["thread_id"] if conversation else str(uuid.uuid4())
            previous_response_id = conversation["previous_response_id"] if conversation else None
            self.db.execute(
                "INSERT INTO deep_runs "
                "(execution_id,conversation_id,thread_id,body_hash,status,response_id,updated,"
                "task_id,attempt,created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (execution_id, conversation_id, thread_id, body_hash, "NOT_DISPATCHED", None,
                 now, task_id, attempt, now),
            )
            self.db.execute(
                "INSERT INTO deep_turns VALUES (?,?,?,?,?,?,?,?,?)",
                (execution_id, task_id, conversation_id, attempt, user_content, None,
                 "PUBLIC", now, None),
            )
            if conversation:
                self.db.execute(
                    "UPDATE deep_conversations SET last_attempt=?,status=?,updated=? "
                    "WHERE conversation_id=?",
                    (attempt, "NOT_DISPATCHED", now, conversation_id),
                )
            else:
                self.db.execute(
                    "INSERT INTO deep_conversations "
                    "(conversation_id,task_id,thread_id,previous_response_id,last_attempt,status,"
                    "created,updated,context_version) VALUES (?,?,?,?,?,?,?,?,?)",
                    (conversation_id, task_id, thread_id, None, attempt,
                     "NOT_DISPATCHED", now, now, DEEP_CONTEXT_VERSION),
                )
            self.db.execute("INSERT INTO deep_claim VALUES (1,?)", (execution_id,))
            self.db.execute("COMMIT")
            return {"thread_id": thread_id, "previous_response_id": previous_response_id,
                    "history": history, "context_version": DEEP_CONTEXT_VERSION,
                    "created": now}
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def mark(self, execution_id: str, status: str, response_id: str | None = None,
             assistant_content: str | None = None) -> None:
        allowed = TERMINAL_RELEASE_STATES | UNCERTAIN_STATES
        if status not in allowed:
            raise ValueError("invalid DEEP execution state")
        now = time.time()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            run = self.db.execute(
                "SELECT conversation_id FROM deep_runs WHERE execution_id=?", (execution_id,)
            ).fetchone()
            if not run:
                raise ValueError("unknown DEEP execution")
            if status == "COMPLETED" and (not response_id or not assistant_content):
                raise ValueError("completed DEEP execution requires response identity and answer")
            if status == "DISPATCHED":
                self.db.execute(
                    "UPDATE deep_runs SET status=?,response_id=?,updated=?,dispatched_at=?,"
                    "settle_after=? WHERE execution_id=?",
                    (status, response_id, now, now, now + DEEP_SETTLEMENT_SECONDS, execution_id),
                )
            else:
                self.db.execute(
                    "UPDATE deep_runs SET status=?,response_id=?,updated=? WHERE execution_id=?",
                    (status, response_id, now, execution_id),
                )
            if status == "COMPLETED":
                self.db.execute(
                    "UPDATE deep_turns SET assistant_content=?,completed=? WHERE execution_id=?",
                    (assistant_content, now, execution_id),
                )
                self.db.execute(
                    "UPDATE deep_conversations SET status=?,previous_response_id=?,updated=? "
                    "WHERE conversation_id=?",
                    (status, response_id, now, run["conversation_id"]),
                )
            else:
                self.db.execute(
                    "UPDATE deep_conversations SET status=?,updated=? WHERE conversation_id=?",
                    (status, now, run["conversation_id"]),
                )
            if status in TERMINAL_RELEASE_STATES:
                self.db.execute("DELETE FROM deep_claim WHERE execution_id=?", (execution_id,))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def start_dispatch_attempt(self, execution_id: str, mode: str) -> int:
        if mode not in {"FULL_TRANSCRIPT", "PREVIOUS_RESPONSE_ID"}:
            raise ValueError("invalid dispatch mode")
        now = time.time()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            run = self.db.execute(
                "SELECT status FROM deep_runs WHERE execution_id=?", (execution_id,)
            ).fetchone()
            if not run or run["status"] != "DISPATCHED":
                raise ValueError("execution must be dispatched")
            number = self.db.execute(
                "SELECT COALESCE(MAX(internal_attempt),0)+1 FROM deep_dispatch_attempts "
                "WHERE execution_id=?", (execution_id,),
            ).fetchone()[0]
            self.db.execute(
                "INSERT INTO deep_dispatch_attempts VALUES (?,?,?,?,?,?,?)",
                (execution_id, number, mode, "STARTED", 1, now, now),
            )
            self.db.execute("COMMIT")
            return int(number)
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def finish_dispatch_attempt(self, execution_id: str, internal_attempt: int,
                                outcome: str, provider_dispatch_possible: bool) -> None:
        self.db.execute(
            "UPDATE deep_dispatch_attempts SET outcome=?,provider_dispatch_possible=?,updated=? "
            "WHERE execution_id=? AND internal_attempt=?",
            (outcome, int(provider_dispatch_possible), time.time(), execution_id, internal_attempt),
        )

    def transcript(self, conversation_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute(
            "SELECT execution_id,task_id,conversation_id,attempt,user_content,assistant_content,"
            "privacy_class,created,completed FROM deep_turns WHERE conversation_id=? "
            "ORDER BY attempt,execution_id", (conversation_id,)
        )]

    def reconcile(self, execution_id: str, outcome: str, actor: str, evidence: str) -> None:
        if outcome not in RECONCILIATION_OUTCOMES or not actor.strip() or not evidence.strip():
            raise ValueError("valid outcome, owner actor and evidence required")
        now = time.time()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            run = self.db.execute(
                "SELECT * FROM deep_runs WHERE execution_id=?", (execution_id,)
            ).fetchone()
            if not run or run["status"] not in UNCERTAIN_STATES:
                raise MGError("EXECUTION_NOT_RECONCILABLE", 409)
            if outcome == "UNRESOLVED" and (run["settle_after"] is None
                                                or now < run["settle_after"]):
                raise MGError("RECONCILIATION_SETTLEMENT_PENDING", 409, reconciliation=True)
            turn = self.db.execute(
                "SELECT assistant_content FROM deep_turns WHERE execution_id=?", (execution_id,)
            ).fetchone()
            if outcome == "CONFIRMED_COMPLETED" and (
                    not run["response_id"] or not turn or not turn["assistant_content"]):
                raise MGError("CONFIRMED_COMPLETION_EVIDENCE_REQUIRED", 409,
                              reconciliation=True)

            if outcome == "CONFIRMED_COMPLETED":
                run_status, conversation_status = "COMPLETED", "COMPLETED"
                self.db.execute(
                    "UPDATE deep_conversations SET status=?,previous_response_id=?,updated=? "
                    "WHERE conversation_id=?",
                    (conversation_status, run["response_id"], now, run["conversation_id"]),
                )
            elif outcome == "UNRESOLVED":
                run_status, conversation_status = "EXECUTION_AMBIGUOUS", "RECONCILIATION_REQUIRED"
                self.db.execute(
                    "UPDATE deep_conversations SET status=?,updated=? WHERE conversation_id=?",
                    (conversation_status, now, run["conversation_id"]),
                )
            else:
                run_status, conversation_status = "FAILED_DETERMINISTIC", "FAILED_DETERMINISTIC"
                self.db.execute(
                    "UPDATE deep_conversations SET status=?,updated=? WHERE conversation_id=?",
                    (conversation_status, now, run["conversation_id"]),
                )
            self.db.execute(
                "UPDATE deep_runs SET status=?,reconciliation_outcome=?,updated=? "
                "WHERE execution_id=?",
                (run_status, outcome, now, execution_id),
            )
            self.db.execute("DELETE FROM deep_claim WHERE execution_id=?", (execution_id,))
            self.db.execute(
                "INSERT INTO deep_reconciliation_audit"
                "(execution_id,outcome,actor,evidence,updated) VALUES (?,?,?,?,?)",
                (execution_id, outcome, actor.strip(), evidence.strip(), now),
            )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def evidence(self, execution_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT execution_id,task_id,conversation_id,thread_id,attempt,status,response_id,"
            "created,updated,dispatched_at,settle_after,reconciliation_outcome "
            "FROM deep_runs WHERE execution_id=?", (execution_id,)
        ).fetchone()
        return dict(row) if row else {}
