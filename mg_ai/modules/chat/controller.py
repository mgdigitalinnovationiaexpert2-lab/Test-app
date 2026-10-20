"""Chat controller: HTTP endpoints for the OpenAI-compatible surface."""
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from mg_ai.modules.chat.dto.chat import ChatRequest

router = APIRouter()

# Injected once by the gateway composition root via configure().
_service = None


def configure(service) -> None:
    """Inject the ChatService built by the gateway composition root."""
    global _service
    _service = service


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request) -> Response:
    client = _service.authenticate(request)
    body: ChatRequest = _service.parse(await request.body())
    return await _service.completions(request, client, body)


@router.get("/v1/models")
async def models(request: Request) -> dict[str, Any]:
    client = _service.authenticate(request)
    return _service.models(client)
