from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.auth import require_default_owner_user
from api.routers import (
    credentials,
    episode_profiles,
    models,
    settings,
    speaker_profiles,
    transformations,
)
from open_notebook.auth_context import DEFAULT_OWNER_ID, AuthenticatedUser


def make_request(user: AuthenticatedUser) -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
        }
    )
    request.state.user = user
    return request


def test_default_owner_user_is_required_for_global_admin_endpoints() -> None:
    default_user = AuthenticatedUser(
        username=DEFAULT_OWNER_ID,
        owner_id=DEFAULT_OWNER_ID,
    )
    regular_user = AuthenticatedUser(username="alice", owner_id="owner_a")

    assert require_default_owner_user(make_request(default_user)) == default_user

    with pytest.raises(HTTPException) as exc_info:
        require_default_owner_user(make_request(regular_user))

    assert exc_info.value.status_code == 403


def test_credentials_router_is_default_admin_only() -> None:
    dependencies = [dependency.dependency for dependency in credentials.router.dependencies]

    assert require_default_owner_user in dependencies


def assert_has_admin_dependency(function) -> None:
    signature = inspect.signature(function)
    parameter = signature.parameters.get("_admin")

    assert parameter is not None
    assert getattr(parameter.default, "dependency", None) is require_default_owner_user


def test_model_management_endpoints_are_default_admin_only() -> None:
    for function in [
        models.create_model,
        models.delete_model,
        models.test_model,
        models.update_default_models,
        models.discover_models,
        models.sync_models,
        models.sync_all_models,
        models.auto_assign_defaults,
    ]:
        assert_has_admin_dependency(function)


def test_settings_update_is_default_admin_only() -> None:
    assert_has_admin_dependency(settings.update_settings)


def test_transformation_management_endpoints_are_default_admin_only() -> None:
    for function in [
        transformations.create_transformation,
        transformations.execute_transformation,
        transformations.update_default_prompt,
        transformations.update_transformation,
        transformations.delete_transformation,
    ]:
        assert_has_admin_dependency(function)


def test_podcast_profile_management_endpoints_are_default_admin_only() -> None:
    for function in [
        episode_profiles.create_episode_profile,
        episode_profiles.update_episode_profile,
        episode_profiles.delete_episode_profile,
        episode_profiles.duplicate_episode_profile,
        speaker_profiles.create_speaker_profile,
        speaker_profiles.update_speaker_profile,
        speaker_profiles.delete_speaker_profile,
        speaker_profiles.duplicate_speaker_profile,
    ]:
        assert_has_admin_dependency(function)
