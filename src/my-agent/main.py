import asyncio
import os
from datetime import date
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from databricks.sdk import WorkspaceClient
from databricks_langchain import (
    ChatDatabricks,
    DatabricksMCPServer,
    DatabricksMultiServerMCPClient,
)
from langchain.agents import create_agent


load_dotenv(find_dotenv(usecwd=True))

PROMPT_PATH = Path(__file__).parent / "system_prompt.md"

WORKSPACE_HOST = os.environ["WORKSPACE_HOST"]
WORKSPACE_ID = os.environ["WORKSPACE_ID"]
GENIE_MCP_URL = (
    f"{WORKSPACE_HOST}/ai-gateway/mcp-services/system.ai.genie_one_mcp"
    f"?o={WORKSPACE_ID}"
)


# --- Auth option A: your own credentials (local dev) ---
# Run first: databricks auth login --host <host> --profile DEFAULT
workspace_client = WorkspaceClient(profile="doperation01")

# --- Auth option B: service principal (OAuth M2M, for automation) ---
# workspace_client = WorkspaceClient(
#     host=WORKSPACE_HOST,
#     client_id="<sp-application-id>",
#     client_secret="<sp-oauth-secret>",   # load from a secret store / env var
# )


def build_system_prompt(tools: list = []) -> str:
    """Render system_prompt.md, filling its {{placeholders}}."""
    extra_tools = [t.name for t in tools if not t.name.startswith("genie_")]
    values = {
        "assistant_name": os.getenv("ASSISTANT_NAME", "Tender Assistant"),
        "company_name": os.getenv("COMPANY_NAME", "the company"),
        "current_date": date.today().strftime("%A, %B %d, %Y"),
        "catalog_schema": os.getenv("CATALOG_SCHEMA", "hive_metastore.<all schema>"),
        "additional_tools": ", ".join(extra_tools) or "none",
    }
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    return prompt


async def main():
    client = DatabricksMultiServerMCPClient([
        DatabricksMCPServer(
            name="genie-one",
            url=GENIE_MCP_URL,
            workspace_client=workspace_client,
        ),
    ])

    tools = await client.get_tools()
    print("Loaded tools:", [t.name for t in tools])

    agent = create_agent(
        ChatDatabricks(endpoint="databricks-claude-sonnet-4-5"),
        tools=tools,
        system_prompt=build_system_prompt(tools),
    )

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Hi, I would like to see the pricing focal list for every trade who is responsible for making pricing decisions."}]}
    )
    for m in result["messages"]:
        m.pretty_print()

asyncio.run(main())
