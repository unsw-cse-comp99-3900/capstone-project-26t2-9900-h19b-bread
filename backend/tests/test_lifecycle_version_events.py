from contextlib import contextmanager
from datetime import datetime

import pytest

from app.lifecycle.enums import (
    ApiStatus,
    ValidationOverallStatus,
    ValidationStage,
    ValidationStageStatus,
    VersionEventType,
)
from app.lifecycle.exceptions import ApiPermissionError
from app.lifecycle.postgres_repository import PostgresLifecycleRepository
from app.lifecycle.schemas import ValidationResultInput
from app.lifecycle.service import LifecycleService


class FakeLifecycleRepository:
    def __init__(self, status: ApiStatus) -> None:
        self.status = status
        self.version_id = 12
        self.version_status = None
        self.events: list[dict] = []
        self.archived_previous = False
        self.previous_published_version_id = None
        self.restored_current_version = None
        self.restored_status = None
        self.validation_run_id = 90
        self.validation_overall_status = ValidationOverallStatus.RUNNING
        self.validation_stage_statuses = {}
        self.connections_deprecated = False
        self.stale_connection_runs_for = None

    @contextmanager
    def transaction(self):
        yield

    def get_api_status(self, api_id):
        return self.status

    def get_api_submitted_by(self, api_id):
        return 42

    def get_api_updated_at(self, api_id):
        return datetime(2026, 7, 19)

    def update_api_status(self, api_id, status):
        self.status = status

    def mark_api_withdrawn(self, api_id, actor_id, reason):
        self.status = ApiStatus.WITHDRAWN

    def deprecate_api_connections(self, api_id):
        self.connections_deprecated = True

    def get_current_version_id(self, api_id):
        return self.version_id

    def update_version_status(self, version_id, status):
        self.version_status = status

    def archive_previous_version(self, api_id, current_version_id):
        self.archived_previous = True

    def stale_superseded_connection_runs(self, api_id, published_version_id):
        self.stale_connection_runs_for = (api_id, published_version_id)

    def get_previous_published_version_id(self, api_id, current_version_id):
        return self.previous_published_version_id

    def restore_api_current_version(self, api_id, version_id, status):
        self.restored_current_version = version_id
        self.restored_status = status
        self.status = status

    def create_version_event(
        self,
        api_id,
        version_id,
        event_type,
        from_status,
        to_status,
        actor_user_id,
        message=None,
    ):
        self.events.append(
            {
                "event_type": event_type,
                "from_status": from_status,
                "to_status": to_status,
                "actor_user_id": actor_user_id,
            }
        )
        return len(self.events)

    def create_validation_run(self, api_id, version_id, overall_status):
        self.validation_overall_status = overall_status
        return self.validation_run_id

    def get_active_validation_run_id(
        self,
        api_id,
        version_id,
        validation_run_id=None,
    ):
        if validation_run_id not in {None, self.validation_run_id}:
            return None
        if self.validation_overall_status not in {
            ValidationOverallStatus.RUNNING,
            ValidationOverallStatus.PARTIAL,
        }:
            return None
        return self.validation_run_id

    def save_validation_result(self, validation_run_id, stage, status, **kwargs):
        self.validation_stage_statuses[stage] = status

    def get_validation_stage_statuses(self, validation_run_id):
        return dict(self.validation_stage_statuses)

    def update_validation_run_status(self, validation_run_id, status, completed):
        self.validation_overall_status = status


def test_submit_records_version_event_with_actor() -> None:
    repository = FakeLifecycleRepository(ApiStatus.DRAFT)

    result = LifecycleService(repository).submit_api(api_id=5, actor_id=42)

    event = repository.events[0]
    assert event["event_type"] == VersionEventType.SUBMITTED_FOR_VALIDATION
    assert event["actor_user_id"] == 42
    assert event["from_status"].value == "DRAFT"
    assert event["to_status"].value == "VALIDATING"
    assert result.validation_run_id == 90
    assert repository.validation_overall_status == ValidationOverallStatus.RUNNING


def test_single_successful_stage_remains_validating() -> None:
    repository = FakeLifecycleRepository(ApiStatus.VALIDATING)

    result = LifecycleService(repository).handle_validation_result(
        api_id=5,
        validation_result=ValidationResultInput(
            passed=True,
            stage=ValidationStage.SPECIFICATION_VALIDATION,
            message="passed",
        ),
    )

    assert result.status == ApiStatus.VALIDATING
    assert repository.validation_overall_status == ValidationOverallStatus.PARTIAL
    assert repository.archived_previous is False
    assert repository.events == []


def test_all_required_stages_publish_and_archive_previous_version() -> None:
    repository = FakeLifecycleRepository(ApiStatus.VALIDATING)
    service = LifecycleService(repository)

    for stage in ValidationStage:
        result = service.handle_validation_result(
            api_id=5,
            validation_run_id=90,
            validation_result=ValidationResultInput(passed=True, stage=stage),
        )

    assert result.status == ApiStatus.PUBLISHED
    assert repository.validation_overall_status == ValidationOverallStatus.PASSED
    assert repository.archived_previous is True
    assert repository.stale_connection_runs_for == (5, 12)
    assert repository.events[0]["event_type"] == VersionEventType.VALIDATION_PASSED


def test_any_failed_stage_rejects_immediately() -> None:
    repository = FakeLifecycleRepository(ApiStatus.VALIDATING)

    result = LifecycleService(repository).handle_validation_result(
        api_id=5,
        validation_run_id=90,
        validation_result=ValidationResultInput(
            passed=False,
            stage=ValidationStage.SECURITY_VALIDATION,
        ),
    )

    assert result.status == ApiStatus.REJECTED
    assert repository.validation_overall_status == ValidationOverallStatus.FAILED
    assert repository.events[0]["event_type"] == VersionEventType.VALIDATION_FAILED


def test_failed_new_version_restores_previous_published_api() -> None:
    repository = FakeLifecycleRepository(ApiStatus.VALIDATING)
    repository.version_id = 22
    repository.previous_published_version_id = 12

    result = LifecycleService(repository).handle_validation_result(
        api_id=5,
        validation_run_id=90,
        validation_result=ValidationResultInput(
            passed=False,
            stage=ValidationStage.DOMAIN_COMPLIANCE_VALIDATION,
        ),
    )

    assert result.status == ApiStatus.REJECTED
    assert result.version_id == 22
    assert "Previous published version remains active" in result.message
    assert repository.version_status.value == "REJECTED"
    assert repository.restored_current_version == 12
    assert repository.restored_status == ApiStatus.PUBLISHED
    assert repository.status == ApiStatus.PUBLISHED


def test_withdraw_records_archive_event_with_actor() -> None:
    repository = FakeLifecycleRepository(ApiStatus.PUBLISHED)

    LifecycleService(repository).withdraw_api(api_id=5, actor_id=42, reason="retired")

    assert repository.events[0]["event_type"] == VersionEventType.ARCHIVED
    assert repository.events[0]["actor_user_id"] == 42
    assert repository.events[0]["to_status"].value == "ARCHIVED"
    assert repository.connections_deprecated is True


def test_rejected_api_can_be_withdrawn() -> None:
    repository = FakeLifecycleRepository(ApiStatus.REJECTED)

    result = LifecycleService(repository).withdraw_api(api_id=5, actor_id=42, reason="cleanup")

    assert result.status == ApiStatus.WITHDRAWN
    assert repository.events[0]["event_type"] == VersionEventType.ARCHIVED
    assert repository.events[0]["from_status"].value == "REJECTED"
    assert repository.events[0]["to_status"].value == "ARCHIVED"


def test_non_creator_cannot_submit() -> None:
    repository = FakeLifecycleRepository(ApiStatus.DRAFT)

    with pytest.raises(ApiPermissionError):
        LifecycleService(repository).submit_api(api_id=5, actor_id=99)


def test_global_admin_can_withdraw_another_users_api() -> None:
    repository = FakeLifecycleRepository(ApiStatus.PUBLISHED)

    result = LifecycleService(repository).withdraw_api(
        api_id=5,
        actor_id=99,
        is_admin=True,
    )

    assert result.status == ApiStatus.WITHDRAWN


def test_deprecate_api_connections_cancels_running_validation_runs() -> None:
    class FakeCursor:
        def __init__(self):
            self.statements = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, statement, params=None):
            self.statements.append((statement, params))

    class FakeConnection:
        def __init__(self, cursor):
            self.cursor_obj = cursor

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return self.cursor_obj

    cursor = FakeCursor()
    repository = PostgresLifecycleRepository(
        connection_factory=lambda: FakeConnection(cursor)
    )

    repository.deprecate_api_connections(5)

    assert len(cursor.statements) == 2
    cancel_statement, params = cursor.statements[0]
    assert "UPDATE connection_validation_run" in cancel_statement
    assert "status = 'CANCELLED'" in cancel_statement
    assert "status = 'RUNNING'" in cancel_statement
    assert params == (5, 5)
    assert "UPDATE schema_mapping" in cursor.statements[1][0]
