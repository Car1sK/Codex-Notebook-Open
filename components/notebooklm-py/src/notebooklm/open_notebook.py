"""Typed client for managing notes in an Open Notebook server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import httpx

__all__ = [
    "OpenNotebookAPIError",
    "OpenNotebookClient",
    "OpenNotebookNote",
    "OpenNotebookNotebook",
    "OpenNotebookSource",
]

DEFAULT_OPEN_NOTEBOOK_URL = "http://localhost:5055"
DEFAULT_OPEN_NOTEBOOK_PASSWORD = "open-notebook-change-me"


class OpenNotebookAPIError(RuntimeError):
    """An Open Notebook API request failed."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Open Notebook API returned {status_code}: {detail}")


@dataclass(frozen=True)
class OpenNotebookNotebook:
    id: str
    name: str
    description: str
    archived: bool
    created: str
    updated: str
    source_count: int
    note_count: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OpenNotebookNotebook:
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            description=str(value.get("description", "")),
            archived=bool(value.get("archived", False)),
            created=str(value.get("created", "")),
            updated=str(value.get("updated", "")),
            source_count=int(value.get("source_count", 0)),
            note_count=int(value.get("note_count", 0)),
        )


@dataclass(frozen=True)
class OpenNotebookSource:
    """A source imported into an Open Notebook notebook."""

    id: str
    title: str
    content: str | None = None
    created: str = ""
    updated: str = ""
    command_id: str | None = None
    status: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OpenNotebookSource:
        # API may return text content under "content" or "full_text"
        content: str | None = None
        raw = value.get("content")
        if raw is not None:
            content = str(raw)
        else:
            raw = value.get("full_text")
            if raw is not None:
                content = str(raw)
        return cls(
            id=str(value["id"]),
            title=str(value.get("title", "")),
            content=content,
            created=str(value.get("created", "")),
            updated=str(value.get("updated", "")),
            command_id=(
                str(value["command_id"])
                if value.get("command_id") is not None
                else None
            ),
            status=(
                str(value["status"]) if value.get("status") is not None else None
            ),
        )


@dataclass(frozen=True)
class OpenNotebookNote:
    id: str
    title: str | None
    content: str | None
    note_type: str | None
    created: str
    updated: str
    command_id: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OpenNotebookNote:
        return cls(
            id=str(value["id"]),
            title=str(value["title"]) if value.get("title") is not None else None,
            content=(
                str(value["content"]) if value.get("content") is not None else None
            ),
            note_type=(
                str(value["note_type"])
                if value.get("note_type") is not None
                else None
            ),
            created=str(value.get("created", "")),
            updated=str(value.get("updated", "")),
            command_id=(
                str(value["command_id"])
                if value.get("command_id") is not None
                else None
            ),
        )


class OpenNotebookClient:
    """Small async HTTP client for Open Notebook notebook and note operations."""

    def __init__(
        self,
        base_url: str,
        password: str,
        *,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not password:
            raise ValueError("Open Notebook password must not be empty")
        normalized = base_url.rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("Open Notebook URL must start with http:// or https://")
        self._client = httpx.AsyncClient(
            base_url=f"{normalized}/api",
            headers={"Authorization": f"Bearer {password}"},
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_env(cls) -> OpenNotebookClient:
        return cls(
            os.environ.get("OPEN_NOTEBOOK_URL", DEFAULT_OPEN_NOTEBOOK_URL),
            os.environ.get(
                "OPEN_NOTEBOOK_PASSWORD", DEFAULT_OPEN_NOTEBOOK_PASSWORD
            ),
        )

    async def __aenter__(self) -> OpenNotebookClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def list_notebooks(self) -> list[OpenNotebookNotebook]:
        value = await self._request("GET", "/notebooks")
        return [OpenNotebookNotebook.from_dict(item) for item in _list_payload(value)]

    async def create_notebook(
        self, name: str, *, description: str = ""
    ) -> OpenNotebookNotebook:
        value = await self._request(
            "POST", "/notebooks", json={"name": name, "description": description}
        )
        return OpenNotebookNotebook.from_dict(_object_payload(value))

    async def list_notes(self, notebook_id: str | None = None) -> list[OpenNotebookNote]:
        params = {"notebook_id": notebook_id} if notebook_id else None
        value = await self._request("GET", "/notes", params=params)
        return [OpenNotebookNote.from_dict(item) for item in _list_payload(value)]

    async def list_sources(
        self, notebook_id: str | None = None
    ) -> list[OpenNotebookSource]:
        """List sources, optionally filtered by notebook ID."""
        params = {"notebook_id": notebook_id} if notebook_id else None
        value = await self._request("GET", "/sources", params=params)
        return [OpenNotebookSource.from_dict(item) for item in _list_payload(value)]

    async def create_text_source(
        self,
        content: str,
        *,
        title: str | None = None,
        notebook_id: str | None = None,
        embed: bool = False,
        async_processing: bool = True,
    ) -> OpenNotebookSource:
        """Import text source material into Open Notebook.

        This imports source material (e.g. an article, document text) for
        later note generation — it does not create final user notes directly.
        """
        payload: dict[str, Any] = {
            "type": "text",
            "title": title or "",
            "content": content,
            "embed": embed,
            "async_processing": async_processing,
            "transformations": [],
        }
        if notebook_id:
            payload["notebooks"] = [notebook_id]
        value = await self._request("POST", "/sources/json", json=payload)
        return OpenNotebookSource.from_dict(_object_payload(value))

    async def get_note(self, note_id: str) -> OpenNotebookNote:
        value = await self._request("GET", f"/notes/{note_id}")
        return OpenNotebookNote.from_dict(_object_payload(value))

    async def create_note(
        self,
        content: str,
        *,
        title: str | None = None,
        notebook_id: str | None = None,
        note_type: Literal["human", "ai"] = "human",
    ) -> OpenNotebookNote:
        value = await self._request(
            "POST",
            "/notes",
            json={
                "title": title,
                "content": content,
                "note_type": note_type,
                "notebook_id": notebook_id,
            },
        )
        return OpenNotebookNote.from_dict(_object_payload(value))

    async def update_note(
        self,
        note_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        note_type: Literal["human", "ai"] | None = None,
    ) -> OpenNotebookNote:
        changes = {
            key: value
            for key, value in {
                "title": title,
                "content": content,
                "note_type": note_type,
            }.items()
            if value is not None
        }
        if not changes:
            raise ValueError("at least one note field must be provided")
        value = await self._request("PUT", f"/notes/{note_id}", json=changes)
        return OpenNotebookNote.from_dict(_object_payload(value))

    async def delete_note(self, note_id: str) -> None:
        await self._request("DELETE", f"/notes/{note_id}")

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._client.request(method, path, **kwargs)
        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                detail = response.text or response.reason_phrase
            else:
                detail = str(payload.get("detail", payload)) if isinstance(payload, dict) else str(payload)
            raise OpenNotebookAPIError(response.status_code, detail)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


def _list_payload(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("Open Notebook API returned an invalid list payload")
    return value


def _object_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Open Notebook API returned an invalid object payload")
    return value
