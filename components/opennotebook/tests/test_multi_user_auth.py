from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import pytest

from api.auth import (
    auth_mode,
    authenticate_bearer,
    authenticate_login,
    create_access_token,
)
from open_notebook.auth_context import (
    DEFAULT_OWNER_ID,
    AuthenticatedUser,
    reset_current_user,
    set_current_user,
)
from open_notebook.domain import base
from open_notebook.domain import notebook as notebook_domain
from open_notebook.domain.base import ObjectModel
from open_notebook.domain.notebook import Notebook
from open_notebook.exceptions import NotFoundError

AUTH_ENV_VARS = [
    "OPEN_NOTEBOOK_USERS",
    "OPEN_NOTEBOOK_USERS_FILE",
    "OPEN_NOTEBOOK_PASSWORD",
    "OPEN_NOTEBOOK_PASSWORD_FILE",
    "OPEN_NOTEBOOK_AUTH_SECRET",
    "OPEN_NOTEBOOK_AUTH_SECRET_FILE",
    "OPEN_NOTEBOOK_ENCRYPTION_KEY",
    "OPEN_NOTEBOOK_ENCRYPTION_KEY_FILE",
]


class OwnedThing(ObjectModel):
    table_name: ClassVar[str] = "owned_thing"

    owner_id: str | None = None
    name: str = ""


@pytest.fixture(autouse=True)
def clean_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in AUTH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_multi_user_login_uses_signed_tokens_and_rejects_legacy_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_NOTEBOOK_USERS", "alice:alpha,bob:beta")
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "legacy-password")
    monkeypatch.setenv("OPEN_NOTEBOOK_AUTH_SECRET", "stable-token-secret")

    assert auth_mode() == "multi_user"

    alice = authenticate_login("alice", "alpha")
    bob = authenticate_login("bob", "beta")

    assert alice is not None
    assert bob is not None
    assert alice.username == "alice"
    assert bob.username == "bob"
    assert alice.owner_id != bob.owner_id
    assert alice.owner_id.startswith("user_")
    assert bob.owner_id.startswith("user_")

    assert authenticate_login("alice", "wrong-password") is None
    assert authenticate_login(None, "alpha") is None

    token = create_access_token(alice)
    assert authenticate_bearer(token) == alice

    # In multi-user mode the legacy shared password must not authenticate.
    assert authenticate_bearer("legacy-password") is None


def test_multi_user_token_is_rejected_after_user_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_NOTEBOOK_USERS", "alice:alpha,bob:beta")
    monkeypatch.setenv("OPEN_NOTEBOOK_AUTH_SECRET", "stable-token-secret")

    alice = authenticate_login("alice", "alpha")
    assert alice is not None
    token = create_access_token(alice)
    assert authenticate_bearer(token) == alice

    monkeypatch.setenv("OPEN_NOTEBOOK_USERS", "bob:beta")

    assert authenticate_bearer(token) is None


def test_multi_user_token_owner_must_match_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_NOTEBOOK_USERS", "alice:alpha")
    monkeypatch.setenv("OPEN_NOTEBOOK_AUTH_SECRET", "stable-token-secret")

    mismatched_token = create_access_token(
        AuthenticatedUser(username="alice", owner_id="owner_b")
    )

    assert authenticate_bearer(mismatched_token) is None


def test_legacy_password_mode_keeps_default_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPEN_NOTEBOOK_PASSWORD", "legacy-password")

    assert auth_mode() == "password"

    user = authenticate_login(None, "legacy-password")

    assert user == AuthenticatedUser(
        username=DEFAULT_OWNER_ID,
        owner_id=DEFAULT_OWNER_ID,
    )
    assert authenticate_bearer("legacy-password") == user


def test_default_account_preserves_access_to_existing_data_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "OPEN_NOTEBOOK_USERS",
        '{"default":"default-password","alice":{"password":"alice-password"}}',
    )

    default_user = authenticate_login("default", "default-password")
    alice = authenticate_login("alice", "alice-password")

    assert default_user == AuthenticatedUser(
        username=DEFAULT_OWNER_ID,
        owner_id=DEFAULT_OWNER_ID,
    )
    assert alice is not None
    assert alice.owner_id != DEFAULT_OWNER_ID


def test_get_all_filters_owned_models_by_current_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any] | None]] = []

    async def fake_repo_query(
        query: str, vars: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        calls.append((query, vars))
        return [
            {
                "id": "owned_thing:one",
                "owner_id": "owner_a",
                "name": "visible",
            }
        ]

    monkeypatch.setattr(base, "repo_query", fake_repo_query)
    token = set_current_user(AuthenticatedUser(username="alice", owner_id="owner_a"))
    try:
        result = asyncio.run(OwnedThing.get_all(order_by="updated desc"))
    finally:
        reset_current_user(token)

    assert len(result) == 1
    assert result[0].owner_id == "owner_a"
    assert calls == [
        (
            "SELECT * FROM owned_thing WHERE owner_id = $owner_id ORDER BY updated desc",
            {"owner_id": "owner_a"},
        )
    ]


def test_get_rejects_records_owned_by_another_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_repo_query(
        query: str, vars: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        assert query == "SELECT * FROM $id"
        assert vars == {"id": "owned_thing:one"}
        return [
            {
                "id": "owned_thing:one",
                "owner_id": "owner_b",
                "name": "hidden",
            }
        ]

    monkeypatch.setattr(base, "repo_query", fake_repo_query)
    token = set_current_user(AuthenticatedUser(username="alice", owner_id="owner_a"))
    try:
        with pytest.raises(NotFoundError):
            asyncio.run(OwnedThing.get("owned_thing:one"))
    finally:
        reset_current_user(token)


def test_default_owner_can_read_pre_migration_records_without_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_repo_query(
        query: str, vars: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": "owned_thing:legacy",
                "name": "legacy",
            }
        ]

    monkeypatch.setattr(base, "repo_query", fake_repo_query)
    token = set_current_user(
        AuthenticatedUser(username=DEFAULT_OWNER_ID, owner_id=DEFAULT_OWNER_ID)
    )
    try:
        result = asyncio.run(OwnedThing.get("owned_thing:legacy"))
    finally:
        reset_current_user(token)

    assert result.id == "owned_thing:legacy"
    assert result.owner_id is None


def test_notebook_relationship_reads_filter_cross_owner_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_repo_query(
        query: str, vars: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        if "fetch source" in query:
            return [
                {
                    "source": {
                        "id": "source:visible",
                        "owner_id": "owner_a",
                        "title": "Visible source",
                    }
                },
                {
                    "source": {
                        "id": "source:hidden",
                        "owner_id": "owner_b",
                        "title": "Hidden source",
                    }
                },
            ]
        if "fetch note" in query:
            return [
                {
                    "note": {
                        "id": "note:visible",
                        "owner_id": "owner_a",
                        "title": "Visible note",
                        "content": "visible",
                    }
                },
                {
                    "note": {
                        "id": "note:hidden",
                        "owner_id": "owner_b",
                        "title": "Hidden note",
                        "content": "hidden",
                    }
                },
            ]
        if "fetch chat_session" in query:
            return [
                {
                    "chat_session": [
                        {
                            "id": "chat_session:visible",
                            "owner_id": "owner_a",
                            "title": "Visible chat",
                        }
                    ]
                },
                {
                    "chat_session": [
                        {
                            "id": "chat_session:hidden",
                            "owner_id": "owner_b",
                            "title": "Hidden chat",
                        }
                    ]
                },
            ]
        raise AssertionError(f"Unexpected query: {query}")

    monkeypatch.setattr(notebook_domain, "repo_query", fake_repo_query)
    user_token = set_current_user(AuthenticatedUser(username="alice", owner_id="owner_a"))
    notebook = Notebook(
        id="notebook:one",
        name="Owned notebook",
        description="",
        owner_id="owner_a",
    )
    try:
        sources = asyncio.run(notebook.get_sources())
        notes = asyncio.run(notebook.get_notes())
        sessions = asyncio.run(notebook.get_chat_sessions())
    finally:
        reset_current_user(user_token)

    assert [source.id for source in sources] == ["source:visible"]
    assert [note.id for note in notes] == ["note:visible"]
    assert [session.id for session in sessions] == ["chat_session:visible"]
