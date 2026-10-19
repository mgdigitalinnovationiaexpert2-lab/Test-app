"""Canonical error type shared by all modules (moved from mg_ai.errors)."""
from typing import Any


class MGError(Exception):
    def __init__(self, code: str, status: int = 400, *, retryable: bool = False,
                 reconciliation: bool = False) -> None:
        self.code = code
        self.status = status
        self.retryable = retryable
        self.reconciliation = reconciliation

    def body(self, request_id: str) -> dict[str, Any]:
        return {"error": {"type": "mg_gateway_error", "code": self.code,
                          "message": self.code.replace("_", " ").lower(),
                          "request_id": request_id, "retryable": self.retryable,
                          "execution_state": ("RECONCILIATION_REQUIRED" if self.reconciliation
                                              else "NOT_COMPLETED")}}
