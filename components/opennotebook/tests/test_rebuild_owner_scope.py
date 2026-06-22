from __future__ import annotations

import asyncio
from typing import Any

from api.models import RebuildRequest
from api.routers import embedding_rebuild
from commands import embedding_commands
from open_notebook.auth_context import AuthenticatedUser


def test_rebuild_endpoint_estimates_and_submits_current_owner_only(
    monkeypatch,
) -> None:
    repo_calls: list[tuple[str, dict[str, Any] | None]] = []
    submitted_args: dict[str, Any] = {}

    async def fake_repo_query(
        query: str, vars: dict[str, Any] | None = None
    ) -> list[dict[str, int]]:
        repo_calls.append((query, vars))
        return [{"count": 2}]

    async def fake_submit_command_job(
        module_name: str,
        command_name: str,
        command_args: dict[str, Any],
    ) -> str:
        submitted_args.update(
            {
                "module_name": module_name,
                "command_name": command_name,
                "command_args": command_args,
            }
        )
        return "command:rebuild"

    monkeypatch.setattr(embedding_rebuild, "repo_query", fake_repo_query)
    monkeypatch.setattr(
        embedding_rebuild.CommandService,
        "submit_command_job",
        fake_submit_command_job,
    )

    response = asyncio.run(
        embedding_rebuild.start_rebuild(
            RebuildRequest(
                mode="all",
                include_sources=True,
                include_notes=True,
                include_insights=True,
            ),
            current_user=AuthenticatedUser(username="alice", owner_id="owner_a"),
        )
    )

    assert response.command_id == "command:rebuild"
    assert response.total_items == 6
    assert len(repo_calls) == 3
    assert all(call[1] == {"owner_id": "owner_a", "owner_is_default": False} for call in repo_calls)
    assert all("$owner_id" in call[0] for call in repo_calls)
    assert submitted_args == {
        "module_name": "open_notebook",
        "command_name": "rebuild_embeddings",
        "command_args": {
            "mode": "all",
            "include_sources": True,
            "include_notes": True,
            "include_insights": True,
            "owner_id": "owner_a",
        },
    }


def test_rebuild_command_collects_items_for_requested_owner_only(
    monkeypatch,
) -> None:
    repo_calls: list[tuple[str, dict[str, Any] | None]] = []

    async def fake_repo_query(
        query: str, vars: dict[str, Any] | None = None
    ) -> list[dict[str, str]]:
        repo_calls.append((query, vars))
        if "FROM source_insight" in query:
            return [{"id": "source_insight:one"}]
        if "FROM note" in query:
            return [{"id": "note:one"}]
        return [{"id": "source:one"}]

    monkeypatch.setattr(embedding_commands, "repo_query", fake_repo_query)

    items = asyncio.run(
        embedding_commands.collect_items_for_rebuild(
            mode="all",
            include_sources=True,
            include_notes=True,
            include_insights=True,
            owner_id="owner_a",
        )
    )

    assert items == {
        "sources": ["source:one"],
        "notes": ["note:one"],
        "insights": ["source_insight:one"],
    }
    assert len(repo_calls) == 3
    assert all(call[1] == {"owner_id": "owner_a", "owner_is_default": False} for call in repo_calls)
    assert "owner_id = $owner_id" in repo_calls[0][0]
    assert "owner_id = $owner_id" in repo_calls[1][0]
    assert "source.owner_id = $owner_id" in repo_calls[2][0]
