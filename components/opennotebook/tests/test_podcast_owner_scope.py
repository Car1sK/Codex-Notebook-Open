from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from fastapi import HTTPException

from api import podcast_service
from api.routers import podcasts
from commands.podcast_commands import PodcastGenerationInput
from open_notebook.auth_context import AuthenticatedUser
from open_notebook.podcasts.models import PodcastEpisode


def make_episode(owner_id: str) -> PodcastEpisode:
    return PodcastEpisode(
        id="episode:one",
        owner_id=owner_id,
        name="Private Episode",
        episode_profile={"name": "default"},
        speaker_profile={"name": "default"},
        briefing="briefing",
        content="private content",
        created=datetime(2026, 1, 1),
        updated=datetime(2026, 1, 1),
    )


def test_podcast_service_passes_owner_to_generation_command(monkeypatch) -> None:
    submitted_args = {}

    async def fake_get_episode_profile(name: str):
        return object()

    async def fake_get_speaker_profile(name: str):
        return object()

    def fake_submit_command(app: str, command: str, args: dict):
        submitted_args.update({"app": app, "command": command, "args": args})
        return "command:podcast"

    monkeypatch.setattr(
        podcast_service.EpisodeProfile,
        "get_by_name",
        fake_get_episode_profile,
    )
    monkeypatch.setattr(
        podcast_service.SpeakerProfile,
        "get_by_name",
        fake_get_speaker_profile,
    )
    monkeypatch.setattr(podcast_service, "submit_command", fake_submit_command)

    job_id = asyncio.run(
        podcast_service.PodcastService.submit_generation_job(
            episode_profile_name="episode-default",
            speaker_profile_name="speaker-default",
            episode_name="episode",
            owner_id="owner_a",
            content="content",
        )
    )

    assert job_id == "command:podcast"
    assert submitted_args["app"] == "open_notebook"
    assert submitted_args["command"] == "generate_podcast"
    assert submitted_args["args"]["owner_id"] == "owner_a"


def test_podcast_generation_input_accepts_owner_id() -> None:
    input_data = PodcastGenerationInput(
        episode_profile="episode-default",
        speaker_profile="speaker-default",
        episode_name="episode",
        content="content",
        owner_id="owner_a",
    )

    assert input_data.owner_id == "owner_a"


def test_podcast_job_status_redacts_result_payload(monkeypatch) -> None:
    class FakeStatus:
        status = "completed"
        result = {"transcript": "private transcript"}
        error_message = None
        created = datetime(2026, 1, 1)
        updated = datetime(2026, 1, 1)
        progress = {"segments": 5}

    async def fake_get_command_status(job_id: str):
        assert job_id == "command:podcast"
        return FakeStatus()

    monkeypatch.setattr(
        podcast_service,
        "get_command_status",
        fake_get_command_status,
    )

    status = asyncio.run(
        podcast_service.PodcastService.get_job_status("command:podcast")
    )

    assert status["status"] == "completed"
    assert status["result"] is None
    assert status["progress"] is None


def test_podcast_episode_route_rejects_cross_owner_episode(monkeypatch) -> None:
    async def fake_get_episode(episode_id: str) -> PodcastEpisode:
        assert episode_id == "episode:one"
        return make_episode("owner_b")

    monkeypatch.setattr(
        podcasts.PodcastService,
        "get_episode",
        fake_get_episode,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            podcasts.get_podcast_episode(
                "episode:one",
                current_user=AuthenticatedUser(username="alice", owner_id="owner_a"),
            )
        )

    assert exc_info.value.status_code == 404


def test_podcast_delete_rejects_cross_owner_before_deleting(monkeypatch) -> None:
    episode = make_episode("owner_b")

    async def fake_get_episode(episode_id: str) -> PodcastEpisode:
        assert episode_id == "episode:one"
        return episode

    async def fail_delete(_self) -> bool:
        raise AssertionError("cross-owner episode must not be deleted")

    monkeypatch.setattr(PodcastEpisode, "delete", fail_delete)
    monkeypatch.setattr(
        podcasts.PodcastService,
        "get_episode",
        fake_get_episode,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            podcasts.delete_podcast_episode(
                "episode:one",
                current_user=AuthenticatedUser(username="alice", owner_id="owner_a"),
            )
        )

    assert exc_info.value.status_code == 404
