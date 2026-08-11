from contextlib import contextmanager
from datetime import datetime

import pytest

from app.version_history.exceptions import VersionConflictError, VersionPermissionError
from app.version_history.schemas import VersionWriteRequest
from app.version_history.service import VersionHistoryService


def version_request(version_number: str = "v2.0") -> VersionWriteRequest:
    return VersionWriteRequest(
        version_number=version_number,
        change_note="Updated endpoint",
        api_name="Invoice API",
        endpoint_url="https://example.test/invoices",
        protocol_type="REST",
        capability_category="invoice",
        description="Invoice exchange",
        input_format="JSON",
        output_format="JSON",
        auth_method="OAUTH2",
        auth_description="OAuth client credentials",
        security_scheme_name="oauth2",
        auth_is_complete=True,
        spec_type="OPENAPI",
        specification='{"openapi":"3.0.0"}',
    )


class FakeVersionHistoryRepository:
    def __init__(self, status: str = "PUBLISHED") -> None:
        self.api = {
            "api_id": 7,
            "enterprise_id": 1,
            "submitted_by": 10,
            "status": status,
            "current_version_id": 70,
        }
        self.versions = {
            70: {
                "version_id": 70,
                "api_id": 7,
                "version_number": "v1.0",
                "change_note": None,
                "status": status,
                "is_current": True,
                "previous_version_id": None,
                "created_by": 10,
                "api_name": "Invoice API",
                "endpoint_url": "https://example.test/v1",
                "protocol_type": "REST",
                "category": None,
                "capability_category": "invoice",
                "description": None,
                "input_format": "JSON",
                "output_format": "JSON",
                "created_at": datetime(2026, 7, 19),
                "published_at": None,
                "archived_at": None,
                "auth": None,
                "specification": None,
                "validation_runs": [],
            }
        }
        self.created_by: int | None = None
        self.updated_by: int | None = None
        self.connection_impacts = [
            {
                "mapping_id": 90,
                "role": "SOURCE",
                "api_version_id": 70,
                "counterpart_api_id": 8,
                "counterpart_version_id": 80,
                "lifecycle_status": "STALE",
                "completeness": "FULL",
                "latest_validation_run_id": 900,
                "latest_validation_run_status": "STALE",
                "updated_at": datetime(2026, 7, 30),
            }
        ]

    @contextmanager
    def transaction(self):
        yield

    def get_api(self, api_id: int, *, for_update: bool = False):
        return self.api if api_id == 7 else None

    def get_version(self, api_id: int, version_id: int):
        return self.versions.get(version_id) if api_id == 7 else None

    def get_version_detail(self, api_id: int, version_id: int):
        return self.get_version(api_id, version_id)

    def list_versions(self, api_id: int, limit: int, offset: int):
        return list(self.versions.values())[offset : offset + limit], len(self.versions)

    def create_version(self, api_id, actor_id, previous_id, data):
        self.created_by = actor_id
        self.versions[71] = {
            **self.versions[70],
            "version_id": 71,
            "version_number": data.version_number,
            "status": "DRAFT",
            "previous_version_id": previous_id,
            "created_by": actor_id,
        }
        self.api["current_version_id"] = 71
        self.api["status"] = "DRAFT"
        return 71

    def update_version(self, api_id, version_id, actor_id, data):
        self.updated_by = actor_id
        self.versions[version_id]["version_number"] = data.version_number

    def list_connection_impacts(
        self,
        api_id,
        limit,
        offset,
        version_id,
        lifecycle_status,
    ):
        items = self.connection_impacts
        if lifecycle_status is not None:
            items = [item for item in items if item["lifecycle_status"] == lifecycle_status]
        return items[offset : offset + limit], len(items)


def test_same_enterprise_can_read_version_history() -> None:
    repository = FakeVersionHistoryRepository()
    service = VersionHistoryService(repository)

    result = service.list_versions(
        api_id=7,
        page=1,
        page_size=20,
        current_user={"user_id": 11, "role": "PUBLISHER", "enterprise_id": 1},
    )

    assert result["total"] == 1
    assert result["items"][0]["version_id"] == 70


def test_other_enterprise_cannot_read_version_history() -> None:
    repository = FakeVersionHistoryRepository()
    service = VersionHistoryService(repository)

    with pytest.raises(VersionPermissionError):
        service.list_versions(
            api_id=7,
            page=1,
            page_size=20,
            current_user={"user_id": 12, "role": "PUBLISHER", "enterprise_id": 2},
        )


def test_global_admin_can_read_version_history() -> None:
    repository = FakeVersionHistoryRepository()
    service = VersionHistoryService(repository)

    result = service.list_versions(
        api_id=7,
        page=1,
        page_size=20,
        current_user={"user_id": 99, "role": "ADMIN", "enterprise_id": 999},
    )

    assert result["total"] == 1


@pytest.mark.parametrize(
    "user",
    [
        {"user_id": 10, "role": "PUBLISHER", "enterprise_id": 1},
        {"user_id": 99, "role": "ADMIN", "enterprise_id": 999},
    ],
)
def test_creator_or_global_admin_can_create_version(user: dict) -> None:
    repository = FakeVersionHistoryRepository()
    service = VersionHistoryService(repository)

    version = service.create_version(7, user, version_request())

    assert version["version_id"] == 71
    assert repository.created_by == user["user_id"]


def test_same_enterprise_does_not_grant_write_permission() -> None:
    repository = FakeVersionHistoryRepository()
    service = VersionHistoryService(repository)
    same_enterprise_non_creator = {
        "user_id": 11,
        "role": "PUBLISHER",
        "enterprise_id": 1,
    }

    with pytest.raises(VersionPermissionError):
        service.create_version(7, same_enterprise_non_creator, version_request())


def test_new_version_rejected_while_current_draft_exists() -> None:
    repository = FakeVersionHistoryRepository(status="DRAFT")
    service = VersionHistoryService(repository)

    with pytest.raises(VersionConflictError):
        service.create_version(
            7,
            {"user_id": 10, "role": "PUBLISHER"},
            version_request(),
        )


def test_only_current_draft_can_be_updated() -> None:
    repository = FakeVersionHistoryRepository(status="DRAFT")
    service = VersionHistoryService(repository)
    creator = {"user_id": 10, "role": "PUBLISHER", "enterprise_id": 1}

    result = service.update_version(7, 70, creator, version_request("v1.1"))

    assert result["version_number"] == "v1.1"
    assert repository.updated_by == 10


def test_published_version_cannot_be_updated() -> None:
    repository = FakeVersionHistoryRepository(status="PUBLISHED")
    service = VersionHistoryService(repository)

    with pytest.raises(VersionConflictError):
        service.update_version(
            7,
            70,
            {"user_id": 10, "role": "PUBLISHER"},
            version_request("v1.1"),
        )


def test_connection_impacts_can_be_filtered_by_lifecycle_status() -> None:
    repository = FakeVersionHistoryRepository()
    service = VersionHistoryService(repository)

    result = service.list_connection_impacts(
        7,
        1,
        20,
        70,
        "STALE",
        {"user_id": 11, "role": "PUBLISHER", "enterprise_id": 1},
    )

    assert result["total"] == 1
    assert result["items"][0]["latest_validation_run_status"] == "STALE"
