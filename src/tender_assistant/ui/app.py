"""Streamlit chat UI for the Tender Assistant.

Run from the project root:  uv run streamlit run src/tender_assistant/ui/app.py
"""

import streamlit as st

from tender_assistant.agent import AgentService
from tender_assistant.config import get_settings
from tender_assistant.ui.components import inject_css, render_message, render_parts
from tender_assistant.ui.sessions import ChatSession, Message, SessionStore

SUGGESTIONS = [
    "Who are the pricing focal points for each trade?",
    "What changed in average selling price last month?",
    "Show the top 5 products by discount rate this quarter",
]

st.set_page_config(page_title="Tender Assistant", page_icon="🚢", layout="centered")


@st.cache_resource(show_spinner=False)
def get_service() -> AgentService:
    """One agent (and event loop) shared by all browser sessions."""
    return AgentService()


def sidebar(store: SessionStore, service: AgentService) -> None:
    settings = get_settings()
    with st.sidebar:
        st.markdown(f"### 🚢 {settings.assistant_name}")
        if st.button("＋ New chat", use_container_width=True, type="primary"):
            store.new()
            st.rerun()

        st.caption("CHATS")
        for s in store.recent_first():
            is_active = s.id == store.active.id
            cols = st.columns([5, 1])
            if cols[0].button(
                s.title, key=f"sel-{s.id}", use_container_width=True,
                type="secondary" if not is_active else "tertiary", disabled=is_active,
            ):
                store.select(s.id)
                st.rerun()
            if cols[1].button("✕", key=f"del-{s.id}", help="Delete chat"):
                service.reset(s.id)
                store.delete(s.id)
                st.rerun()

        st.divider()
        st.caption("SESSION")
        active = store.active
        usage = active.usage
        st.markdown(
            f"**Status:** {'🟢 Agent ready' if service.tool_names else '🟡 Starts on first message'}  \n"
            f"**Model:** `{settings.model_endpoint}`  \n"
            f"**Tools:** {len(service.tool_names)}  \n"
            f"**Session:** `{active.id}`  \n"
            f"**Turns:** {usage['turns']} · **Tool calls:** {int(usage['tool_calls'])}  \n"
            f"**Tokens:** {int(usage['input_tokens']):,} in / {int(usage['output_tokens']):,} out"
        )


def run_turn(service: AgentService, session: ChatSession, prompt: str) -> None:
    if not session.messages:
        session.title = prompt[:40] + ("…" if len(prompt) > 40 else "")
    user_msg, reply = Message.user(prompt), Message("assistant")
    session.messages += [user_msg, reply]
    render_message(user_msg)
    with st.chat_message("assistant", avatar="🚢"):
        slot = st.empty()
        with slot.container():
            render_parts(reply, live=True)
        for event in service.stream(session.id, prompt):
            reply.apply(event)
            with slot.container():
                render_parts(reply, live=True)
        with slot.container():
            render_parts(reply)
    st.rerun()  # refresh sidebar stats and chat title


def main() -> None:
    inject_css()
    service, store = get_service(), SessionStore()
    session = store.active
    sidebar(store, service)

    st.markdown("<p class='app-title'>Tender Assistant</p>"
                "<p class='app-sub'>Ask about pricing, discounts and sales in plain language.</p>",
                unsafe_allow_html=True)

    for msg in session.messages:
        render_message(msg)

    prompt = st.chat_input("Ask a question about your data…")
    if not session.messages:
        cols = st.columns(len(SUGGESTIONS))
        for col, text in zip(cols, SUGGESTIONS):
            if col.button(text, key=f"sg-{text}", use_container_width=True):
                prompt = text
    if prompt:
        run_turn(service, session, prompt)


main()
