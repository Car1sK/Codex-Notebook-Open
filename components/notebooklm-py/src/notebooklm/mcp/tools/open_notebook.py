"""MCP tools for direct Open Notebook note management."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ...open_notebook import OpenNotebookClient
from .._confirm import DESTRUCTIVE, READ_ONLY, needs_confirmation


def register(mcp: Any) -> None:
    """Register Open Notebook tools on the NotebookLM MCP server."""

    @mcp.tool(annotations=READ_ONLY)
    async def open_notebook_list_notebooks() -> dict[str, Any]:
        """List notebooks from the configured Open Notebook server."""
        async with OpenNotebookClient.from_env() as client:
            notebooks = await client.list_notebooks()
        return {"notebooks": [asdict(item) for item in notebooks]}

    @mcp.tool
    async def open_notebook_create_notebook(
        name: str,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new Open Notebook notebook."""
        async with OpenNotebookClient.from_env() as client:
            notebook = await client.create_notebook(
                name, description=description
            )
        return {"notebook": asdict(notebook), "created": True}

    @mcp.tool(annotations=READ_ONLY)
    async def open_notebook_list_notes(
        notebook_id: str | None = None,
    ) -> dict[str, Any]:
        """List Open Notebook notes, optionally filtered by notebook ID."""
        async with OpenNotebookClient.from_env() as client:
            notes = await client.list_notes(notebook_id)
        return {"notes": [asdict(item) for item in notes]}

    @mcp.tool(annotations=READ_ONLY)
    async def open_notebook_get_note(note_id: str) -> dict[str, Any]:
        """Read one Open Notebook note by ID."""
        async with OpenNotebookClient.from_env() as client:
            note = await client.get_note(note_id)
        return {"note": asdict(note)}

    @mcp.tool(annotations=READ_ONLY)
    async def open_notebook_list_sources(
        notebook_id: str | None = None,
    ) -> dict[str, Any]:
        """List imported Open Notebook source material, optionally filtered by notebook ID."""
        async with OpenNotebookClient.from_env() as client:
            sources = await client.list_sources(notebook_id)
        return {"sources": [asdict(item) for item in sources]}

    @mcp.tool
    async def open_notebook_create_text_source(
        content: str,
        title: str | None = None,
        notebook_id: str | None = None,
        embed: bool = False,
        async_processing: bool = True,
    ) -> dict[str, Any]:
        """Import text source material into Open Notebook; this does not create final user notes."""
        async with OpenNotebookClient.from_env() as client:
            source = await client.create_text_source(
                content,
                title=title,
                notebook_id=notebook_id,
                embed=embed,
                async_processing=async_processing,
            )
        return {"source": asdict(source), "created": True}

    @mcp.tool
    async def open_notebook_create_note(
        content: str,
        title: str | None = None,
        notebook_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a note, optionally attaching it to an Open Notebook notebook."""
        async with OpenNotebookClient.from_env() as client:
            note = await client.create_note(
                content, title=title, notebook_id=notebook_id
            )
        return {"note": asdict(note), "created": True}

    @mcp.tool
    async def open_notebook_update_note(
        note_id: str,
        title: str | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        """Update an Open Notebook note title or content."""
        async with OpenNotebookClient.from_env() as client:
            note = await client.update_note(note_id, title=title, content=content)
        return {"note": asdict(note), "status": "updated"}

    @mcp.tool(annotations=DESTRUCTIVE)
    async def open_notebook_delete_note(
        note_id: str,
        confirm: bool = False,
    ) -> dict[str, Any]:
        """Delete an Open Notebook note using two-step confirmation."""
        async with OpenNotebookClient.from_env() as client:
            if not confirm:
                note = await client.get_note(note_id)
                return needs_confirmation(
                    {
                        "action": "delete_open_notebook_note",
                        "note_id": note.id,
                        "title": note.title,
                    }
                )
            await client.delete_note(note_id)
        return {"status": "deleted", "note_id": note_id}


__all__ = ["register"]
