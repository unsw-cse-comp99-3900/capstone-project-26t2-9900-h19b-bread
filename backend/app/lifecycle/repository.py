from contextlib import AbstractContextManager
from typing import Protocol

from app.lifecycle.enums import (
    ApiStatus,
    ApiVersionStatus,
    ValidationOverallStatus,
    ValidationStage,
    ValidationStageStatus,
)


class LifecycleRepository(Protocol):
    """Persistence contract based on the current PostgreSQL schema."""

    def transaction(self) -> AbstractContextManager[None]:
        """Run multiple repository operations in one transaction."""

    def get_api_status(self, api_id: int) -> ApiStatus | None:
        """Read api_submission.status for the given api_id."""

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

    def create_validation_run(
        self,
        api_id: int,
        version_id: int,
        overall_status: ValidationOverallStatus,
    ) -> int:
        """Insert validation_run and return validation_run.validation_run_id."""

    def save_validation_result(
        self,
        validation_run_id: int,
        stage: ValidationStage,
        status: ValidationStageStatus,
        message: str | None,
        error_detail: str | None,
    ) -> None:
        """Insert validation_result for a validation run stage."""
