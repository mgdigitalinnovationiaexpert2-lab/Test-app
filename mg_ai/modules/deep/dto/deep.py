"""DEEP DTOs: request/response contracts and attachment validation."""
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote
from uuid import UUID

from pydantic import Field, model_validator

from mg_ai.common.base import StrictModel

DEEP_ATTACHMENT_LIMIT = 10
DEEP_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
DEEP_TEXT_TOTAL_MAX_BYTES = 200_000
DEEP_TEXT_MIME_TYPES = {
    "text/plain", "text/markdown", "text/css", "text/html", "text/javascript",
    "application/javascript", "application/json", "application/xml", "text/xml",
}
DEEP_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}
DEEP_FILE_MIME_TYPES = {"application/pdf"}
DEEP_SUPPORTED_MIME_TYPES = DEEP_TEXT_MIME_TYPES | DEEP_IMAGE_MIME_TYPES | DEEP_FILE_MIME_TYPES


class DeepAttachment(StrictModel):
    index: int = Field(ge=0, lt=DEEP_ATTACHMENT_LIMIT)
    filename: str = Field(min_length=1, max_length=180)
    mime_type: str = Field(min_length=1, max_length=160)
    size_bytes: int = Field(gt=0, le=DEEP_ATTACHMENT_MAX_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def supported(self) -> "DeepAttachment":
        if self.mime_type not in DEEP_SUPPORTED_MIME_TYPES:
            raise ValueError("unsupported deep attachment type")
        if Path(self.filename).name != self.filename or "\x00" in self.filename:
            raise ValueError("unsafe attachment filename")
        return self


class DeepRequest(StrictModel):
    execution_id: UUID
    task_id: UUID
    conversation_id: UUID
    attempt: int = Field(ge=1, le=1000000)
    input: str = Field(min_length=1, max_length=32000)
    privacy_class: Literal["PUBLIC", "INTERNAL"]
    attachments: list[DeepAttachment] = Field(default_factory=list, max_length=DEEP_ATTACHMENT_LIMIT)

    @model_validator(mode="after")
    def attachment_contract(self) -> "DeepRequest":
        if len({item.index for item in self.attachments}) != len(self.attachments):
            raise ValueError("duplicate attachment index")
        if self.attachments and self.privacy_class != "INTERNAL":
            raise ValueError("private attachments require internal privacy")
        return self


class DeepResponse(StrictModel):
    execution_id: UUID
    task_id: UUID
    conversation_id: UUID
    request_id: str
    attempt: int
    status: Literal["COMPLETED"] = "COMPLETED"
    answer: str
    created_at: datetime
    completed_at: datetime
    continuity: Literal["TASK_SCOPED"] = "TASK_SCOPED"


def attachment_metadata_from_headers(index: int, headers: Any, body: bytes) -> DeepAttachment:
    """Validate staging headers plus payload against the attachment contract."""
    filename = unquote(headers["x-mg-filename"])
    mime_type = headers["content-type"].split(";", 1)[0].strip().lower()
    size_bytes = int(headers["x-mg-size"])
    sha256 = headers["x-mg-sha256"].lower()
    metadata = DeepAttachment(index=index, filename=filename, mime_type=mime_type,
                              size_bytes=size_bytes, sha256=sha256)
    if len(body) != metadata.size_bytes or hashlib.sha256(body).hexdigest() != metadata.sha256:
        raise ValueError("attachment integrity mismatch")
    return metadata
