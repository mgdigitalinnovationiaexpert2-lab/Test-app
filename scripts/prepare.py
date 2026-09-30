import json
from pathlib import Path

import yaml

from mg_ai.config import Configuration, load_config
from mg_ai.proxy_config import render

config = load_config()
root = Path(".runtime")
root.mkdir(exist_ok=True)
(root / "litellm.yaml").write_text(yaml.safe_dump(render(config), sort_keys=False))
Path("model-registry/config.schema.json").write_text(
    json.dumps(Configuration.model_json_schema(), indent=2) + "\n")
print("Validated configuration and rendered secret-free LiteLLM configuration.")
