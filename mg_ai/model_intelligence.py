"""Manual external evidence and MG result recommendations, never registry mutation."""
from datetime import datetime
import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from mg_ai.config import StrictModel


class ExternalEvidence(StrictModel):
    model: str
    source: Literal["Artificial Analysis", "LiveBench", "LMArena", "OpenRouter"]
    reference: str = Field(pattern=r"^https://[^\s]+$")
    observed_at: datetime
    metric: str
    value: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def timestamp(self) -> "ExternalEvidence":
        if self.observed_at.tzinfo is None:
            raise ValueError("external evidence requires timezone")
        return self


def recommendations(reports: list[dict[str, Any]], dataset_hash: str,
                    thresholds: dict[str, dict[str, float]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for route, limits in thresholds.items():
        pool = []
        for report in reports:
            if (report.get("mode") != "live_free" or report.get("status") != "COMPLETED"
                    or report.get("paid_allowed") is not False
                    or report.get("dataset_sha256") != dataset_hash
                    or not (report.get("provider") == "groq"
                            or report.get("provider") == "openrouter"
                            and str(report.get("model", "")).endswith(":free"))):
                continue
            rows = [r for r in report.get("results", []) if r.get("route") == route]
            if not rows or any(r.get("outcome") != "SUCCESS" or
                               not math.isfinite(r.get("latency_ms", float("nan"))) or
                               r["latency_ms"] < 0 for r in rows):
                continue
            scores = {dimension: min((r.get("scores", {}).get(dimension, 0) for r in rows
                                      if dimension in r.get("scores", {})), default=0)
                      for dimension in limits}
            if not all(isinstance(scores[k], (int, float)) and math.isfinite(scores[k])
                       and v <= scores[k] <= 1 for k, v in limits.items()):
                continue
            pool.append({"model": report["model"], "run_id": report["run_id"],
                         "score": min(scores[k] for k in limits),
                         "latency_ms": sum(r["latency_ms"] for r in rows) / len(rows)})
        ranked = sorted(pool, key=lambda r: (-r["score"], r["latency_ms"], r["model"]))
        unique = {row["model"]: row for row in reversed(ranked)}
        ranked = sorted(unique.values(), key=lambda r: (-r["score"], r["latency_ms"], r["model"]))
        result[route] = {"status": "PROVISIONAL_REVIEW_REQUIRED" if ranked else "BLOCKED",
                         "recommended_champion": ranked[0] if ranked else None,
                         "recommended_fallback": ranked[1] if len(ranked) > 1 else None,
                         "challengers": ranked[2:], "automatic_promotion": False,
                         "required_review": ["qualitative Persian/code review", "privacy", "capacity",
                                             "free status expiry", "owner approval"]}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare fixed-dataset MG reports; never promote")
    parser.add_argument("--reports", type=Path, nargs="*", default=[])
    parser.add_argument("--output", type=Path, default=Path("reports/champion-recommendations.json"))
    args = parser.parse_args()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports]
    data = recommendations(reports, hashlib.sha256(Path("evals/live-cases.json").read_bytes()).hexdigest(),
                           json.loads(Path("evals/live-thresholds.json").read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("Wrote provisional route recommendations; registry unchanged.")


if __name__ == "__main__":
    main()
