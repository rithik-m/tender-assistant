"""Renders system_prompt.md, filling its {{placeholders}}."""

from datetime import date
from pathlib import Path
from typing import Iterable

from .config import Settings

PROMPT_PATH = Path(__file__).parent / "system_prompt.md"


def build_system_prompt(settings: Settings, tool_names: Iterable[str] = ()) -> str:
    extra_tools = [n for n in tool_names if not n.startswith("genie_")]
    values = {
        "assistant_name": settings.assistant_name,
        "company_name": settings.company_name,
        "current_date": date.today().strftime("%A, %B %d, %Y"),
        "catalog_schema": settings.catalog_schema,
        "additional_tools": ", ".join(extra_tools) or "none",
    }
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    return prompt
