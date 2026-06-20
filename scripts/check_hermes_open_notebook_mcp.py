from __future__ import annotations

import json
import os
from pathlib import Path


if "HERMES_HOME" not in os.environ:
    os.environ["HERMES_HOME"] = str(Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "hermes")

from tools.mcp_tool import discover_mcp_tools, shutdown_mcp_servers
from tools.registry import registry


REQUIRED_TOOLS = {
    "mcp_open_notebook_open_notebook_list_notebooks",
    "mcp_open_notebook_open_notebook_create_notebook",
    "mcp_open_notebook_open_notebook_list_sources",
    "mcp_open_notebook_open_notebook_create_text_source",
    "mcp_open_notebook_open_notebook_list_notes",
    "mcp_open_notebook_open_notebook_get_note",
    "mcp_open_notebook_open_notebook_create_note",
    "mcp_open_notebook_open_notebook_update_note",
    "mcp_open_notebook_open_notebook_delete_note",
}


def call_structured(tool_name: str) -> dict:
    raw = registry.dispatch(tool_name, {})
    payload = json.loads(raw)
    structured = payload.get("structuredContent")
    if not isinstance(structured, dict):
        raise SystemExit(f"Hermes MCP tool {tool_name} returned no structured content")
    return structured


def main() -> None:
    registered = set(discover_mcp_tools())
    missing = sorted(REQUIRED_TOOLS - registered)
    if missing:
        raise SystemExit(f"Missing Hermes MCP tools: {', '.join(missing)}")

    notebooks = call_structured("mcp_open_notebook_open_notebook_list_notebooks")
    sources = call_structured("mcp_open_notebook_open_notebook_list_sources")
    if "notebooks" not in notebooks:
        raise SystemExit("Hermes MCP notebook list returned no notebooks key")
    if "sources" not in sources:
        raise SystemExit("Hermes MCP source list returned no sources key")
    print(
        f"OK: Hermes MCP registered {len(REQUIRED_TOOLS)} Open Notebook tools and can read "
        f"{len(notebooks['notebooks'])} notebook(s), {len(sources['sources'])} source(s)."
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        shutdown_mcp_servers()
