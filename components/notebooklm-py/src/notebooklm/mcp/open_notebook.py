"""Standalone Open Notebook MCP server without Google authentication."""

from __future__ import annotations

from fastmcp import FastMCP

from .tools import open_notebook as open_notebook_tools

__all__ = ["create_open_notebook_server", "main"]


def create_open_notebook_server() -> FastMCP:
    """Build the Open Notebook-only MCP server."""
    server = FastMCP(
        name="open-notebook",
        instructions=(
            "Manage notes on the configured Open Notebook server. "
            "Use list tools to discover notebook and note IDs. "
            "Use open_notebook_create_notebook when the user asks for a new notebook. "
            "Deletion requires confirm=true."
        ),
    )
    open_notebook_tools.register(server)
    return server


def main() -> None:
    """Run the Open Notebook-only MCP server over stdio."""
    create_open_notebook_server().run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
