import re
from typing import Any, Literal, Self

from jsonschema import Draft202012Validator
from pydantic import Field, model_validator

from mg_ai.config import Privacy, StrictModel


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
                if not isinstance(function, dict) or set(function) - {
                    "name", "description", "parameters", "strict"
                }:
                    raise ValueError("invalid function")
                if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", function.get("name", "")):
                    raise ValueError("invalid function name")
                schema = function.get("parameters", {})
                if not isinstance(schema, dict) or "$ref" in str(schema):
                    raise ValueError("local inline tool schema required")
                try:
                    Draft202012Validator.check_schema(schema)
                except Exception as exc:
                    raise ValueError("invalid tool schema") from exc
        if self.tool_choice is not None and not self.tools:
            raise ValueError("tool_choice requires tools")
        if isinstance(self.tool_choice, str) and self.tool_choice not in {"auto", "none", "required"}:
            raise ValueError("invalid tool choice")
        if isinstance(self.tool_choice, dict):
            if set(self.tool_choice) != {"type", "function"} or self.tool_choice["type"] != "function":
                raise ValueError("invalid tool choice")
            if self.tool_choice["function"] not in [{"name": t["function"]["name"]}
                                                    for t in self.tools or []]:
                raise ValueError("unknown tool choice")
        if self.response_format:
            fmt = self.response_format
            if fmt.get("type") not in {"json_object", "json_schema"}:
                raise ValueError("unsupported response format")
            if fmt["type"] == "json_schema":
                schema = fmt.get("json_schema", {}).get("schema")
                if not isinstance(schema, dict) or "$ref" in str(schema):
                    raise ValueError("local inline schema required")
                try:
                    Draft202012Validator.check_schema(schema)
                except Exception as exc:
                    raise ValueError("invalid schema") from exc
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
