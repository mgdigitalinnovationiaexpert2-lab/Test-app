"""DEEP DTOs."""
from mg_ai.modules.deep.dto.deep import (DEEP_ATTACHMENT_LIMIT, DEEP_ATTACHMENT_MAX_BYTES,
                                         DEEP_IMAGE_MIME_TYPES, DEEP_FILE_MIME_TYPES,
                                         DEEP_SUPPORTED_MIME_TYPES, DEEP_TEXT_MIME_TYPES,
                                         DEEP_TEXT_TOTAL_MAX_BYTES, DeepAttachment, DeepRequest,
                                         DeepResponse, attachment_metadata_from_headers)

__all__ = ["DEEP_ATTACHMENT_LIMIT", "DEEP_ATTACHMENT_MAX_BYTES", "DEEP_FILE_MIME_TYPES",
           "DEEP_IMAGE_MIME_TYPES", "DEEP_SUPPORTED_MIME_TYPES", "DEEP_TEXT_MIME_TYPES",
           "DEEP_TEXT_TOTAL_MAX_BYTES", "DeepAttachment", "DeepRequest", "DeepResponse",
           "attachment_metadata_from_headers"]
