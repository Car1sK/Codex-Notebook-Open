from __future__ import annotations

import asyncio

from fastmcp import Client

from notebooklm.mcp.open_notebook import create_open_notebook_server

REQUIRED_TOOLS = {
    "open_notebook_list_notebooks",
    "open_notebook_create_notebook",
    "open_notebook_list_sources",
    "open_notebook_create_text_source",
    "open_notebook_list_notes",
    "open_notebook_get_note",
    "open_notebook_create_note",
    "open_notebook_update_note",
    "open_notebook_delete_note",
}


async def main() -> None:
    async with Client(create_open_notebook_server()) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    missing = sorted(REQUIRED_TOOLS - names)
    if missing:
        raise SystemExit(f"Missing Open Notebook MCP tools: {', '.join(missing)}")
    print(f"OK: Open Notebook MCP exposes {len(REQUIRED_TOOLS)} required tools.")


if __name__ == "__main__":
    asyncio.run(main())
