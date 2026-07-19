from contextlib import contextmanager
from datetime import datetime

from app.lifecycle.enums import ApiStatus, ValidationStage, VersionEventType
from app.lifecycle.schemas import ValidationResultInput
from app.lifecycle.service import LifecycleService


class FakeLifecycleRepository:
    def __init__(self, status: ApiStatus) -> None:
        self.status = status
        self.version_id = 12
        self.version_status = None
        self.events: list[dict] = []
        self.archived_previous = False

    @contextmanager
    def transaction(self):
        yield

    def get_api_status(self, api_id):
        return self.status

    def get_api_updated_at(self, api_id):
        return datetime(2026, 7, 19)

    def update_api_status(self, api_id, status):
        self.status = status

    def mark_api_withdrawn(self, api_id, actor_id, reason):
        self.status = ApiStatus.WITHDRAWN

    def get_current_version_id(self, api_id):
        return self.version_id

    def update_version_status(self, version_id, status):
        self.version_status = status

    def archive_previous_version(self, api_id, current_version_id):
        self.archived_previous = True

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
        return 90

    def save_validation_result(self, **kwargs):
        return None


def test_submit_records_version_event_with_actor() -> None:
    repository = FakeLifecycleRepository(ApiStatus.DRAFT)

    LifecycleService(repository).submit_api(api_id=5, actor_id=42)

    event = repository.events[0]
    assert event["event_type"] == VersionEventType.SUBMITTED_FOR_VALIDATION
    assert event["actor_user_id"] == 42
    assert event["from_status"].value == "DRAFT"
    assert event["to_status"].value == "VALIDATING"


def test_successful_validation_archives_prior_published_version() -> None:
    repository = FakeLifecycleRepository(ApiStatus.VALIDATING)

    LifecycleService(repository).handle_validation_result(
        api_id=5,
        validation_result=ValidationResultInput(
            passed=True,
            stage=ValidationStage.SPECIFICATION_VALIDATION,
            message="passed",
        ),
    )

    assert repository.archived_previous is True
    assert repository.events[0]["event_type"] == VersionEventType.VALIDATION_PASSED
    assert repository.events[0]["to_status"].value == "PUBLISHED"


def test_withdraw_records_archive_event_with_actor() -> None:
    repository = FakeLifecycleRepository(ApiStatus.PUBLISHED)

    LifecycleService(repository).withdraw_api(api_id=5, actor_id=42, reason="retired")

    assert repository.events[0]["event_type"] == VersionEventType.ARCHIVED
    assert repository.events[0]["actor_user_id"] == 42
    assert repository.events[0]["to_status"].value == "ARCHIVED"
