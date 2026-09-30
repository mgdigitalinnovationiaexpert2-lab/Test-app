"""Inspect only this project's HTTP endpoint; never use a live provider."""
import argparse
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--contract", action="store_true")
args = parser.parse_args()
env = dict(line.split("=", 1) for line in Path(".env").read_text().splitlines() if "=" in line)
url = "http://127.0.0.1:18088" if args.contract else "http://127.0.0.1:8090"
headers = {"Authorization": "Bearer " + env["MG_DEV_TOKEN"]}
with httpx.Client(base_url=url, timeout=90, trust_env=False) as client:
    assert client.get("/health/live").status_code == 200
    assert client.get("/v1/models").status_code == 401
    status = client.get("/health/ready", headers=headers)
    assert status.status_code == 200
    if not args.contract:
        # Refuse even the synthetic prompt if this is no longer a disabled-provider stack.
        assert status.json()["status"] == "configured_no_eligible_provider"
    payload = {"model": "dev-light", "messages": [{"role": "user", "content": "synthetic smoke"}]}
    response = client.post("/v1/chat/completions", headers=headers, json=payload)
    if args.contract:
        assert response.status_code == 502, response.text
        assert response.json()["error"]["execution_state"] == "RECONCILIATION_REQUIRED"
        response = client.post("/v1/chat/completions", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["choices"][0]["message"]["content"] == "synthetic-ok"
    else:
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "NO_ELIGIBLE_FREE_MODEL"
print("Docker HTTP smoke passed; no external inference.")
