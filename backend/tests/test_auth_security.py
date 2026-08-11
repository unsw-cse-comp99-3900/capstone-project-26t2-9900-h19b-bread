import hashlib

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.core.passwords import hash_password, verify_password
from app.routers import auth
from app.schemas.auth_schema import LoginRequest, RegisterRequest


class FakeCursor:
    def __init__(self, row: dict | None = None) -> None:
        self.row = row
        self.statements: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement: str, parameters: tuple | None = None) -> None:
        self.statements.append((statement, parameters))

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self.fake_cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor


def test_scrypt_hash_is_salted_and_verifiable() -> None:
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first.startswith("scrypt$")
    assert first != second
    assert verify_password("correct horse battery staple", first) == (True, False)
    assert verify_password("wrong password", first) == (False, False)


def test_legacy_sha256_hash_is_accepted_only_for_migration() -> None:
    legacy = hashlib.sha256(b"legacy-password").hexdigest()

    assert verify_password("legacy-password", legacy) == (True, True)
    assert verify_password("wrong-password", legacy) == (False, False)


def test_malformed_password_hash_fails_closed() -> None:
    assert verify_password("password", "scrypt$bad$hash") == (False, False)
    assert verify_password("password", "!disabled-demo-account!") == (False, False)


def test_registration_rejects_caller_controlled_tenant_and_role() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            name="Publisher",
            email="publisher@example.test",
            password="a-long-password",
            enterprise_id=99,
            role="ADMIN",
        )


def test_public_registration_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ALLOW_PUBLIC_REGISTRATION", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        auth.register(
            RegisterRequest(
                name="Publisher",
                email="publisher@example.test",
                password="a-long-password",
            )
        )

    assert exc_info.value.status_code == 403


def test_enabled_registration_forces_configured_tenant_and_publisher_role(monkeypatch) -> None:
    cursor = FakeCursor(
        {
            "user_id": 5,
            "enterprise_id": 7,
            "email": "publisher@example.test",
            "role": "PUBLISHER",
        }
    )
    monkeypatch.setenv("ALLOW_PUBLIC_REGISTRATION", "true")
    monkeypatch.setenv("PUBLIC_REGISTRATION_ENTERPRISE_ID", "7")
    monkeypatch.setattr(auth, "get_connection", lambda: FakeConnection(cursor))
    monkeypatch.setattr(auth, "create_access_token", lambda **_kwargs: "token")

    result = auth.register(
        RegisterRequest(
            name="Publisher",
            email="publisher@example.test",
            password="a-long-password",
        )
    )

    insert_parameters = cursor.statements[0][1]
    assert insert_parameters is not None
    assert insert_parameters[0] == 7
    assert insert_parameters[4] == "PUBLISHER"
    assert result.user is not None
    assert result.user.enterprise_id == "7"


def test_successful_legacy_login_upgrades_stored_hash(monkeypatch) -> None:
    legacy = hashlib.sha256(b"legacy-password").hexdigest()
    select_cursor = FakeCursor(
        {
            "user_id": 5,
            "enterprise_id": 7,
            "email": "publisher@example.test",
            "role": "PUBLISHER",
            "status": "ACTIVE",
            "password_hash": legacy,
        }
    )
    update_cursor = FakeCursor()
    connections = iter((FakeConnection(select_cursor), FakeConnection(update_cursor)))
    monkeypatch.setattr(auth, "get_connection", lambda: next(connections))
    monkeypatch.setattr(auth, "create_access_token", lambda **_kwargs: "token")

    result = auth.login(
        LoginRequest(email="publisher@example.test", password="legacy-password")
    )

    assert result.status == "success"
    update_parameters = update_cursor.statements[0][1]
    assert update_parameters is not None
    assert update_parameters[0].startswith("scrypt$")
    assert update_parameters[1] == 5
