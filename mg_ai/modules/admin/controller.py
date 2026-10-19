"""Admin module: health probes and provider eligibility reporting."""
from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


def configure(chat_service, readiness_probe) -> None:
    """Inject the shared authenticator and a callable producing the readiness payload."""
    router.state.authenticator = chat_service.authenticate
    router.state.readiness_probe = readiness_probe


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request) -> dict[str, Any]:
    client = router.state.authenticator(request)
    return router.state.readiness_probe(client)
