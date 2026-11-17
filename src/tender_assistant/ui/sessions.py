"""Chat session model and a thin store over st.session_state.

Messages are stored as ordered "parts" (text / tool steps / errors) so a reply
can be re-rendered exactly as it streamed. Agent-side context lives in the
agent's checkpointer, keyed by `ChatSession.id` (used as the thread_id).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import streamlit as st

from ..events import Event, RunFailed, RunFinished, TextDelta, ToolFinished, ToolStarted


@dataclass
class Message:
    role: str  # "user" | "assistant"
    parts: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] | None = None  # RunFinished data for assistant turns

    @classmethod
    def user(cls, text: str) -> "Message":
        return cls("user", [{"kind": "text", "text": text}])

    @property
    def text(self) -> str:
        return "".join(p["text"] for p in self.parts if p["kind"] == "text")

    def apply(self, ev: Event) -> None:
        """Fold a streamed agent event into this message."""
        if isinstance(ev, TextDelta):
            if self.parts and self.parts[-1]["kind"] == "text":
                self.parts[-1]["text"] += ev.text
            else:
                self.parts.append({"kind": "text", "text": ev.text})
        elif isinstance(ev, ToolStarted):
            self.parts.append(
                {"kind": "tool", "id": ev.id, "name": ev.name, "args": ev.args, "done": False, "ok": True}
            )
        elif isinstance(ev, ToolFinished):
            for p in self.parts:
                if p["kind"] == "tool" and p["id"] == ev.id:
                    p.update(done=True, ok=ev.ok)
        elif isinstance(ev, RunFinished):
            self.meta = ev.to_dict()
        elif isinstance(ev, RunFailed):
            self.parts.append({"kind": "error", "text": ev.error})


@dataclass
class ChatSession:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = "New chat"
    created: datetime = field(default_factory=datetime.now)
    messages: list[Message] = field(default_factory=list)

    @property
    def usage(self) -> dict[str, float]:
        metas = [m.meta for m in self.messages if m.meta]
        return {
            "turns": len(metas),
            "input_tokens": sum(m["input_tokens"] for m in metas),
            "output_tokens": sum(m["output_tokens"] for m in metas),
            "tool_calls": sum(m["tool_calls"] for m in metas),
        }


class SessionStore:
    """Per-browser-tab sessions. Replace with a DB/cookie-backed store later."""

    _KEY = "_sessions"

    def __init__(self):
        state = st.session_state
        if self._KEY not in state:
            first = ChatSession()
            state[self._KEY] = {first.id: first}
            state["_active"] = first.id
        self.sessions: dict[str, ChatSession] = state[self._KEY]

    @property
    def active(self) -> ChatSession:
        return self.sessions[st.session_state["_active"]]

    def new(self) -> ChatSession:
        # Reuse an untouched empty chat instead of piling up blank ones.
        for s in self.sessions.values():
            if not s.messages:
                st.session_state["_active"] = s.id
                return s
        s = ChatSession()
        self.sessions[s.id] = s
        st.session_state["_active"] = s.id
        return s

    def select(self, session_id: str) -> None:
        st.session_state["_active"] = session_id

    def delete(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
        if not self.sessions:
            self.new()
        elif st.session_state["_active"] == session_id:
            st.session_state["_active"] = next(reversed(self.sessions))

    def recent_first(self) -> list[ChatSession]:
        return sorted(self.sessions.values(), key=lambda s: s.created, reverse=True)
