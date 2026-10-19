"""Executions DTOs: reconciliation request contract."""
import re

from pydantic import field_validator

from mg_ai.common.base import StrictModel


class ReconciliationRequest(StrictModel):
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def valid_key(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
            raise ValueError("invalid idempotency key")
        return value
