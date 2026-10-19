"""Explicit account observations, never an inference-time discovery service."""
import argparse
import hashlib
import json
import math
import os
import re
import time
from typing import Any, Literal

import httpx
from pydantic import Field

from mg_ai.common.base import StrictModel

OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"


class Capacity(StrictModel):
    provider: str
    account: str
    credential_fingerprint: str = ""
    tier: str = "UNKNOWN"
    free_now: Literal["UNKNOWN", "AVAILABLE", "UNAVAILABLE"] = "UNKNOWN"
    remaining_requests: int | None = Field(default=None, ge=0)
    remaining_tokens: int | None = Field(default=None, ge=0)
    remaining_credits: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    credit_reset_policy: Literal["daily", "weekly", "monthly"] | None = None
    requests_reset_at: float | None = None
    tokens_reset_at: float | None = None
    health: Literal["UNKNOWN", "HEALTHY", "AUTH_REJECTED", "RATE_LIMITED"] = "UNKNOWN"
    checked_at: float
    valid_until: float
    source: str
    reliable: bool = False

    def blocks(self, credential: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if (not self.reliable or not self.checked_at <= now < self.valid_until
                or self.credential_fingerprint != fingerprint(credential)):
            return False
        if self.health == "AUTH_REJECTED" or self.free_now == "UNAVAILABLE":
            return True
        # Dollar credit balance does not describe free-model request eligibility.
        return any(remaining == 0 and (reset is None or now < reset)
                   for remaining, reset in [(self.remaining_requests, self.requests_reset_at),
                                            (self.remaining_tokens, self.tokens_reset_at)])


def fingerprint(credential: str) -> str:
    return hashlib.sha256(credential.encode()).hexdigest() if credential else ""


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def openrouter_capacity(data: dict[str, Any], credential: str, now: float) -> Capacity:
    remaining = number(data.get("limit_remaining"))
    reset = data.get("limit_reset")
    return Capacity(provider="openrouter", account="OPENROUTER_API_KEY",
                    credential_fingerprint=fingerprint(credential),
                    tier="FREE" if data.get("is_free_tier") is True else "UNKNOWN",
                    remaining_credits=remaining, health="HEALTHY", checked_at=now,
                    credit_reset_policy=reset if reset in {"daily", "weekly", "monthly"} else None,
                    valid_until=now + 300, source=OPENROUTER_KEY_URL, reliable=True)


def duration(value: str) -> float | None:
    pieces = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h)", value)
    if not pieces or "".join(n + unit for n, unit in pieces) != value:
        return None
    result = sum(float(n) * {"ms": .001, "s": 1, "m": 60, "h": 3600}[unit]
                 for n, unit in pieces)
    return result if math.isfinite(result) else None


def groq_capacity(headers: dict[str, str], credential: str, now: float,
                  *, verified_direct_response: bool = False) -> Capacity:
    headers = {k.lower(): v for k, v in headers.items()}
    values: dict[str, Any] = {}
    for kind in ("requests", "tokens"):
        remaining = number(headers.get("x-ratelimit-remaining-" + kind))
        reset = duration(headers.get("x-ratelimit-reset-" + kind, ""))
        values["remaining_" + kind] = (int(remaining) if remaining is not None
                                        and remaining.is_integer() else None)
        values[kind + "_reset_at"] = now + reset if reset is not None else None
    return Capacity(provider="groq", account="GROQ_API_KEY",
                    credential_fingerprint=fingerprint(credential), checked_at=now,
                    valid_until=now + 60, source="https://api.groq.com/openai/v1 (response headers)",
                    reliable=verified_direct_response, **values)


def refresh_openrouter(credential: str, http: httpx.Client) -> Capacity:
    now = time.time()
    unknown = Capacity(provider="openrouter", account="OPENROUTER_API_KEY",
                       credential_fingerprint=fingerprint(credential), checked_at=now,
                       valid_until=now + 300, source=OPENROUTER_KEY_URL)
    if not credential:
        return unknown
    try:
        response = http.get(OPENROUTER_KEY_URL,
                            headers={"Authorization": "Bearer " + credential})
        if response.status_code in {401, 403}:
            return unknown.model_copy(update={"health": "AUTH_REJECTED", "reliable": True})
        response.raise_for_status()
        data = response.json()["data"]
        if not isinstance(data, dict):
            return unknown
        return openrouter_capacity(data, credential, now)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return unknown


def main() -> None:
    from mg_ai.state import State
    parser = argparse.ArgumentParser(description="Read account metadata only; no inference")
    parser.add_argument("--state", default=os.getenv("MG_STATE_PATH", ".runtime/state.sqlite"))
    args = parser.parse_args()
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as http:
        snapshot = refresh_openrouter(os.getenv("OPENROUTER_API_KEY", ""), http)
    state = State(args.state)
    try:
        state.save_capacity(snapshot)
    finally:
        state.db.close()
    print(json.dumps(snapshot.model_dump(exclude={"credential_fingerprint"}), indent=2))


if __name__ == "__main__":
    main()
