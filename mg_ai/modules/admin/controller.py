"""Admin module: health probes and provider eligibility reporting."""
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()

# Injected once by the gateway composition root via configure().
_authenticator = None
_readiness_probe = None


def configure(chat_service, readiness_probe) -> None:
    """Inject the shared authenticator and a callable producing the readiness payload."""
    global _authenticator, _readiness_probe
    _authenticator = chat_service.authenticate
    _readiness_probe = readiness_probe


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, Any]:
    client = _authenticator(request)
    return _readiness_probe(client)
