from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from fastapi import HTTPException

from api.models import EmbedRequest
from api.routers import embedding, insights
from open_notebook.auth_context import AuthenticatedUser
from open_notebook.domain.notebook import Source


def test_async_embed_rejects_cross_owner_source_before_queueing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_embedding_model() -> object:
        return object()

    async def fake_source_get(source_id: str) -> Source:
        assert source_id == "source:private"
        return Source(id=source_id, owner_id="owner_b", title="Private")

    async def fail_submit_command_job(*_args, **_kwargs) -> str:
        raise AssertionError("cross-owner embed must not be queued")

    monkeypatch.setattr(
        embedding.model_manager, "get_embedding_model", fake_embedding_model
    )
    monkeypatch.setattr(embedding.Source, "get", fake_source_get)
    monkeypatch.setattr(
        embedding.CommandService, "submit_command_job", fail_submit_command_job
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            embedding.embed_content(
                EmbedRequest(
                    item_id="source:private",
                    item_type="source",
                    async_processing=True,
                ),
                current_user=AuthenticatedUser(
                    username="alice",
                    owner_id="owner_a",
                ),
            )
        )

    assert exc_info.value.status_code == 404


def test_insight_lookup_rejects_cross_owner_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeInsight:
        id = "source_insight:private"
        insight_type = "summary"
        content = "hidden"
        created = datetime(2026, 1, 1)
        updated = datetime(2026, 1, 1)

        async def get_source(self) -> Source:
            return Source(id="source:private", owner_id="owner_b", title="Private")

    async def fake_insight_get(insight_id: str) -> FakeInsight:
        assert insight_id == "source_insight:private"
        return FakeInsight()

    monkeypatch.setattr(insights.SourceInsight, "get", fake_insight_get)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            insights.get_insight(
                "source_insight:private",
                current_user=AuthenticatedUser(
                    username="alice",
                    owner_id="owner_a",
                ),
            )
        )

    assert exc_info.value.status_code == 404
