"""ASGI middleware shared by the gateway and DEEP applications."""
import asyncio
import time
import uuid
from typing import Any

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mg_ai.common.errors import MGError


class Boundary:
    """Envelope middleware: request-id tagging, body size cap and read deadline."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = 1048576) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        chunks: list[bytes] = []
        total = 0
        deadline = time.monotonic() + 10
        try:
            while True:
                message: Message = await asyncio.wait_for(
                    receive(), timeout=max(0, deadline - time.monotonic()))
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                total += len(chunk)
                if total > self.max_body_bytes:
                    raise MGError("REQUEST_TOO_LARGE", 413)
                chunks.append(chunk)
                if not message.get("more_body", False):
                    break
        except (MGError, TimeoutError) as exc:
            error: Any = exc if isinstance(exc, MGError) else MGError("REQUEST_READ_TIMEOUT", 408)
            await JSONResponse(error.body(request_id), status_code=error.status)(scope, receive, send)
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        async def tagged(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        await self.app(scope, replay, tagged)
