"""Compatibility alias for the authoritative Chat DTOs.

The request contracts and their validation live in
mg_ai.modules.chat.dto.chat; this module only re-exports them so existing
imports of mg_ai.requests keep working unchanged.
"""
from mg_ai.modules.chat.dto.chat import ChatRequest, Message, RoutingInput

__all__ = ["ChatRequest", "Message", "RoutingInput"]
