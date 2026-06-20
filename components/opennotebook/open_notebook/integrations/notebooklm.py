"""Import portable notebooklm-py bundles into Open Notebook."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator

PROVIDER = "google-notebooklm"
OPEN_NOTEBOOK_ORIGIN = "open-notebook"
SCHEMA_VERSION = 1
ImportAction = Literal["create", "update", "skip"]


def _content_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class BundleNotebookPayload(BaseModel):
    id: str
    title: str
    created_at: datetime | None = None
    modified_at: datetime | None = None

    @property
    def content_hash(self) -> str:
        return _content_hash({"title": self.title})


class BundleSourcePayload(BaseModel):
    id: str
    title: str
    kind: str
    url: str | None = None
    content: str | None = None
    created_at: datetime | None = None
    content_hash: str

    @model_validator(mode="after")
    def validate_content_hash(self) -> BundleSourcePayload:
        expected = _content_hash(
            {
                "title": self.title,
                "kind": self.kind,
                "url": self.url,
                "content": self.content,
            }
        )
        if self.content_hash != expected:
            raise ValueError(f"source {self.id!r} content_hash does not match its content")
        return self


class BundleNotePayload(BaseModel):
    id: str
    title: str
    content: str
    created_at: datetime | None = None
    content_hash: str

    @model_validator(mode="after")
    def validate_content_hash(self) -> BundleNotePayload:
        expected = _content_hash({"title": self.title, "content": self.content})
        if self.content_hash != expected:
            raise ValueError(f"note {self.id!r} content_hash does not match its content")
        return self


class NotebookBundlePayload(BaseModel):
    schema_version: Literal[1]
    origin: Literal["google-notebooklm", "open-notebook"]
    exported_at: datetime
    notebook: BundleNotebookPayload
    sources: list[BundleSourcePayload] = Field(default_factory=list)
    notes: list[BundleNotePayload] = Field(default_factory=list)


class ImportCounts(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0

    def add(self, action: ImportAction) -> None:
        if action == "create":
            self.created += 1
        elif action == "update":
            self.updated += 1
        else:
            self.skipped += 1


class BundleImportPreview(BaseModel):
    notebook_action: ImportAction
    sources: ImportCounts
    notes: ImportCounts


class BundleImportResult(BundleImportPreview):
    local_notebook_id: str
    embedding_command_ids: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ExternalMapping:
    id: str
    remote_type: str
    remote_id: str
    remote_parent_id: str | None
    local_id: str
    content_hash: str


class BundleImportStore(Protocol):
    async def get_mapping(self, remote_type: str, remote_id: str) -> ExternalMapping | None: ...

    async def save_mapping(
        self,
        *,
        remote_type: str,
        remote_id: str,
        remote_parent_id: str | None,
        local_id: str,
        content_hash: str,
    ) -> None: ...

    async def create_notebook(self, payload: BundleNotebookPayload) -> str: ...
    async def update_notebook(self, local_id: str, payload: BundleNotebookPayload) -> None: ...
    async def create_source(
        self, notebook_id: str, payload: BundleSourcePayload, *, embed: bool
    ) -> tuple[str, str | None]: ...
    async def update_source(
        self, local_id: str, payload: BundleSourcePayload, *, embed: bool
    ) -> str | None: ...
    async def create_note(
        self, notebook_id: str, payload: BundleNotePayload
    ) -> tuple[str, str | None]: ...
    async def update_note(self, local_id: str, payload: BundleNotePayload) -> str | None: ...


class OpenNotebookBundleStore:
    async def get_mapping(
        self, remote_type: str, remote_id: str
    ) -> ExternalMapping | None:
        from open_notebook.database.repository import repo_query

        rows = await repo_query(
            "SELECT * FROM external_sync_mapping "
            "WHERE provider=$provider AND remote_type=$remote_type "
            "AND remote_id=$remote_id LIMIT 1;",
            {
                "provider": PROVIDER,
                "remote_type": remote_type,
                "remote_id": remote_id,
            },
        )
        if not rows:
            return None
        row = rows[0]
        return ExternalMapping(
            id=str(row["id"]),
            remote_type=row["remote_type"],
            remote_id=row["remote_id"],
            remote_parent_id=row.get("remote_parent_id"),
            local_id=str(row["local_id"]),
            content_hash=row["content_hash"],
        )

    async def save_mapping(
        self,
        *,
        remote_type: str,
        remote_id: str,
        remote_parent_id: str | None,
        local_id: str,
        content_hash: str,
    ) -> None:
        from open_notebook.database.repository import repo_create, repo_update

        data = {
            "provider": PROVIDER,
            "remote_type": remote_type,
            "remote_id": remote_id,
            "remote_parent_id": remote_parent_id,
            "local_id": local_id,
            "content_hash": content_hash,
        }
        current = await self.get_mapping(remote_type, remote_id)
        if current:
            await repo_update("external_sync_mapping", current.id, data)
        else:
            await repo_create("external_sync_mapping", data)

    async def create_notebook(self, payload: BundleNotebookPayload) -> str:
        from open_notebook.domain.notebook import Notebook

        notebook = Notebook(name=payload.title, description="", archived=False)
        await notebook.save()
        return _saved_id(notebook.id, "notebook")

    async def update_notebook(
        self, local_id: str, payload: BundleNotebookPayload
    ) -> None:
        from open_notebook.domain.notebook import Notebook

        notebook = await Notebook.get(local_id)
        notebook.name = payload.title
        await notebook.save()

    async def create_source(
        self, notebook_id: str, payload: BundleSourcePayload, *, embed: bool
    ) -> tuple[str, str | None]:
        source = _source(payload)
        await source.save()
        source_id = _saved_id(source.id, "source")
        await source.add_to_notebook(notebook_id)
        command_id = await source.vectorize() if embed and payload.content else None
        return source_id, command_id

    async def update_source(
        self, local_id: str, payload: BundleSourcePayload, *, embed: bool
    ) -> str | None:
        from open_notebook.domain.notebook import Asset, Source

        source = await Source.get(local_id)
        source.asset = Asset(url=payload.url) if payload.url else None
        source.title = payload.title
        source.full_text = payload.content
        await source.save()
        return await source.vectorize() if embed and payload.content else None

    async def create_note(
        self, notebook_id: str, payload: BundleNotePayload
    ) -> tuple[str, str | None]:
        note = _note(payload)
        command_id = await note.save()
        note_id = _saved_id(note.id, "note")
        await note.add_to_notebook(notebook_id)
        return note_id, command_id

    async def update_note(
        self, local_id: str, payload: BundleNotePayload
    ) -> str | None:
        from open_notebook.domain.notebook import Note

        note = await Note.get(local_id)
        note.title = payload.title
        note.content = payload.content or None
        return await note.save()


def _source(payload: BundleSourcePayload, local_id: str | None = None):
    from open_notebook.domain.notebook import Asset, Source

    asset = Asset(url=payload.url) if payload.url else None
    return Source(id=local_id, asset=asset, title=payload.title, full_text=payload.content)


def _note(payload: BundleNotePayload, local_id: str | None = None):
    from open_notebook.domain.notebook import Note

    return Note(
        id=local_id,
        title=payload.title,
        note_type="human",
        content=payload.content or None,
    )


def _saved_id(value: str | None, entity: str) -> str:
    if value is None:
        raise RuntimeError(f"saved {entity} did not receive an id")
    return str(value)


class NotebookBundleImporter:
    def __init__(self, store: BundleImportStore):
        self.store = store

    async def preview(self, bundle: NotebookBundlePayload) -> BundleImportPreview:
        if bundle.origin != PROVIDER:
            raise ValueError(f"cannot import bundle with origin {bundle.origin!r}")
        notebook_mapping = await self.store.get_mapping("notebook", bundle.notebook.id)
        source_counts = ImportCounts()
        note_counts = ImportCounts()
        for source in bundle.sources:
            source_counts.add(
                _action(await self.store.get_mapping("source", source.id), source.content_hash)
            )
        for note in bundle.notes:
            note_counts.add(
                _action(await self.store.get_mapping("note", note.id), note.content_hash)
            )
        return BundleImportPreview(
            notebook_action=_action(notebook_mapping, bundle.notebook.content_hash),
            sources=source_counts,
            notes=note_counts,
        )

    async def import_bundle(
        self, bundle: NotebookBundlePayload, *, embed_sources: bool = False
    ) -> BundleImportResult:
        preview = await self.preview(bundle)
        notebook_mapping = await self.store.get_mapping("notebook", bundle.notebook.id)
        if preview.notebook_action == "create":
            notebook_id = await self.store.create_notebook(bundle.notebook)
        else:
            assert notebook_mapping is not None
            notebook_id = notebook_mapping.local_id
            if preview.notebook_action == "update":
                await self.store.update_notebook(notebook_id, bundle.notebook)
        if preview.notebook_action != "skip":
            await self.store.save_mapping(
                remote_type="notebook",
                remote_id=bundle.notebook.id,
                remote_parent_id=None,
                local_id=notebook_id,
                content_hash=bundle.notebook.content_hash,
            )

        command_ids: list[str] = []
        for source in bundle.sources:
            command_id = await self._import_source(
                notebook_id, bundle.notebook.id, source, embed_sources
            )
            if command_id:
                command_ids.append(str(command_id))
        for note in bundle.notes:
            command_id = await self._import_note(notebook_id, bundle.notebook.id, note)
            if command_id:
                command_ids.append(str(command_id))
        return BundleImportResult(
            local_notebook_id=notebook_id,
            notebook_action=preview.notebook_action,
            sources=preview.sources,
            notes=preview.notes,
            embedding_command_ids=command_ids,
        )

    async def _import_source(
        self,
        notebook_id: str,
        remote_parent_id: str,
        payload: BundleSourcePayload,
        embed: bool,
    ) -> str | None:
        mapping = await self.store.get_mapping("source", payload.id)
        action = _action(mapping, payload.content_hash)
        if action == "skip":
            return None
        if action == "create":
            local_id, command_id = await self.store.create_source(
                notebook_id, payload, embed=embed
            )
        else:
            assert mapping is not None
            local_id = mapping.local_id
            command_id = await self.store.update_source(local_id, payload, embed=embed)
        await self.store.save_mapping(
            remote_type="source",
            remote_id=payload.id,
            remote_parent_id=remote_parent_id,
            local_id=local_id,
            content_hash=payload.content_hash,
        )
        return command_id

    async def _import_note(
        self, notebook_id: str, remote_parent_id: str, payload: BundleNotePayload
    ) -> str | None:
        mapping = await self.store.get_mapping("note", payload.id)
        action = _action(mapping, payload.content_hash)
        if action == "skip":
            return None
        if action == "create":
            local_id, command_id = await self.store.create_note(notebook_id, payload)
        else:
            assert mapping is not None
            local_id = mapping.local_id
            command_id = await self.store.update_note(local_id, payload)
        await self.store.save_mapping(
            remote_type="note",
            remote_id=payload.id,
            remote_parent_id=remote_parent_id,
            local_id=local_id,
            content_hash=payload.content_hash,
        )
        return command_id


def _action(mapping: ExternalMapping | None, content_hash: str) -> ImportAction:
    if mapping is None:
        return "create"
    return "skip" if mapping.content_hash == content_hash else "update"


async def export_open_notebook_bundle(
    notebook_id: str,
    *,
    exported_at: datetime | None = None,
) -> NotebookBundlePayload:
    """Export one Open Notebook notebook using the shared portable contract."""
    from open_notebook.domain.notebook import Notebook

    notebook = await Notebook.get(notebook_id)
    sources, notes = await asyncio.gather(
        notebook.get_sources(include_full_text=True),
        notebook.get_notes(include_content=True),
    )
    bundle_sources: list[BundleSourcePayload] = []
    for source in sources:
        url = source.asset.url if source.asset else None
        kind = "url" if url else "file" if source.asset and source.asset.file_path else "text"
        values: dict[str, object] = {
            "title": source.title or "Untitled source",
            "kind": kind,
            "url": url,
            "content": source.full_text,
        }
        bundle_sources.append(
            BundleSourcePayload(
                id=str(source.id),
                created_at=source.created,
                content_hash=_content_hash(values),
                **values,
            )
        )
    bundle_notes: list[BundleNotePayload] = []
    for note in notes:
        values = {"title": note.title or "Untitled note", "content": note.content or ""}
        bundle_notes.append(
            BundleNotePayload(
                id=str(note.id),
                created_at=note.created,
                content_hash=_content_hash(values),
                **values,
            )
        )
    return NotebookBundlePayload(
        schema_version=SCHEMA_VERSION,
        origin=OPEN_NOTEBOOK_ORIGIN,
        exported_at=exported_at or datetime.now(timezone.utc),
        notebook=BundleNotebookPayload(
            id=str(notebook.id),
            title=notebook.name,
            created_at=notebook.created,
            modified_at=notebook.updated,
        ),
        sources=bundle_sources,
        notes=bundle_notes,
    )


__all__ = [
    "BundleImportPreview",
    "BundleImportResult",
    "BundleNotePayload",
    "BundleNotebookPayload",
    "BundleSourcePayload",
    "ExternalMapping",
    "ImportCounts",
    "NotebookBundleImporter",
    "NotebookBundlePayload",
    "OpenNotebookBundleStore",
    "export_open_notebook_bundle",
]
