"""Compatibility aliases; DEEP continuity lives in mg_ai.database."""
from mg_ai.database.deep_repository import (DEEP_CONTEXT_MAX_CHARS, DEEP_CONTEXT_VERSION,
                                            DEEP_SETTLEMENT_SECONDS, DeepRepository)

DeepState = DeepRepository
__all__ = ["DEEP_CONTEXT_MAX_CHARS", "DEEP_CONTEXT_VERSION", "DEEP_SETTLEMENT_SECONDS",
           "DeepRepository", "DeepState"]
