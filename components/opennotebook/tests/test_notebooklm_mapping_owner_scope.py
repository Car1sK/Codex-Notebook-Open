from __future__ import annotations

import asyncio
from typing import Any

import pytest

from open_notebook.auth_context import (
    AuthenticatedUser,
    reset_current_user,
    set_current_user,
)
from open_notebook.database import repository
from open_notebook.integrations.notebooklm import OpenNotebookBundleStore


def test_bundle_mapping_lookup_is_scoped_to_current_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any] | None]] = []

    async def fake_repo_query(
        query: str, vars: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        calls.append((query, vars))
        return []

    monkeypatch.setattr(repository, "repo_query", fake_repo_query)
    store = OpenNotebookBundleStore()

    token = set_current_user(AuthenticatedUser(username="alice", owner_id="owner_a"))
    try:
        result = asyncio.run(store.get_mapping("notebook", "remote-1"))
    finally:
        reset_current_user(token)

    assert result is None
    assert calls == [
        (
            "SELECT * FROM external_sync_mapping "
            "WHERE provider=$provider AND remote_type=$remote_type "
            "AND remote_id=$remote_id AND owner_id=$owner_id LIMIT 1;",
            {
                "provider": "google-notebooklm",
                "remote_type": "notebook",
                "remote_id": "remote-1",
                "owner_id": "owner_a",
            },
        )
    ]


def test_bundle_mapping_save_writes_current_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[tuple[str, dict[str, Any]]] = []

    async def fake_repo_query(
        query: str, vars: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return []

    async def fake_repo_create(table: str, data: dict[str, Any]) -> dict[str, Any]:
        created.append((table, data))
        return data

    monkeypatch.setattr(repository, "repo_query", fake_repo_query)
    monkeypatch.setattr(repository, "repo_create", fake_repo_create)
    store = OpenNotebookBundleStore()

    token = set_current_user(AuthenticatedUser(username="bob", owner_id="owner_b"))
    try:
        asyncio.run(
            store.save_mapping(
                remote_type="source",
                remote_id="remote-source",
                remote_parent_id="remote-notebook",
                local_id="source:local",
                content_hash="hash",
            )
        )
    finally:
        reset_current_user(token)

    assert created == [
        (
            "external_sync_mapping",
            {
                "provider": "google-notebooklm",
                "owner_id": "owner_b",
                "remote_type": "source",
                "remote_id": "remote-source",
                "remote_parent_id": "remote-notebook",
                "local_id": "source:local",
                "content_hash": "hash",
            },
        )
    ]
