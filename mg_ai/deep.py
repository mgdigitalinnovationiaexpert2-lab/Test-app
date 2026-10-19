"""Private DEEP boundary, separate from FREE Gateway routes and credentials.

Composition root for the DEEP feature module (mg_ai.modules.deep): builds the
repository, adapter and service, then registers the module router plus the
Boundary middleware and exception handlers. HTTP shapes live in controller.py,
business logic in service.py and request/response contracts in dto/.
"""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from mg_ai.common.errors import MGError
from mg_ai.common.middleware import Boundary
from mg_ai.database.deep_repository import (DEEP_CONTEXT_VERSION, DEEP_SETTLEMENT_SECONDS,
                                             DeepRepository)
from mg_ai.modules.deep.controller import configure, error_response, router
from mg_ai.modules.deep.dto.deep import DEEP_ATTACHMENT_MAX_BYTES, DeepRequest, DeepResponse
from mg_ai.modules.deep.service import (DEEP_DEVELOPER_CONTEXT, DEEP_ROUTE, OMNI_REVISION,
                                        DeepAdapter, DeepService, secret_file)

# Compatibility re-exports: tests and tooling import these from mg_ai.deep.
__all__ = ["DEEP_CONTEXT_VERSION", "DEEP_DEVELOPER_CONTEXT", "DEEP_ROUTE", "DEEP_SETTLEMENT_SECONDS",
           "DeepAdapter", "DeepRepository", "DeepRequest", "DeepResponse", "OMNI_REVISION",
           "create_deep_app", "secret_file"]


def create_deep_app(state: DeepRepository | None = None, adapter: DeepAdapter | None = None,
                    token: str | None = None) -> FastAPI:
    state = state or DeepRepository(os.getenv("MG_STATE_PATH", ".runtime/state.sqlite"))
    token = token if token is not None else secret_file("MG_DEEP_TOKEN_FILE")
    upstream_token = secret_file("MG_OMNI_TOKEN_FILE")
    if token and token == upstream_token:
        raise ValueError("DEEP client and upstream credentials must be distinct")
    configured = adapter is not None or len(upstream_token) >= 20
    optimize_previous = os.getenv("MG_DEEP_PREVIOUS_RESPONSE_OPTIMIZATION", "false").lower()
    adapter = adapter or DeepAdapter(
        os.getenv("MG_OMNI_URL", "http://omniroute:20129"), upstream_token,
        optimize_previous_response=optimize_previous == "true",
    )
    attachment_root = Path(os.getenv("MG_DEEP_ATTACHMENT_ROOT", "/state/deep-attachments"))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await adapter.http.aclose()
        state.db.close()

    app = FastAPI(title="MG private DEEP", docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.add_middleware(Boundary, max_body_bytes=DEEP_ATTACHMENT_MAX_BYTES + 65536)

    # Dependency wiring for the DEEP module controller.
    configure(DeepService(state, adapter, configured, attachment_root), token)

    @app.exception_handler(MGError)
    async def error(request: Request, exc: MGError) -> JSONResponse:
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(MGError("INVALID_REQUEST").body(request.state.request_id), status_code=400)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(MGError("DEEP_UNAVAILABLE", 503, reconciliation=True).body(
            request.state.request_id), status_code=503)

    app.include_router(router)
    return app
