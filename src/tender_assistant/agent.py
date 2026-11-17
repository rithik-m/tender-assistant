"""Agent service: owns the LangGraph agent and exposes a UI-agnostic event stream.

The agent (MCP client, model, checkpointer) lives on a dedicated background
event loop, so it survives Streamlit reruns and can later be dropped behind a
FastAPI endpoint by consuming `astream()` directly.
"""

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Iterator
from typing import Any

from databricks_langchain import (
    ChatDatabricks,
    DatabricksMCPServer,
    DatabricksMultiServerMCPClient,
)
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from .config import Settings, get_settings, get_workspace_client
from .events import Event, RunFailed, RunFinished, TextDelta, ToolFinished, ToolStarted
from .prompt import build_system_prompt

MAX_TOOL_OUTPUT_CHARS = 4000


def _as_text(content: Any) -> str:
    """Flatten message content (str or list of content blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b if isinstance(b, str) else b.get("text", "")
            for b in content
            if isinstance(b, (str, dict))
        )
    return "" if content is None else str(content)


def _leaf_errors(exc: BaseException) -> list[BaseException]:
    """Unwrap (nested) ExceptionGroups, e.g. from MCP TaskGroups, to the real errors."""
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for e in exc.exceptions for leaf in _leaf_errors(e)]
    return [exc]


class AgentService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.checkpointer = InMemorySaver()  # swap for a persistent saver later
        self.tool_names: list[str] = []
        self._agent = None
        self._init_lock: asyncio.Lock | None = None
        self._loop = asyncio.new_event_loop()
        threading.Thread(target=self._loop.run_forever, daemon=True, name="agent-loop").start()

    # ---- lifecycle -------------------------------------------------------
    async def _ensure_agent(self):
        if self._agent is not None:
            return self._agent
        self._init_lock = self._init_lock or asyncio.Lock()
        async with self._init_lock:
            if self._agent is None:
                s = self.settings
                # Token auth (DATABRICKS_TOKEN) when set, else local CLI profile.
                workspace_client = get_workspace_client(s)
                client = DatabricksMultiServerMCPClient([
                    DatabricksMCPServer(
                        name="genie-one",
                        url=s.genie_mcp_url,
                        workspace_client=workspace_client,
                    ),
                ])
                tools = await client.get_tools()
                self.tool_names = [t.name for t in tools]
                self._agent = create_agent(
                    ChatDatabricks(endpoint=s.model_endpoint, workspace_client=workspace_client),
                    tools=tools,
                    system_prompt=build_system_prompt(s, self.tool_names),
                    checkpointer=self.checkpointer,
                )
        return self._agent

    # ---- async API (use this from FastAPI) ---------------------------------
    async def astream(self, thread_id: str, text: str) -> AsyncIterator[Event]:
        """Run one user turn, yielding events. Conversation state is keyed by thread_id."""
        started = time.perf_counter()
        in_tok = out_tok = tool_calls = 0
        try:
            agent = await self._ensure_agent()
            async for mode, data in agent.astream(
                {"messages": [{"role": "user", "content": text}]},
                {"configurable": {"thread_id": thread_id}},
                stream_mode=["messages", "updates"],
            ):
                if mode == "messages":
                    chunk, _meta = data
                    if isinstance(chunk, AIMessageChunk) and (t := _as_text(chunk.content)):
                        yield TextDelta(t)
                elif mode == "updates" and isinstance(data, dict):
                    for update in data.values():
                        msgs = update.get("messages") if isinstance(update, dict) else None
                        for msg in msgs if isinstance(msgs, list) else []:
                            if isinstance(msg, AIMessage):
                                usage = msg.usage_metadata or {}
                                in_tok += usage.get("input_tokens", 0)
                                out_tok += usage.get("output_tokens", 0)
                                for call in msg.tool_calls:
                                    tool_calls += 1
                                    yield ToolStarted(call["id"] or "", call["name"], call["args"])
                            elif isinstance(msg, ToolMessage):
                                yield ToolFinished(
                                    msg.tool_call_id,
                                    msg.name or "tool",
                                    _as_text(msg.content)[:MAX_TOOL_OUTPUT_CHARS],
                                    msg.status != "error",
                                )
            yield RunFinished(
                thread_id=thread_id,
                model=self.settings.model_endpoint,
                latency_s=round(time.perf_counter() - started, 2),
                input_tokens=in_tok,
                output_tokens=out_tok,
                tool_calls=tool_calls,
            )
        except Exception as exc:  # surface to the UI instead of crashing the stream
            yield RunFailed("; ".join(f"{type(e).__name__}: {e}" for e in _leaf_errors(exc)))

    async def areset(self, thread_id: str) -> None:
        await self.checkpointer.adelete_thread(thread_id)

    # ---- sync bridge (use this from Streamlit) -------------------------------
    def stream(self, thread_id: str, text: str) -> Iterator[Event]:
        agen = self.astream(thread_id, text)
        try:
            while True:
                fut = asyncio.run_coroutine_threadsafe(agen.__anext__(), self._loop)
                try:
                    yield fut.result()
                except StopAsyncIteration:
                    return
        finally:  # consumer abandoned the stream (e.g. Streamlit rerun)
            asyncio.run_coroutine_threadsafe(agen.aclose(), self._loop)

    def reset(self, thread_id: str) -> None:
        asyncio.run_coroutine_threadsafe(self.areset(thread_id), self._loop).result()
