from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from api.routers import commands


def test_generic_command_submission_is_disabled() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            commands.execute_command(
                commands.CommandExecutionRequest(
                    app="open_notebook",
                    command="embed_source",
                    input={"source_id": "source:private"},
                )
            )
        )

    assert exc_info.value.status_code == 403


def test_generic_command_status_redacts_result_payload(monkeypatch) -> None:
    async def fake_get_command_status(job_id: str):
        assert job_id == "command:one"
        return {
            "job_id": job_id,
            "status": "completed",
            "result": {"source_text": "private content"},
            "error_message": None,
            "created": "2026-01-01",
            "updated": "2026-01-01",
            "progress": {"chunks": 12},
        }

    monkeypatch.setattr(
        commands.CommandService,
        "get_command_status",
        fake_get_command_status,
    )

    response = asyncio.run(commands.get_command_job_status("command:one"))

    assert response.status == "completed"
    assert response.result is None
    assert response.progress is None


def test_generic_command_cancel_and_registry_debug_are_disabled() -> None:
    with pytest.raises(HTTPException) as cancel_exc:
        asyncio.run(commands.cancel_command_job("command:one"))

    with pytest.raises(HTTPException) as debug_exc:
        asyncio.run(commands.debug_registry())

    assert cancel_exc.value.status_code == 403
    assert debug_exc.value.status_code == 403
