import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx

from mg_ai.config import Configuration, load_config
from mg_ai.model_intelligence import ExternalEvidence

SOURCE = "https://openrouter.ai/api/v1/models"
GROQ_SOURCE = "https://api.groq.com/openai/v1/models"


def free_model(row: dict[str, Any]) -> bool:
    prices = row.get("pricing", {})
    try:
        return (all(k in prices for k in ("prompt", "completion"))
                and all(Decimal(str(v)).is_finite() and Decimal(str(v)) == 0
                        for v in prices.values())
                and (row["id"].endswith(":free") or row["id"] == "openrouter/free"))
    except (InvalidOperation, KeyError, TypeError, AttributeError):
        return False


def proposal(rows: list[dict[str, Any]], previous: list[dict[str, Any]],
             config: Configuration | None = None) -> dict[str, Any]:
    free = [{"model": row["id"], "context_limit": row.get("context_length"),
             "supported_parameters": row.get("supported_parameters", []),
             "input_modalities": row.get("architecture", {}).get("input_modalities", []),
             "pricing": row.get("pricing", {}),
             "enabled": False, "approved": False} for row in rows if free_model(row)]
    current = {row["model"] for row in free}
    old = {row["model"] for row in previous}
    by_id = {row["id"]: row for row in rows}
    old_rows = {row["model"]: row for row in previous}
    changes = [{"model": row["model"], "fields": [field for field in
                ("context_limit", "supported_parameters", "input_modalities", "pricing")
                if row.get(field) != old_rows[row["model"]].get(field)]}
               for row in free if row["model"] in old_rows]
    recommendations = []
    for row in free:
        candidate = next((m for m in config.models if m.model == row["model"]), None) if config else None
        routes = ["dev-light", "life-study", "study-generation", "portal-light", "portal-workhorse"]
        if "tools" in row["supported_parameters"]:
            routes.extend(["dev-code", "dev-reasoning", "dev-strong"])
        if "image" in row["input_modalities"]:
            routes.append("dev-vision")
        random = row["model"] == "openrouter/free"
        recommendations.append({"model": row["model"], "provider": "openrouter",
            "free_status": "CATALOG_ZERO_PRICE", "suggested_routes": [] if random else routes,
            "advertised_metadata": row, "verified_capabilities": sorted(candidate.capabilities)
            if candidate and candidate.approved else [],
            "external_evidence": [{"source": SOURCE, "kind": "official_catalog"}],
            "current_champions": {name: config.routes[name].champion for name in routes
                                  if config and name in config.routes},
            "mg_benchmark_scores": candidate.benchmark_scores if candidate else {},
            "privacy_status": "REVIEWED" if candidate and candidate.data_policy_reviewed else "UNKNOWN",
            "status": "REJECTED" if random else "NOT_BENCHMARKED",
            "reason": "Nondeterministic router cannot be Champion" if random else
            "Evaluate advertised compatibility against route Champion; MG benchmark and privacy review required",
            "automatic_promotion": False})
    return {"source": SOURCE, "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "new": sorted(current - old), "removed_or_no_longer_free": sorted(old - current),
            "removed": sorted(old - by_id.keys()),
            "no_longer_free": sorted(model for model in old & by_id.keys()
                                     if not free_model(by_id[model])),
            "metadata_changes": [change for change in changes if change["fields"]],
            "recommendations": recommendations,
            "candidates": free, "quota": "not provided by catalog; review account limits"}


def groq_proposal(rows: list[dict[str, Any]], config: Configuration | None = None, *,
                  owner_confirm_free: bool = False,
                  owner_confirm_zdr: bool = False) -> dict[str, Any]:
    candidates = [{"model": row["id"], "active": row.get("active") is True,
                   "context_limit": row.get("context_window"),
                   "max_output_tokens": row.get("max_completion_tokens"),
                   "enabled": False, "approved": False}
                  for row in rows if isinstance(row.get("id"), str)]
    configured = {model.model: model for model in config.models
                  if model.provider == "groq"} if config else {}
    return {"source": GROQ_SOURCE, "provider": "groq",
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "account_free_confirmed_by_owner": owner_confirm_free,
            "global_zdr_confirmed_by_owner": owner_confirm_zdr,
            "candidates": candidates,
            "recommendations": [{"model": row["model"], "provider": "groq",
                "free_status": "OWNER_CONFIRMED_FREE_PROJECT",
                "privacy_status": "GLOBAL_ZDR_OWNER_CONFIRMED",
                "verified_capabilities": sorted(configured[row["model"]].capabilities)
                if row["model"] in configured and configured[row["model"]].approved else [],
                "status": "NOT_BENCHMARKED", "automatic_promotion": False}
                for row in candidates]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read official metadata; never enable runtime models")
    parser.add_argument("--provider", choices=["openrouter", "groq"], default="openrouter")
    parser.add_argument("--owner-confirm-free-project", action="store_true")
    parser.add_argument("--owner-confirm-global-zdr", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("reports/discovery.json"))
    parser.add_argument("--external-evidence", type=Path,
                        help="Manually reviewed external ranking metadata; never runtime authority")
    args = parser.parse_args()
    if args.provider == "groq":
        if not args.owner_confirm_free_project or not args.owner_confirm_global_zdr:
            parser.error("Groq discovery requires explicit owner FREE-project and Global ZDR confirmation")
        credential = os.getenv("GROQ_API_KEY", "")
        if not credential:
            parser.error("GROQ_API_KEY is required")
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            response = client.get(GROQ_SOURCE, headers={"Authorization": "Bearer " + credential})
            response.raise_for_status()
            rows = response.json()["data"]
            details = []
            for row in rows:
                detail = client.get(GROQ_SOURCE + "/" + row["id"],
                                    headers={"Authorization": "Bearer " + credential})
                details.append(detail.json() if detail.status_code == 200 else row)
        result = groq_proposal(details, load_config(),
                               owner_confirm_free=args.owner_confirm_free_project,
                               owner_confirm_zdr=args.owner_confirm_global_zdr)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, indent=2) + "\n")
        temporary.replace(args.output)
        print(f"Wrote disabled proposals to {args.output}")
        return
    previous = json.loads(args.output.read_text())["candidates"] if args.output.exists() else []
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.get(SOURCE)
        response.raise_for_status()
        rows = response.json()["data"]
    result = proposal(rows, previous, load_config())
    if args.external_evidence:
        evidence = [ExternalEvidence.model_validate(row).model_dump(mode="json") for row in
                    json.loads(args.external_evidence.read_text(encoding="utf-8"))]
        for recommendation in result["recommendations"]:
            recommendation["external_evidence"].extend(
                row for row in evidence if row["model"] == recommendation["model"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(args.output)
    print(f"Wrote disabled proposals to {args.output}")


if __name__ == "__main__":
    main()
