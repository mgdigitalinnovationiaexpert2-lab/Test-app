"""Chat controller: HTTP endpoints for the OpenAI-compatible surface."""
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response

from mg_ai.modules.chat.dto.chat import ChatRequest

router = APIRouter()


def configure(service) -> None:
    """Inject the ChatService built by the gateway composition root."""
    router.state.service = service


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request) -> Response:
    service = router.state.service
    client = service.authenticate(request)
    body: ChatRequest = service.parse(await request.body())
    return await service.completions(request, client, body)


@router.get("/v1/models")
async def models(request: Request) -> dict[str, Any]:
    service = router.state.service
    client = service.authenticate(request)
    return service.models(client)
