from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import os
from threading import Barrier

import psycopg
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.errors import ForeignKeyViolation, RaiseException
from psycopg.rows import dict_row


ROOT_SCHEMA = Path(__file__).resolve().parents[2] / "24.6_DATABASE_1stversion.sql"
TEST_JWT_SECRET = "version-history-integration-test-key"


@pytest.fixture()
def history_database() -> Iterator[tuple[TestClient, str]]:
    configured_url = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get(
        "DATABASE_URL"
    )
    if not configured_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")

    admin_settings = conninfo_to_dict(configured_url)
    admin_settings["dbname"] = "postgres"
    admin_url = make_conninfo(**admin_settings)
    database_name = "bread_history_test_" + datetime.now().strftime("%Y%m%d%H%M%S%f")
    if not database_name.startswith("bread_history_test_"):
        raise RuntimeError("Unexpected integration-test database name")

    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    target_settings = dict(admin_settings)
    target_settings["dbname"] = database_name
    target_url = make_conninfo(**target_settings)
    previous_database_url = os.environ.get("DATABASE_URL")
    previous_jwt_secret = os.environ.get("JWT_SECRET_KEY")
    try:
        with psycopg.connect(target_url) as connection:
            connection.execute(ROOT_SCHEMA.read_text(encoding="utf-8"))
        os.environ["DATABASE_URL"] = target_url
        os.environ["JWT_SECRET_KEY"] = TEST_JWT_SECRET

        from app.main import app

        yield TestClient(app), target_url
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
        if previous_jwt_secret is None:
            os.environ.pop("JWT_SECRET_KEY", None)
        else:
            os.environ["JWT_SECRET_KEY"] = previous_jwt_secret
        with psycopg.connect(admin_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )


def _headers(user_id: int, email: str, role: str, enterprise_id: int) -> dict[str, str]:
    from app.core.security import create_access_token

    token = create_access_token(user_id, email, role, enterprise_id)
    return {"Authorization": f"Bearer {token}"}


def _version_payload(version_number: str, api_name: str) -> dict[str, object]:
    return {
        "version_number": version_number,
        "change_note": f"Changes for {version_number}",
        "api_name": api_name,
        "endpoint_url": f"https://example.test/{version_number}",
        "protocol_type": "REST",
        "input_format": "JSON",
        "output_format": "JSON",
        "capability_category": "integration-test",
        "description": "Version history integration test.",
        "auth_method": "API_KEY",
        "auth_description": "API key authentication.",
        "security_scheme_name": "ApiKey",
        "spec_content": (
            "openapi: 3.0.3\n"
            "info:\n"
            f"  title: {api_name}\n"
            f"  version: {version_number.removeprefix('v')}\n"
            "paths: {}\n"
        ),
    }


def test_version_history_full_postgresql_flow(
    history_database: tuple[TestClient, str],
) -> None:
    client, _database_url = history_database
    owner = _headers(1, "publisher@example.com", "PUBLISHER", 1)

    v2_response = client.post(
        "/api/apis/1/versions",
        headers=owner,
        json=_version_payload("v2.0", "Invoice API v2"),
    )
    assert v2_response.status_code == 201
    v2_id = v2_response.json()["version_id"]
    assert client.post("/api/apis/1/submit", headers=owner, json={}).status_code == 200
    rejected = client.post(
        "/api/apis/1/validation-result",
        json={
            "passed": False,
            "stage": "SPECIFICATION_VALIDATION",
            "result_json": {"message": "v2 rejected"},
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    v3_response = client.post(
        "/api/apis/1/versions",
        headers=owner,
        json=_version_payload("v3.0", "Invoice API v3"),
    )
    assert v3_response.status_code == 201
    v3_id = v3_response.json()["version_id"]
    assert client.post("/api/apis/1/submit", headers=owner, json={}).status_code == 200
    published = client.post(
        "/api/apis/1/validation-result",
        json={
            "passed": True,
            "stage": "SPECIFICATION_VALIDATION",
            "result_json": {"message": "v3 passed"},
        },
    )
    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"

    versions = client.get("/api/apis/1/versions", headers=owner)
    assert versions.status_code == 200
    assert versions.json()["total"] == 3
    statuses = {
        item["version_number"]: item["status"] for item in versions.json()["items"]
    }
    assert statuses == {"v1.0": "ARCHIVED", "v2.0": "REJECTED", "v3.0": "PUBLISHED"}

    v2_detail = client.get(f"/api/apis/1/versions/{v2_id}", headers=owner)
    assert v2_detail.status_code == 200
    assert v2_detail.json()["api_name"] == "Invoice API v2"
    assert v2_detail.json()["validation_runs"][0]["overall_status"] == "FAILED"
    v3_detail = client.get(f"/api/apis/1/versions/{v3_id}", headers=owner)
    assert v3_detail.json()["is_current"] is True
    assert v3_detail.json()["is_last_published"] is True

    history = client.get("/api/apis/1/history", headers=owner)
    assert history.status_code == 200
    actions = [event["action"] for event in history.json()["items"]]
    assert "VERSION_CREATED" in actions
    assert "VALIDATION_FAILED" in actions
    assert "VALIDATION_PASSED" in actions


def test_history_access_matrix(history_database: tuple[TestClient, str]) -> None:
    client, database_url = history_database
    with psycopg.connect(database_url) as connection:
        connection.execute(
            "INSERT INTO enterprise(name, registration_number) VALUES ('Other', 'ENT-0002')"
        )
        connection.execute(
            """
            INSERT INTO app_user (enterprise_id, name, email, password_hash, role)
            VALUES
                (2, 'Other Viewer', 'other@example.com', 'x', 'VIEWER'),
                (1, 'Enterprise Viewer', 'same@example.com', 'x', 'VIEWER'),
                (1, 'Enterprise Admin', 'admin@example.com', 'x', 'ADMIN')
            """
        )

    owner = _headers(1, "publisher@example.com", "PUBLISHER", 1)
    other = _headers(2, "other@example.com", "VIEWER", 2)
    same_enterprise = _headers(3, "same@example.com", "VIEWER", 1)
    enterprise_admin = _headers(4, "admin@example.com", "ADMIN", 1)

    assert client.get("/api/apis/1/versions").status_code == 401
    assert client.get("/api/apis/1/versions", headers=other).status_code == 200

    private = client.put(
        "/api/apis/1/history-access",
        headers=owner,
        json={"visibility": "PRIVATE", "allowed_user_ids": []},
    )
    assert private.status_code == 200
    assert client.get("/api/apis/1/versions", headers=other).status_code == 404
    assert client.get("/api/apis/1/versions", headers=same_enterprise).status_code == 404
    assert client.get("/api/apis/1/versions", headers=enterprise_admin).status_code == 200

    enterprise = client.put(
        "/api/apis/1/history-access",
        headers=owner,
        json={"visibility": "ENTERPRISE", "allowed_user_ids": []},
    )
    assert enterprise.status_code == 200
    assert client.get("/api/apis/1/versions", headers=same_enterprise).status_code == 200
    assert client.get("/api/apis/1/versions", headers=other).status_code == 404

    granted = client.put(
        "/api/apis/1/history-access",
        headers=owner,
        json={"visibility": "PRIVATE", "allowed_user_ids": [2]},
    )
    assert granted.status_code == 200
    assert client.get("/api/apis/1/versions", headers=other).status_code == 200
    denied_update = client.put(
        "/api/apis/1/history-access",
        headers=other,
        json={"visibility": "PUBLIC", "allowed_user_ids": []},
    )
    assert denied_update.status_code == 403


def test_version_constraints_and_event_atomicity(
    history_database: tuple[TestClient, str],
) -> None:
    client, database_url = history_database
    owner = _headers(1, "publisher@example.com", "PUBLISHER", 1)
    payload = _version_payload("v2.0", "Constraint API")
    created = client.post("/api/apis/1/versions", headers=owner, json=payload)
    assert created.status_code == 201
    version_id = created.json()["version_id"]
    assert client.post("/api/apis/1/versions", headers=owner, json=payload).status_code == 409
    assert client.get(f"/api/apis/999/versions/{version_id}", headers=owner).status_code == 404

    assert client.post("/api/apis/1/submit", headers=owner, json={}).status_code == 200
    assert (
        client.put(
            f"/api/apis/1/versions/{version_id}",
            headers=owner,
            json=payload,
        ).status_code
        == 409
    )
    assert client.post(
        "/api/apis/1/validation-result",
        json={"passed": False, "stage": "SPECIFICATION_VALIDATION"},
    ).status_code == 200
    assert client.post("/api/apis/1/versions", headers=owner, json=payload).status_code == 409

    draft = client.post(
        "/api/v1/submissions/draft",
        headers=owner,
        json={
            "api_name": "Rollback API",
            "endpoint_url": "https://example.test/rollback",
            "protocol": "REST",
            "input_format": "JSON",
            "output_format": "JSON",
            "auth_method": "API_KEY",
            "description": "Rollback test",
            "capability_category": "integration-test",
            "spec_content": _version_payload("v1.0", "Rollback API")["spec_content"],
        },
    )
    assert draft.status_code == 200
    rollback_api_id = int(draft.json()["submission_id"])

    from app.lifecycle import LifecycleService, PostgresLifecycleRepository

    with pytest.raises(ForeignKeyViolation):
        LifecycleService(PostgresLifecycleRepository()).submit_api(rollback_api_id, 999999)

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        state = connection.execute(
            """
            SELECT submission.status AS submission_status, version.status AS version_status
            FROM api_submission submission
            JOIN api_version version ON version.version_id = submission.current_version_id
            WHERE submission.api_id = %s
            """,
            (rollback_api_id,),
        ).fetchone()
        assert state == {"submission_status": "DRAFT", "version_status": "DRAFT"}
        with pytest.raises(RaiseException):
            connection.execute(
                "UPDATE api_lifecycle_event SET reason = 'changed' WHERE api_id = %s",
                (rollback_api_id,),
            )
        connection.rollback()
        with pytest.raises(RaiseException):
            connection.execute(
                "DELETE FROM api_lifecycle_event WHERE api_id = %s",
                (rollback_api_id,),
            )


def test_concurrent_version_creation_allows_one_draft(
    history_database: tuple[TestClient, str],
) -> None:
    _client, database_url = history_database
    actor = {"user_id": 1, "enterprise_id": 1, "role": "PUBLISHER"}
    barrier = Barrier(2)

    from app.version_history import (
        PostgresVersionHistoryRepository,
        VersionConflictError,
        VersionHistoryService,
        VersionWrite,
    )

    def create(version_number: str) -> str:
        payload = _version_payload(version_number, f"Concurrent {version_number}")
        write = VersionWrite(
            version_number=str(payload["version_number"]),
            change_note=str(payload["change_note"]),
            api_name=str(payload["api_name"]),
            endpoint_url=str(payload["endpoint_url"]),
            protocol_type=str(payload["protocol_type"]),
            input_format=str(payload["input_format"]),
            output_format=str(payload["output_format"]),
            capability_category=str(payload["capability_category"]),
            description=str(payload["description"]),
            auth_method=str(payload["auth_method"]),
            auth_description=str(payload["auth_description"]),
            security_scheme_name=str(payload["security_scheme_name"]),
            spec_content=str(payload["spec_content"]),
        )
        barrier.wait()
        try:
            VersionHistoryService(PostgresVersionHistoryRepository()).create_version(
                1, actor, write
            )
            return "created"
        except VersionConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = sorted(executor.map(create, ["v2.0", "v3.0"]))
    assert outcomes == ["conflict", "created"]

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        draft_count = connection.execute(
            "SELECT COUNT(*) AS count FROM api_version WHERE api_id = 1 AND status = 'DRAFT'"
        ).fetchone()["count"]
    assert draft_count == 1
