"""Chat-agent message + LangGraph state types."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str = ""
    thinking: str = ""
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)

    def to_openai(self) -> dict[str, Any]:
        """Render as the OpenAI/K2 chat-completion message format."""
        out: dict[str, Any] = {"role": self.role, "content": self.content or ""}
        if self.role == "assistant" and self.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": __import__("json").dumps(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]
        if self.role == "tool" and self.tool_call_id:
            out["tool_call_id"] = self.tool_call_id
        return out


class ChatState(TypedDict, total=False):
    """LangGraph state passed between nodes.

    Mutated in-place by node functions. Streaming is *out of band* via the
    EventBus so this dict stays small.
    """

    messages: list[ChatMessage]    # full conversation incl. system + tool messages
    case_summary: str               # slim case-file context (string-formatted)
    system_prompt: str              # picked by audience (oncologist vs patient)
    pending_tool_calls: list[ToolCall]
    rag_hits: list[dict[str, Any]]
    last_assistant_text: str
    last_assistant_thinking: str
    iteration: int                  # tool-call loop guard
