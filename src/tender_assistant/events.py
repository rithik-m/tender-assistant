"""UI-agnostic events emitted while the agent answers.

Every event is a plain dataclass with `to_dict()`, so the same stream can be
rendered by Streamlit today or serialized as SSE/JSON by an API tomorrow.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


@dataclass
class Event:
    type: str = field(init=False)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TextDelta(Event):
    text: str
    type: Literal["text"] = field(default="text", init=False)


@dataclass
class ToolStarted(Event):
    id: str
    name: str
    args: dict[str, Any]
    type: Literal["tool_start"] = field(default="tool_start", init=False)


@dataclass
class ToolFinished(Event):
    id: str
    name: str
    output: str
    ok: bool
    type: Literal["tool_end"] = field(default="tool_end", init=False)


@dataclass
class RunFinished(Event):
    """Final metadata for one assistant turn."""

    thread_id: str
    model: str
    latency_s: float
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    type: Literal["done"] = field(default="done", init=False)


@dataclass
class RunFailed(Event):
    error: str
    type: Literal["error"] = field(default="error", init=False)
