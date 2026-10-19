"""DEEP module: private boundary service, DTOs and HTTP controller."""
from mg_ai.modules.deep.controller import router
from mg_ai.modules.deep.service import (DEEP_DEVELOPER_CONTEXT, OMNI_REVISION, DEEP_ROUTE,
                                        DeepAdapter, DeepService, secret_file)

__all__ = ["DEEP_DEVELOPER_CONTEXT", "DEEP_ROUTE", "DeepAdapter", "DeepService", "OMNI_REVISION",
           "router", "secret_file"]
