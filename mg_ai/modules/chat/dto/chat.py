"""Chat request DTOs: definition and validation of inbound completions payloads."""
import re
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from mg_ai.common.base import StrictModel
from mg_ai.config.constants import Privacy


class Message(StrictModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    name: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def content_safety(self) -> Self:
        if isinstance(self.content, list):
            for part in self.content:
                if part.get("type") == "text" and set(part) == {"type", "text"}:
                    if not isinstance(part["text"], str):
                        raise ValueError("invalid text")
                elif part.get("type") == "image_url" and set(part) == {"type", "image_url"}:
                    image = part["image_url"]
                    if not isinstance(image, dict) or set(image) - {"url", "detail"}:
                        raise ValueError("invalid image")
                    # Remote URLs permit server-side fetches; accept inline images only.
                    if not re.fullmatch(r"data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+",
                                        str(image.get("url", ""))):
                        raise ValueError("inline images only")
                    if image.get("detail", "auto") not in {"auto", "low", "high"}:
                        raise ValueError("invalid image detail")
                else:
                    raise ValueError("unsupported content part")
        return self


class RoutingInput(StrictModel):
    required_capabilities: set[str] = Field(default_factory=set)
    privacy_class: Privacy | None = None
    context_tokens: int = Field(default=0, ge=0, le=1000000)
    latency_preference: Literal["quality", "fast"] = "quality"
    max_cost_class: Literal["FREE", "SUBSCRIPTION"] | None = None


class ChatRequest(StrictModel):
    model: str = Field(max_length=64)
    messages: list[Message] = Field(min_length=1, max_length=256)
    max_tokens: int = Field(default=1024, gt=0, le=32768)
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)
    top_p: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    stop: str | list[str] | None = None
    stream: bool = False
    stream_options: dict[str, bool] | None = None
    tools: list[dict[str, Any]] | None = Field(default=None, max_length=64)
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    mg: RoutingInput = Field(default_factory=RoutingInput)

    @model_validator(mode="after")
    def supported_options(self) -> Self:
        if self.stream_options and set(self.stream_options) != {"include_usage"}:
            raise ValueError("unsupported stream options")
        if self.tools:
            for tool in self.tools:
                if set(tool) != {"type", "function"} or tool["type"] != "function":
                    raise ValueError("function tools only")
                function = tool["function"]
                if not isinstance(function, dict) or "name" not in function:
                    raise ValueError("invalid function tool")
        return self

    def capabilities(self) -> set[str]:
        required = set(self.mg.required_capabilities)
        if self.tools or any(m.tool_calls or m.role == "tool" for m in self.messages):
            required.add("TOOL_CALLING")
        if self.response_format:
            required.add("STRUCTURED_OUTPUT")
        if any(isinstance(m.content, list) and any(p["type"] == "image_url" for p in m.content)
               for m in self.messages):
            required.add("VISION")
        return required
