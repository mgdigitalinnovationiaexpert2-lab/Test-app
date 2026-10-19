"""Shared building blocks used by every MG module (errors, DTO base, middleware)."""
from mg_ai.common.base import StrictModel
from mg_ai.common.errors import MGError
from mg_ai.common.middleware import Boundary

__all__ = ["Boundary", "MGError", "StrictModel"]
