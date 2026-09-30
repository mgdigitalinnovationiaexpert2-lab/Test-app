import json
import os

from mg_ai.config import load_config
from mg_ai.state import State

config = load_config()
state = State(os.getenv("MG_STATE_PATH", ".runtime/state.sqlite"))
for model in config.models:
    print(json.dumps({"id": model.id, "configured_eligible": model.available(),
                      "configured_health": model.health, "runtime": state.health(model.id)}))
state.db.close()
