"""Chat module: OpenAI-compatible /v1/chat/completions over the FREE registry."""
from mg_ai.modules.chat.controller import router
from mg_ai.modules.chat.dto.chat import ChatRequest, Message, RoutingInput

__all__ = ["ChatRequest", "Message", "RoutingInput", "configure", "router"]


def configure(service) -> None:
    """Compatibility hook; controllers self-configure via their module-level configure()."""
    from mg_ai.modules.chat import controller
    controller.configure(service)
