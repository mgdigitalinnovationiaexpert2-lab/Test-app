"""MG AI Gateway composition root.

Wires the modular feature packages together:
  modules/chat        -> /v1/chat/completions, /v1/models
  modules/executions  -> /internal/executions/reconcile
  modules/admin       -> /health/live, /health/ready
Business logic lives in each module's service.py; HTTP shapes live in controller.py;
request/response contracts live in dto/. This file only builds dependencies and
registers routers, middleware and exception handlers.
"""
import hashlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mg_ai.common.errors import MGError
from mg_ai.common.middleware import Boundary
from mg_ai.config import Configuration, load_config
from mg_ai.database.gateway_repository import GatewayRepository
from mg_ai.modules import admin, chat, executions
from mg_ai.modules.admin.service import AdminService
from mg_ai.modules.chat.service import ChatService, build_token_hashes
from mg_ai.modules.executions.service import ExecutionsService
from mg_ai.programmer import ProgrammerAdapter
from mg_ai.providers import LiteLLMAdapter


def create_app(config: Configuration | None = None, state: GatewayRepository | None = None,
               adapter: LiteLLMAdapter | None = None,
               programmer: ProgrammerAdapter | None = None) -> FastAPI:
    config = config or load_config(Path(os.getenv("MG_CONFIG_ROOT", ".")))
    state = state or GatewayRepository(os.getenv("MG_STATE_PATH", ".runtime/state.sqlite"))
    token_hashes = build_token_hashes(config)
    master = os.getenv("LITELLM_MASTER_KEY", "")
    seen_hashes = {digest for _, digest in token_hashes}
    if adapter is None and (len(master) < 32
                            or hashlib.sha256(master.encode()).digest() in seen_hashes):
        raise ValueError("configure a distinct strong LiteLLM master key")
    adapter = adapter or LiteLLMAdapter(os.getenv("MG_PROXY_URL", "http://127.0.0.1:4000"), master)
    if programmer is None and os.getenv("MG_PROGRAMMER_ENABLED", "false").lower() == "true":
        programmer = ProgrammerAdapter.from_file(
            os.getenv("MG_PROGRAMMER_OMNI_URL", "http://omniroute:20129"),
            os.getenv("MG_PROGRAMMER_TOKEN_FILE", ""))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await adapter.http.aclose()
        if programmer:
            await programmer.http.aclose()
        state.db.close()

    app = FastAPI(title="MG AI Infrastructure", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(Boundary)

    # Dependency wiring: controllers receive their services here and nothing else.
    chat_service = ChatService(config, state, adapter, programmer, token_hashes)
    chat.controller.configure(chat_service)
    executions.controller.configure(ExecutionsService(state), chat_service)
    admin.controller.configure(chat_service, AdminService(config, state, programmer).ready)

    @app.exception_handler(MGError)
    async def mg_error(request: Request, error: MGError) -> JSONResponse:
        return JSONResponse(error.body(request.state.request_id), status_code=error.status,
                            headers={"Retry-After": "60"} if error.retryable else None)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(MGError("INVALID_REQUEST").body(request.state.request_id), status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        # Exception strings can contain credentials or provider response bodies.
        return JSONResponse(MGError("GATEWAY_UNAVAILABLE", 503,
                                   reconciliation=True).body(request.state.request_id),
                            status_code=503)

    app.include_router(admin.router)
    app.include_router(chat.router)
    app.include_router(executions.router)
    return app
