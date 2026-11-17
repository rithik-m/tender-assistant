# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Python 3.13 project managed with `uv`. A LangChain/LangGraph agent answers business data questions through Databricks Genie (MCP), with a Streamlit chat UI as a temporary prototype front end. No tests, linter config, or git repo yet.

## Commands

```
uv sync --inexact                                   # install deps (--inexact avoids removing locked .venv files on Windows)
uv run streamlit run src/tender_assistant/ui/app.py # run the chat UI (from project root, so .env is found)
databricks auth login --host <host> --profile <profile>   # one-time local auth
```

## Architecture (`src/tender_assistant/`, installed editable via hatchling)

- `config.py`: `Settings` from `.env`/environment. Required: `WORKSPACE_HOST`, `WORKSPACE_ID`. Optional: `DATABRICKS_TOKEN` (access token; when set, `get_workspace_client()` authenticates with it against `WORKSPACE_HOST` and no CLI is needed, which is the deployment mode), `DATABRICKS_PROFILE` (CLI-profile fallback for local dev, default `doperation01`), `MODEL_ENDPOINT`, `ASSISTANT_NAME`, `COMPANY_NAME`, `CATALOG_SCHEMA`.
- `prompt.py` + `system_prompt.md`: the system prompt, with `{{placeholders}}` filled at startup. Edit the prompt in the .md file.
- `events.py`: UI-agnostic event dataclasses (`TextDelta`, `ToolStarted`, `ToolFinished`, `RunFinished`, `RunFailed`) with `to_dict()`. This is the contract between agent and any front end.
- `agent.py`: `AgentService` builds the MCP client, `create_agent` and an `InMemorySaver` lazily on first message. It runs on its own background event loop. `astream(thread_id, text)` is the async API to use from a future FastAPI endpoint. `stream()` is the sync bridge for Streamlit. Conversation context is keyed by `thread_id` in the checkpointer.
- `ui/`: `app.py` is the Streamlit entry point. `sessions.py` holds `ChatSession`/`Message` (messages are ordered parts: text, tool steps, errors) and a `SessionStore` over `st.session_state`. `components.py` has the rendering helpers and CSS. The `AgentService` is shared across browser sessions via `st.cache_resource`.

## Gotchas

- The checkpointer is in-memory, so chats and agent context are lost when the process restarts. UI sessions live in `st.session_state` and are lost on browser refresh (cookies and persistence are intentionally deferred).
- The system prompt mentions web search and Atlassian tools, but only the Genie MCP server is connected.
- `.env` holds workspace config. Never print or commit its values.
