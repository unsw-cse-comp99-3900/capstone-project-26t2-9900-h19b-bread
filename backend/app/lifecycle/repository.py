from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from app.lifecycle.enums import (
    ApiStatus,
    ApiVersionStatus,
    ValidationOverallStatus,
    ValidationStage,
    ValidationStageStatus,
    VersionEventType,
)


class LifecycleRepository(Protocol):
    """Persistence contract based on the current PostgreSQL schema."""

    def transaction(self) -> AbstractContextManager[None]:
        """Run multiple repository operations in one transaction."""

    def get_api_status(self, api_id: int) -> ApiStatus | None:
        """Read api_submission.status for the given api_id."""

    def get_api_submitted_by(self, api_id: int) -> int | None:
        """Return the API creator used for lifecycle write authorization."""

    def get_api_updated_at(self, api_id: int) -> datetime | None:
        """Read api_submission.updated_at for the given api_id."""

    def update_api_status(self, api_id: int, status: ApiStatus) -> None:
        """Update api_submission.status and api_submission.updated_at."""

    def mark_api_withdrawn(
        self,
        api_id: int,
        actor_id: int,
        reason: str | None,
    ) -> None:
        """Update api_submission withdrawn_* fields and status."""

    def get_current_version_id(self, api_id: int) -> int | None:
        """Return the active/latest api_version.version_id for the API."""

    def update_version_status(
        self,
        version_id: int,
        status: ApiVersionStatus,
    ) -> None:
        """Update api_version.status for statuses supported by api_version_status."""

    def archive_previous_version(self, api_id: int, current_version_id: int) -> None:
        """Archive the previous published version in the cloud version chain."""

    def create_version_event(
        self,
        api_id: int,
        version_id: int,
        event_type: VersionEventType,
        from_status: ApiVersionStatus | None,
        to_status: ApiVersionStatus | None,
        actor_user_id: int | None,
        message: str | None = None,
    ) -> int:
        """Append an event to the cloud-managed api_version_event table."""

    def create_validation_run(
        self,
        api_id: int,
        version_id: int,
        overall_status: ValidationOverallStatus,
    ) -> int:
        """Insert validation_run and return validation_run.validation_run_id."""

    def get_active_validation_run_id(
        self,
        api_id: int,
        version_id: int,
        validation_run_id: int | None = None,
    ) -> int | None:
        """Lock and return the active RUNNING/PARTIAL validation run."""

    def save_validation_result(
        self,
        validation_run_id: int,
        stage: ValidationStage,
        status: ValidationStageStatus,
        message: str | None,
        error_detail: str | None,
    ) -> None:
        """Insert or replace one stage result for a validation run."""

    def get_validation_stage_statuses(
        self,
        validation_run_id: int,
    ) -> dict[ValidationStage, ValidationStageStatus]:
        """Return all recorded stage statuses for the run."""

    def update_validation_run_status(
        self,
        validation_run_id: int,
        status: ValidationOverallStatus,
        completed: bool,
    ) -> None:
        """Update aggregate validation status and completion timestamp."""
