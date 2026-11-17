"""Reusable Streamlit rendering helpers."""

import json
from itertools import groupby

import streamlit as st

from .sessions import Message

TOOL_LABELS = {
    "genie_ask": "Asking the data",
    "genie_poll_response": "Waiting for results",
    "genie_get_query_result": "Fetching full results",
    "genie_cancel_response": "Cancelling request",
}

CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 2rem; max-width: 52rem;}
.app-title {font-size: 1.6rem; font-weight: 650; margin: 0;}
.app-sub {color: #6b7280; margin: 0 0 1.2rem 0; font-size: .95rem;}
.meta {color: #8b93a1; font-size: .75rem; margin-top: .25rem;}
[data-testid="stSidebar"] .stButton button {text-align: left; justify-content: flex-start;}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, name.replace("_", " ").capitalize())


def _render_tool_group(tools: list[dict], live: bool) -> None:
    running = live and any(not t["done"] for t in tools)
    failed = any(not t["ok"] for t in tools)
    n = len(tools)
    label = f"{'Working' if running else 'Worked'} · {n} step{'s' if n != 1 else ''}"
    state = "running" if running else "error" if failed else "complete"
    with st.status(label, state=state, expanded=False):
        for t in tools:
            icon = "⏳" if not t["done"] else "✅" if t["ok"] else "⚠️"
            st.markdown(f"{icon} **{tool_label(t['name'])}**")
            if t["args"]:
                st.caption(json.dumps(t["args"], ensure_ascii=False)[:300])


def render_parts(msg: Message, live: bool = False) -> None:
    """Render an assistant message: text and consecutive tool steps, in order."""
    for kind, group in groupby(msg.parts, key=lambda p: p["kind"]):
        items = list(group)
        if kind == "text":
            cursor = " ▌" if live and items[-1] is msg.parts[-1] else ""
            st.markdown("".join(p["text"] for p in items) + cursor)
        elif kind == "tool":
            _render_tool_group(items, live)
        else:
            for p in items:
                st.error(p["text"])
    if live and not msg.parts:
        st.markdown("_Thinking…_")
    if msg.meta:
        m = msg.meta
        st.markdown(
            f"<div class='meta'>{m['model']} · {m['latency_s']}s · "
            f"{m['input_tokens']:,} in / {m['output_tokens']:,} out tokens · "
            f"{m['tool_calls']} tool call{'s' if m['tool_calls'] != 1 else ''}</div>",
            unsafe_allow_html=True,
        )


def render_message(msg: Message) -> None:
    with st.chat_message(msg.role, avatar="🧑‍💼" if msg.role == "user" else "🚢"):
        if msg.role == "user":
            st.markdown(msg.text)
        else:
            render_parts(msg)
