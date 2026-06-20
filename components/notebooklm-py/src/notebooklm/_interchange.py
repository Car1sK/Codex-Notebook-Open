"""Notebook interchange bundle types and export orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .types import Note, Notebook, Source, SourceFulltext

__all__ = [
    "BundleNote",
    "BundleNotebook",
    "BundleSource",
    "NotebookBundle",
    "PublishBundleResult",
    "export_notebook_bundle",
    "publish_notebook_bundle",
]

SCHEMA_VERSION = 1
ORIGIN = "google-notebooklm"
SUPPORTED_ORIGINS = frozenset({ORIGIN, "open-notebook"})


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("datetime values must be ISO-8601 strings or null")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _content_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class BundleNotebook:
    """Notebook identity and timestamps carried by a bundle."""

    id: str
    title: str
    created_at: datetime | None = None
    modified_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": _isoformat(self.created_at),
            "modified_at": _isoformat(self.modified_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BundleNotebook:
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            created_at=_parse_datetime(data.get("created_at")),
            modified_at=_parse_datetime(data.get("modified_at")),
        )


@dataclass(frozen=True)
class BundleSource:
    """A source with portable indexed text and origin metadata."""

    id: str
    title: str
    kind: str
    url: str | None
    content: str | None
    created_at: datetime | None = None

    @property
    def content_hash(self) -> str:
        return _content_hash(
            {
                "title": self.title,
                "kind": self.kind,
                "url": self.url,
                "content": self.content,
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "url": self.url,
            "content": self.content,
            "created_at": _isoformat(self.created_at),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BundleSource:
        source = cls(
            id=str(data["id"]),
            title=str(data["title"]),
            kind=str(data["kind"]),
            url=str(data["url"]) if data.get("url") is not None else None,
            content=(str(data["content"]) if data.get("content") is not None else None),
            created_at=_parse_datetime(data.get("created_at")),
        )
        expected = data.get("content_hash")
        if expected is not None and expected != source.content_hash:
            raise ValueError(f"source {source.id!r} content_hash does not match its content")
        return source


@dataclass(frozen=True)
class BundleNote:
    """A portable user note."""

    id: str
    title: str
    content: str
    created_at: datetime | None = None

    @property
    def content_hash(self) -> str:
        return _content_hash({"title": self.title, "content": self.content})

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "created_at": _isoformat(self.created_at),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> BundleNote:
        note = cls(
            id=str(data["id"]),
            title=str(data["title"]),
            content=str(data["content"]),
            created_at=_parse_datetime(data.get("created_at")),
        )
        expected = data.get("content_hash")
        if expected is not None and expected != note.content_hash:
            raise ValueError(f"note {note.id!r} content_hash does not match its content")
        return note


@dataclass(frozen=True)
class NotebookBundle:
    """Portable representation of one NotebookLM notebook."""

    notebook: BundleNotebook
    sources: tuple[BundleSource, ...]
    notes: tuple[BundleNote, ...]
    exported_at: datetime
    schema_version: int = SCHEMA_VERSION
    origin: str = ORIGIN

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "origin": self.origin,
            "exported_at": _isoformat(self.exported_at),
            "notebook": self.notebook.to_dict(),
            "sources": [source.to_dict() for source in self.sources],
            "notes": [note.to_dict() for note in self.notes],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> NotebookBundle:
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"unsupported notebook bundle schema_version {version!r}; expected {SCHEMA_VERSION}"
            )
        origin = data.get("origin")
        if origin not in SUPPORTED_ORIGINS:
            raise ValueError(f"unsupported notebook bundle origin {origin!r}")

        notebook_data = data.get("notebook")
        source_data = data.get("sources")
        note_data = data.get("notes")
        if not isinstance(notebook_data, dict):
            raise ValueError("notebook must be an object")
        if not isinstance(source_data, list):
            raise ValueError("sources must be an array")
        if not isinstance(note_data, list):
            raise ValueError("notes must be an array")

        exported_at = _parse_datetime(data.get("exported_at"))
        if exported_at is None:
            raise ValueError("exported_at is required")
        return cls(
            notebook=BundleNotebook.from_dict(notebook_data),
            sources=tuple(BundleSource.from_dict(item) for item in source_data),
            notes=tuple(BundleNote.from_dict(item) for item in note_data),
            exported_at=exported_at,
            origin=str(origin),
        )

    @classmethod
    def from_json(cls, value: str) -> NotebookBundle:
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError("notebook bundle JSON must contain an object")
        return cls.from_dict(data)


class _NotebookReader(Protocol):
    async def get(self, notebook_id: str) -> Notebook: ...

    async def create(self, title: str) -> Notebook: ...


class _SourceReader(Protocol):
    async def list(self, notebook_id: str, *, strict: bool = False) -> list[Source]: ...

    async def get_fulltext(
        self,
        notebook_id: str,
        source_id: str,
        *,
        output_format: str = "text",
    ) -> SourceFulltext: ...

    async def add_text(self, notebook_id: str, title: str, content: str) -> Source: ...

    async def add_url(self, notebook_id: str, url: str) -> Source: ...


class _NoteReader(Protocol):
    async def list(self, notebook_id: str) -> list[Note]: ...

    async def create(self, notebook_id: str, title: str, content: str) -> Note: ...


class _InterchangeClient(Protocol):
    notebooks: _NotebookReader
    sources: _SourceReader
    notes: _NoteReader


async def export_notebook_bundle(
    client: _InterchangeClient,
    notebook_id: str,
    *,
    include_source_content: bool = True,
    max_concurrency: int = 4,
    exported_at: datetime | None = None,
) -> NotebookBundle:
    """Export one notebook into the versioned interchange contract.

    Source order is preserved. Fulltext reads are bounded so callers can export
    useful notebooks without serial latency or an unbounded request burst.
    """
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be at least 1")

    notebook, sources, notes = await asyncio.gather(
        client.notebooks.get(notebook_id),
        client.sources.list(notebook_id, strict=True),
        client.notes.list(notebook_id),
    )
    async def export_source(source: Source) -> BundleSource:
        fulltext: SourceFulltext | None = None
        if include_source_content:
            fulltext = await client.sources.get_fulltext(notebook_id, source.id)
        return BundleSource(
            id=source.id,
            title=(fulltext.title if fulltext else source.title) or "Untitled source",
            kind=(fulltext.kind.value if fulltext else source.kind.value),
            url=(fulltext.url if fulltext else source.url),
            content=fulltext.content if fulltext else None,
            created_at=source.created_at,
        )

    bundle_sources: list[BundleSource] = []
    for offset in range(0, len(sources), max_concurrency):
        batch = sources[offset : offset + max_concurrency]
        bundle_sources.extend(await asyncio.gather(*(export_source(source) for source in batch)))
    return NotebookBundle(
        notebook=BundleNotebook(
            id=notebook.id,
            title=notebook.title,
            created_at=notebook.created_at,
            modified_at=notebook.modified_at,
        ),
        sources=tuple(bundle_sources),
        notes=tuple(
            BundleNote(
                id=note.id,
                title=note.title,
                content=note.content,
                created_at=note.created_at,
            )
            for note in notes
        ),
        exported_at=exported_at or datetime.now(timezone.utc),
    )


@dataclass(frozen=True)
class PublishBundleResult:
    """Identifiers created while publishing a bundle to NotebookLM."""

    notebook_id: str
    source_ids: tuple[str, ...]
    note_ids: tuple[str, ...]


async def publish_notebook_bundle(
    client: _InterchangeClient,
    bundle: NotebookBundle,
    *,
    title: str | None = None,
) -> PublishBundleResult:
    """Publish a portable bundle as a new NotebookLM notebook.

    Source snapshots are preferred over URLs so Open Notebook edits are
    preserved. A URL is used only when the bundle has no non-blank content.
    """
    for source in bundle.sources:
        if not (source.content and source.content.strip()) and not source.url:
            raise ValueError(f"source {source.id!r} has neither content nor a URL")

    notebook = await client.notebooks.create(title or bundle.notebook.title)
    source_ids: list[str] = []
    for source in bundle.sources:
        if source.content and source.content.strip():
            created_source = await client.sources.add_text(
                notebook.id, source.title, source.content
            )
        else:
            assert source.url is not None
            created_source = await client.sources.add_url(notebook.id, source.url)
        source_ids.append(created_source.id)

    note_ids: list[str] = []
    for note in bundle.notes:
        created_note = await client.notes.create(
            notebook.id, note.title, note.content
        )
        note_ids.append(created_note.id)

    return PublishBundleResult(
        notebook_id=notebook.id,
        source_ids=tuple(source_ids),
        note_ids=tuple(note_ids),
    )
