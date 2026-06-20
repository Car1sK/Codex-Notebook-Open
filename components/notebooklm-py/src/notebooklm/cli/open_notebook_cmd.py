"""Direct Open Notebook note-management CLI commands."""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import asdict
from typing import Any

import click

from ..open_notebook import OpenNotebookClient
from .error_handler import handle_errors
from .options import json_option
from .rendering import cli_print, json_output_response
from .runtime import run_async


def _execute(operation: Awaitable[Any], *, json_output: bool) -> Any:
    with handle_errors(json_output=json_output):
        return run_async(operation)
    raise AssertionError("unreachable")  # pragma: no cover


@click.group("open-notebook")
def open_notebook():
    """Manage notes on an Open Notebook server."""


@open_notebook.command("notebooks")
@json_option
def list_notebooks(json_output: bool) -> None:
    """List Open Notebook notebooks."""

    async def _run():
        async with OpenNotebookClient.from_env() as client:
            return await client.list_notebooks()

    notebooks = _execute(_run(), json_output=json_output)
    payload = {"notebooks": [asdict(item) for item in notebooks]}
    if json_output:
        json_output_response(payload)
        return
    for notebook in notebooks:
        cli_print(f"{notebook.id}  {notebook.name}  ({notebook.note_count} notes)")


@open_notebook.command("notebook-create")
@click.argument("name")
@click.option("--description", default="")
@json_option
def create_notebook(name: str, description: str, json_output: bool) -> None:
    """Create an Open Notebook notebook."""

    async def _run():
        async with OpenNotebookClient.from_env() as client:
            return await client.create_notebook(name, description=description)

    notebook = _execute(_run(), json_output=json_output)
    if json_output:
        json_output_response({"notebook": asdict(notebook)})
        return
    cli_print(f"[green]Created Open Notebook notebook:[/green] {notebook.id}")


@open_notebook.command("notes")
@click.option("--notebook-id", default=None, help="Filter notes by notebook ID.")
@json_option
def list_notes(notebook_id: str | None, json_output: bool) -> None:
    """List Open Notebook notes."""

    async def _run():
        async with OpenNotebookClient.from_env() as client:
            return await client.list_notes(notebook_id)

    notes = _execute(_run(), json_output=json_output)
    payload = {"notes": [asdict(item) for item in notes]}
    if json_output:
        json_output_response(payload)
        return
    for note in notes:
        cli_print(f"{note.id}  {note.title or '(untitled)'}")


@open_notebook.command("note-get")
@click.argument("note_id")
@json_option
def get_note(note_id: str, json_output: bool) -> None:
    """Get one Open Notebook note."""

    async def _run():
        async with OpenNotebookClient.from_env() as client:
            return await client.get_note(note_id)

    note = _execute(_run(), json_output=json_output)
    if json_output:
        json_output_response({"note": asdict(note)})
        return
    cli_print(f"[bold]{note.title or '(untitled)'}[/bold]\n{note.content or ''}")


@open_notebook.command("note-create")
@click.argument("content")
@click.option("--title", default=None)
@click.option("--notebook-id", default=None)
@json_option
def create_note(
    content: str,
    title: str | None,
    notebook_id: str | None,
    json_output: bool,
) -> None:
    """Create an Open Notebook note."""

    async def _run():
        async with OpenNotebookClient.from_env() as client:
            return await client.create_note(
                content, title=title, notebook_id=notebook_id
            )

    note = _execute(_run(), json_output=json_output)
    if json_output:
        json_output_response({"note": asdict(note)})
        return
    cli_print(f"[green]Created Open Notebook note:[/green] {note.id}")


@open_notebook.command("note-update")
@click.argument("note_id")
@click.option("--title", default=None)
@click.option("--content", default=None)
@json_option
def update_note(
    note_id: str,
    title: str | None,
    content: str | None,
    json_output: bool,
) -> None:
    """Update an Open Notebook note title or content."""

    async def _run():
        async with OpenNotebookClient.from_env() as client:
            return await client.update_note(note_id, title=title, content=content)

    note = _execute(_run(), json_output=json_output)
    if json_output:
        json_output_response({"note": asdict(note)})
        return
    cli_print(f"[green]Updated Open Notebook note:[/green] {note.id}")


@open_notebook.command("note-delete")
@click.argument("note_id")
@click.option("--yes", "confirmed", is_flag=True, help="Confirm irreversible deletion.")
@json_option
def delete_note(note_id: str, confirmed: bool, json_output: bool) -> None:
    """Delete an Open Notebook note."""
    if not confirmed:
        if json_output:
            raise click.UsageError(  # cli-input-validation: JSON deletion requires explicit confirmation
                "--yes is required with --json"
            )
        confirmed = click.confirm(f"Delete Open Notebook note {note_id}?")
    if not confirmed:
        return

    async def _run():
        async with OpenNotebookClient.from_env() as client:
            await client.delete_note(note_id)

    _execute(_run(), json_output=json_output)
    payload = {"status": "deleted", "note_id": note_id}
    if json_output:
        json_output_response(payload)
        return
    cli_print(f"[green]Deleted Open Notebook note:[/green] {note_id}")


@open_notebook.command("sources")
@click.option("--notebook-id", default=None, help="Filter sources by notebook ID.")
@json_option
def list_sources(notebook_id: str | None, json_output: bool) -> None:
    """List Open Notebook sources (imported source material)."""

    async def _run():
        async with OpenNotebookClient.from_env() as client:
            return await client.list_sources(notebook_id)

    sources = _execute(_run(), json_output=json_output)
    payload = {"sources": [asdict(item) for item in sources]}
    if json_output:
        json_output_response(payload)
        return
    for source in sources:
        cli_print(f"{source.id}  {source.title}")


@open_notebook.command("source-create-text")
@click.argument("content")
@click.option("--title", default=None)
@click.option("--notebook-id", default=None)
@click.option("--embed/--no-embed", default=False)
@click.option("--async-processing/--sync-processing", default=True)
@json_option
def create_text_source(
    content: str,
    title: str | None,
    notebook_id: str | None,
    embed: bool,
    async_processing: bool,
    json_output: bool,
) -> None:
    """Import text source material into Open Notebook (not a user note)."""

    async def _run():
        async with OpenNotebookClient.from_env() as client:
            return await client.create_text_source(
                content,
                title=title,
                notebook_id=notebook_id,
                embed=embed,
                async_processing=async_processing,
            )

    source = _execute(_run(), json_output=json_output)
    if json_output:
        json_output_response({"source": asdict(source)})
        return
    cli_print(f"[green]Created Open Notebook source:[/green] {source.id}")


__all__ = ["open_notebook"]
