"""Runtime configuration, read once from the environment / .env."""

import os
from dataclasses import dataclass
from functools import lru_cache

from databricks.sdk import WorkspaceClient
from dotenv import find_dotenv, load_dotenv


@dataclass(frozen=True)
class Settings:
    workspace_host: str
    workspace_id: str
    databricks_profile: str
    databricks_token: str | None  # personal access token or service-principal token
    model_endpoint: str
    assistant_name: str
    company_name: str
    catalog_schema: str

    @property
    def genie_mcp_url(self) -> str:
        return (
            f"{self.workspace_host}/ai-gateway/mcp-services/system.ai.genie_one_mcp"
            f"?o={self.workspace_id}"
        )


def get_workspace_client(settings: Settings | None = None) -> WorkspaceClient:
    """Databricks client for deployments: authenticates with an access token.

    Uses DATABRICKS_TOKEN against WORKSPACE_HOST, so no CLI login or personal
    profile is needed on the host machine. If DATABRICKS_TOKEN is unset, falls
    back to the local CLI profile (dev only).
    """
    s = settings or get_settings()
    if s.databricks_token:
        return WorkspaceClient(host=s.workspace_host, token=s.databricks_token)
    # return WorkspaceClient(profile=s.databricks_profile)


@lru_cache
def get_settings() -> Settings:
    load_dotenv(find_dotenv(usecwd=True))
    env = os.environ
    return Settings(
        workspace_host=env["WORKSPACE_HOST"].rstrip("/"),
        workspace_id=env["WORKSPACE_ID"],
        databricks_profile=env.get("DATABRICKS_PROFILE", "doperation01"),
        databricks_token=env.get("DATABRICKS_TOKEN") or None,
        model_endpoint=env.get("MODEL_ENDPOINT", "databricks-claude-sonnet-4-5"),
        assistant_name=env.get("ASSISTANT_NAME", "Tender Assistant"),
        company_name=env.get("COMPANY_NAME", "the company"),
        catalog_schema=env.get("CATALOG_SCHEMA", "hive_metastore.<all schema>"),
    )
