"""Generate an isolated synthetic configuration; no provider secrets or real inference."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from mg_ai.config import Candidate, Retry429Review, load_config
from mg_ai.proxy_config import render

config = load_config()
config.models = [Candidate(
    id=name, provider="openai-compatible", model=name,
    enabled=True, approved=True, data_policy_reviewed=True,
    credential_env="MOCK_PROVIDER_KEY", api_base="http://mock:9000/v1",
    context_limit=32768, quality_tier="FRONTIER", health="HEALTHY",
    capabilities=config.clients["developer"].allowed_capabilities,
    privacy_classes={"PUBLIC", "INTERNAL"}, benchmark_scores={"GENERAL": score},
    free_evidence="local synthetic fake endpoint, no external inference",
    free_verified_until=datetime.now(timezone.utc) + timedelta(hours=2),
    retry_429_review=Retry429Review(
        adapter="LiteLLMAdapter", provider="openai-compatible", model=name,
        semantics="REJECTED_BEFORE_EXECUTION", reviewed_by="local mock contract",
        evidence="tests/mock_provider.py: deterministic mock-limit rejection; synthetic only",
        valid_until=datetime.now(timezone.utc) + timedelta(hours=2),
    ) if name == "mock-limit" else None,
) for name, score in [("mock-error", .99), ("mock-limit", .98), ("mock-ok", .97)]]
root = Path(".runtime/contract")
for directory, name, value in [("model-registry", "models", [m.model_dump(mode="json") for m in config.models]),
                               ("policies", "clients", {k: v.model_dump(mode="json") for k, v in config.clients.items()}),
                               ("routing", "routes", {k: v.model_dump(mode="json") for k, v in config.routes.items()})]:
    path = root / directory
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{name}.json").write_text(json.dumps(value, indent=2))
(root / "litellm.yaml").write_text(yaml.safe_dump(render(config), sort_keys=False))
print("Prepared local mock-only contract configuration.")
