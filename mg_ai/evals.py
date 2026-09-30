import argparse
import json
import time
from pathlib import Path
from typing import Any

from pydantic import Field

from mg_ai.config import StrictModel

CATEGORIES = {"GENERAL", "MANAGEMENT", "HR", "PROCESS", "DATA", "MARKETING", "PRODUCTION",
              "IT_CODING", "LIFE_OS_STUDY", "DOCUMENT_ANALYSIS", "PERSIAN"}
DIMENSIONS = {"answer_quality", "correctness", "persian_quality", "coding_quality", "tool_calling",
              "structured_output", "error_rate", "latency_ms", "cost_usd", "success_rate"}


class Fixture(StrictModel):
    id: str
    category: str
    prompt: str
    expected_contains: list[str] = Field(min_length=1)
    reference_response: str
    rubric: str


def fixtures(path: Path) -> list[Fixture]:
    data = [Fixture.model_validate(json.loads(line)) for line in path.read_text(encoding="utf-8")
            .splitlines() if line.strip()]
    if {f.category for f in data} != CATEGORIES or len({f.id for f in data}) != len(data):
        raise ValueError("unique fixtures for every category are required")
    return data


def score(fixture: Fixture, response: str) -> dict[str, Any]:
    correct = all(word.casefold() in response.casefold() for word in fixture.expected_contains)
    return {"fixture": fixture.id, "category": fixture.category,
            "dimensions": {"correctness": float(correct)},
            "human_review_required": True, "rubric": fixture.rubric}


def run(data: list[Fixture], responses: dict[str, str] | None = None) -> dict[str, Any]:
    start = time.monotonic()
    if responses is not None and set(responses) != {f.id for f in data}:
        raise ValueError("responses must exactly match fixture ids")
    results = [score(f, responses[f.id] if responses is not None else f.reference_response)
               for f in data]
    return {"mode": "offline_answers" if responses is not None else "fixture_self_test",
            "not_a_model_quality_claim": True, "promotion": "manual_only",
            "elapsed_ms": (time.monotonic() - start) * 1000, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path("evals/fixtures/synthetic.jsonl"))
    parser.add_argument("--responses", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/evals.json"))
    args = parser.parse_args()
    responses = json.loads(args.responses.read_text(encoding="utf-8")) if args.responses else None
    report = run(fixtures(args.fixtures), responses)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(report['results'])} fixture results; no inference performed.")


if __name__ == "__main__":
    main()
