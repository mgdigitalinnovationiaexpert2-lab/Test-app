"""Fixed synthetic probes via a separate private LiteLLM deployment; never promotes models."""
import argparse
import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import ValidationError, validate

from mg_ai.config import Candidate, load_config
from mg_ai.discovery import GROQ_SOURCE, SOURCE, free_model
from mg_ai.errors import MGError
from mg_ai.providers import LiteLLMAdapter, Outcome, Result
from mg_ai.proxy_config import render
from mg_ai.state import State

CASES = Path("evals/live-cases.json")
THRESHOLDS = Path("evals/live-thresholds.json")
DATASET_MANIFEST = Path("evals/dataset-approval.json")


def approved_dataset() -> bytes:
    manifest = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
    data = CASES.read_bytes()
    if (manifest.get("dataset") != CASES.as_posix()
            or manifest.get("data_class") != "PUBLIC_SYNTHETIC"
            or not manifest.get("approved_by") or not manifest.get("approval_reason")
            or manifest.get("sha256") != hashlib.sha256(data).hexdigest()):
        raise ValueError("benchmark dataset is not approved")
    return data


def eligible(model: Candidate, catalog: dict[str, Any], now: float | None = None) -> bool:
    now = time.time() if now is None else now
    try:
        checked = datetime.fromisoformat(catalog["refreshed_at"])
        if checked.tzinfo is None or not 0 <= now - checked.timestamp() < 86400:
            return False
        row = next(r for r in catalog["candidates"] if r["model"] == model.model)
        common = (model.cost_class == "FREE" and not model.random_router
                  and model.api_base is None)
        if model.provider == "openrouter":
            return bool(common and catalog["source"] == SOURCE
                        and model.model.endswith(":free")
                        and model.credential_env == "OPENROUTER_API_KEY"
                        and free_model({"id": model.model, "pricing": row["pricing"]}))
        if model.provider == "groq":
            return bool(common and catalog["source"] == GROQ_SOURCE
                        and catalog.get("provider") == "groq"
                        and catalog.get("account_free_confirmed_by_owner") is True
                        and catalog.get("global_zdr_confirmed_by_owner") is True
                        and model.credential_env == "GROQ_API_KEY" and row.get("active") is True)
        return False
    except (KeyError, TypeError, ValueError, StopIteration):
        return False


def payload(case: dict[str, Any]) -> dict[str, Any]:
    prompt = case["prompt"]
    if case.get("long_context"):
        filler = "این جمله فقط متن ساختگی نامرتبط برای آزمون بازیابی است.\n" * 600
        prompt += "\nFIRST=173\n" + filler + "MIDDLE=482\n" + filler + "LAST=921"
    body: dict[str, Any] = {"messages": [{"role": "user", "content": prompt}],
                            "temperature": 0, "max_tokens": 512, "stream": False}
    if case.get("tool"):
        body["tools"] = [{"type": "function", "function": {"name": "propose_edit",
                         "description": "Synthetic proposal only; never executed",
                         "parameters": case["schema"]}}]
        body["tool_choice"] = {"type": "function", "function": {"name": "propose_edit"}}
    else:
        body["response_format"] = {"type": "json_schema", "json_schema": {
            "name": "synthetic_probe", "strict": True, "schema": case["schema"]}}
    return body


def score_case(case: dict[str, Any], result: Result) -> dict[str, float]:
    dimensions = {name: 0.0 for name in case["checks"]}
    dimensions.update(structured_output=0.0, reliability=float(result.outcome == Outcome.SUCCESS))
    if case.get("persian_field"):
        dimensions["persian_script"] = 0.0
    try:
        if result.outcome != Outcome.SUCCESS or result.response is None:
            return dimensions
        message = result.response["choices"][0]["message"]
        if case.get("tool"):
            calls = message.get("tool_calls", [])
            if len(calls) != 1 or calls[0]["function"]["name"] != "propose_edit":
                return dimensions
            data = json.loads(calls[0]["function"]["arguments"])
        else:
            data = json.loads(message["content"])
        validate(data, case["schema"])
        dimensions["structured_output"] = 1.0
        for dimension, fields in case["checks"].items():
            dimensions[dimension] = sum(data.get(k) == case["expected"][k] for k in fields) / len(fields)
        if case.get("persian_field"):
            text = data.get(case["persian_field"], "")
            dimensions["persian_script"] = float(bool(re.search(r"[\u0600-\u06ff]", text)))
        return dimensions
    except (ValueError, KeyError, TypeError, ValidationError, IndexError):
        return dimensions


def summarize(results: list[dict[str, Any]], thresholds: dict[str, dict[str, float]]) -> dict[str, Any]:
    routes: dict[str, Any] = {}
    for route, limits in thresholds.items():
        rows = [row for row in results if row["route"] == route]
        metrics = {dimension: min((r["scores"][dimension] for r in rows
                                  if dimension in r["scores"]), default=0.0) for dimension in limits}
        passes = bool(rows) and all(metrics[k] >= v for k, v in limits.items())
        routes[route] = {"metrics": metrics, "thresholds_pass": passes,
                         "status": "NOT_TESTED" if not rows else
                         "HUMAN_REVIEW_REQUIRED" if passes else "REJECTED",
                         "champion": None, "fallback": None}
    return routes


async def run(model: Candidate, catalog: dict[str, Any], adapter: LiteLLMAdapter,
              state: State, run_id: str, output: Path,
              routes: set[str] | None = None, *, approved_by: str = "",
              control_state: State | None = None) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id):
        raise ValueError("invalid run identity")
    selected = routes or {"life-study", "dev-code", "portal-workhorse"}
    if not selected <= {"life-study", "dev-code", "portal-workhorse"}:
        raise ValueError("unknown benchmark route")
    if not approved_by.strip():
        raise ValueError("explicit manual campaign approval required")
    dataset = approved_dataset()
    controls = control_state if control_state is not None else state
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8"):
        pass
    report: dict[str, Any] = {"run_id": run_id, "model": model.model, "candidate": model.id,
        "provider": model.provider, "paid_allowed": False, "automatic_promotion": False,
        "mode": "live_free", "dataset_sha256": hashlib.sha256(dataset).hexdigest(),
        "approved_by": approved_by,
        "privacy": "PUBLIC_SYNTHETIC_ONLY", "results": [], "status": "BLOCKED",
        "selected_routes": sorted(selected),
        "human_review_required": True, "verified_capabilities": [],
        "note": "Script/fixture correctness is not Persian fluency or general coding certification"}

    def persist() -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)

    if not controls.provider_enabled(model.provider):
        report["blocker"] = "PROVIDER_DISABLED"
        persist()
        return report
    if not eligible(model, catalog) or not os.getenv(model.credential_env):
        report["blocker"] = "FRESH_FREE_CATALOG_AND_OPENROUTER_API_KEY_REQUIRED"
        persist()
        return report
    cases = [case for case in json.loads(dataset)
             if case["route"] in selected]
    client = "benchmark:" + model.id
    run_body = json.dumps({"model": model.model, "dataset": report["dataset_sha256"],
                           "routes": sorted(selected)}).encode()
    try:
        state.admit(client, 100, None, run_id, run_body, run_id)
    except MGError:
        raise ValueError("run identity already recorded; inspect journal, never blindly repeat") from None
    digest = hashlib.sha256(run_id.encode()).hexdigest()
    report["status"] = "RUNNING"
    persist()
    for case in cases:
        body = payload(case)
        if not controls.provider_enabled(model.provider):
            result = Result(Outcome.FAILED_TERMINAL, category="PROVIDER_DISABLED")
        elif len(json.dumps(body, ensure_ascii=False).encode("utf-8")) + 512 > model.context_limit:
            result = Result(Outcome.FAILED_TERMINAL, category="CONTEXT_BOUND_EXCEEDS_CANDIDATE")
        else:
            # Persist dispatch before awaiting I/O; interrupted runs cannot silently resume/replay.
            state.execution(client, digest, "DISPATCHED")
            persist()
            result = await adapter.execute(model, body)
        row = {"fixture": case["id"], "route": case["route"], "request_id": str(uuid.uuid4()),
               "timestamp": datetime.now().astimezone().isoformat(), "candidate_sequence": [model.id],
               "fallback_count": 0, "outcome": str(result.outcome), "category": result.category,
               "latency_ms": result.latency_ms, "scores": score_case(case, result),
               "tokens": result.response.get("usage", {}) if result.response else {}}
        report["results"].append(row)
        persist()
        if result.outcome != Outcome.SUCCESS:
            state.execution(client, digest, "AMBIGUOUS" if result.outcome == Outcome.EXECUTION_AMBIGUOUS
                            else "FAILED")
            report["status"] = "RECONCILIATION_REQUIRED" if result.outcome == Outcome.EXECUTION_AMBIGUOUS else "FAILED"
            break
    else:
        state.execution(client, digest, "COMPLETED")
        report["status"] = "COMPLETED"
    report["routes"] = summarize(report["results"], json.loads(THRESHOLDS.read_text()))
    report["capability_probes"] = {capability: {
        "fixtures": [c["id"] for c in cases if capability in c["capabilities"]],
        "passed": all(any(r["fixture"] == c["id"] and all(v == 1 for v in r["scores"].values())
                          for r in report["results"]) for c in cases if capability in c["capabilities"]),
        "human_review_required": capability in {"PERSIAN", "CODING", "REASONING"},
    } for capability in {cap for c in cases for cap in c["capabilities"]}}
    persist()
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run"])
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--catalog", type=Path, default=Path("reports/discovery.json"))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--approved-by", default="", help="Owner/admin authorizing this manual campaign")
    parser.add_argument("--routes", nargs="+", choices=["life-study", "dev-code", "portal-workhorse"])
    parser.add_argument("--output", type=Path, default=Path("reports/live-benchmark.json"))
    args = parser.parse_args()
    config = load_config()
    model = next((m for m in config.models if m.id == args.candidate), None)
    if model is None:
        parser.error("unknown registry candidate")
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    if args.action == "prepare":
        approved_dataset()
        if not eligible(model, catalog):
            parser.error("candidate requires fresh zero-price catalog evidence")
        # Isolate qualification deployments from the runtime gateway's approved pool.
        config.models = [model]
        folder = Path(".runtime/benchmark")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "litellm.yaml").write_text(yaml.safe_dump(render(config, {model.id})))
        print("Prepared isolated free benchmark proxy; runtime registry unchanged.")
        return
    if not args.live or not args.run_id or not args.approved_by.strip():
        parser.error("explicit --live, --approved-by and stable --run-id required")
    state = State(os.getenv("MG_BENCHMARK_STATE_PATH", ".runtime/benchmark.sqlite"))
    controls = State(os.getenv("MG_PROVIDER_CONTROL_STATE_PATH",
                               os.getenv("MG_STATE_PATH", ".runtime/state.sqlite")))
    adapter = LiteLLMAdapter(os.getenv("MG_BENCHMARK_PROXY_URL", "http://benchmark-proxy:4000"),
                            os.getenv("LITELLM_MASTER_KEY", ""))

    async def execute() -> dict[str, Any]:
        try:
            return await run(model, catalog, adapter, state, args.run_id, args.output,
                             set(args.routes) if args.routes else None,
                             approved_by=args.approved_by, control_state=controls)
        finally:
            await adapter.http.aclose()
            state.db.close()
            controls.db.close()
    try:
        report = asyncio.run(execute())
    except (ValueError, OSError):
        parser.exit(2, "Benchmark stopped; check run identity, output path and journal.\n")
    print(json.dumps({"status": report["status"], "candidate": model.id, "report": str(args.output)}))


if __name__ == "__main__":
    main()
