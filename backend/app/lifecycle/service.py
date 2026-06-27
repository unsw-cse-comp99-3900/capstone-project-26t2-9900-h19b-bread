from app.lifecycle.enums import (
    ApiStatus,
    ApiVersionStatus,
    LifecycleAction,
    ValidationOverallStatus,
    ValidationStageStatus,
)
from app.lifecycle.exceptions import ApiNotFoundError, CurrentVersionNotFoundError
from app.lifecycle.repository import LifecycleRepository
from app.lifecycle.schemas import LifecycleResult, ValidationResultInput
from app.lifecycle.state_machine import ensure_transition_allowed


class LifecycleService:
    def __init__(self, repository: LifecycleRepository) -> None:
        self.repository = repository

    def submit_api(self, api_id: int, actor_id: int) -> LifecycleResult:
        with self.repository.transaction():
            current_status = self._get_required_status(api_id)
            target_status = ApiStatus.VALIDATING
            ensure_transition_allowed(current_status, target_status)

            version_id = self._get_required_version_id(api_id)
            action = (
                LifecycleAction.RESUBMIT
                if current_status == ApiStatus.REJECTED
                else LifecycleAction.SUBMIT
            )

            self.repository.update_api_status(api_id, target_status)
            self.repository.update_version_status(version_id, ApiVersionStatus.VALIDATING)
            updated_at = self.repository.get_api_updated_at(api_id)

        return LifecycleResult(
            api_id=api_id,
            status=target_status,
            action=action,
            message="API submitted for validation.",
            version_id=version_id,
            updated_at=updated_at,
        )

    def handle_validation_result(
        self,
        api_id: int,
        validation_result: ValidationResultInput,
    ) -> LifecycleResult:
        with self.repository.transaction():
            current_status = self._get_required_status(api_id)
            target_status = (
                ApiStatus.PUBLISHED if validation_result.passed else ApiStatus.REJECTED
            )
            ensure_transition_allowed(current_status, target_status)

            version_id = self._get_required_version_id(api_id)
            action = (
                LifecycleAction.VALIDATION_PASSED
                if validation_result.passed
                else LifecycleAction.VALIDATION_FAILED
            )
            overall_status = (
                ValidationOverallStatus.PASSED
                if validation_result.passed
                else ValidationOverallStatus.FAILED
            )
            stage_status = (
                ValidationStageStatus.PASSED
                if validation_result.passed
                else ValidationStageStatus.FAILED
            )

            validation_run_id = self.repository.create_validation_run(
                api_id=api_id,
                version_id=version_id,
                overall_status=overall_status,
            )
            self.repository.save_validation_result(
                validation_run_id=validation_run_id,
                stage=validation_result.stage,
                status=stage_status,
                message=validation_result.message,
                error_detail=validation_result.error_detail,
            )
            self.repository.update_api_status(api_id, target_status)
            self.repository.update_version_status(
                version_id,
                self._to_version_status(target_status),
            )
            updated_at = self.repository.get_api_updated_at(api_id)

        return LifecycleResult(
            api_id=api_id,
            status=target_status,
            action=action,
            message=(
                "Validation passed. API published successfully."
                if validation_result.passed
                else "Validation failed. API rejected."
            ),
            version_id=version_id,
            validation_run_id=validation_run_id,
            updated_at=updated_at,
        )

    def withdraw_api(
        self,
        api_id: int,
        actor_id: int,
        reason: str | None = None,
    ) -> LifecycleResult:
        with self.repository.transaction():
            current_status = self._get_required_status(api_id)
            target_status = ApiStatus.WITHDRAWN
            ensure_transition_allowed(current_status, target_status)

            version_id = self._get_required_version_id(api_id)
            self.repository.mark_api_withdrawn(
                api_id=api_id,
                actor_id=actor_id,
                reason=reason,
            )
            self.repository.update_version_status(version_id, ApiVersionStatus.ARCHIVED)
            updated_at = self.repository.get_api_updated_at(api_id)

        return LifecycleResult(
            api_id=api_id,
            status=target_status,
            action=LifecycleAction.WITHDRAW,
            message="API withdrawn successfully.",
            version_id=version_id,
            updated_at=updated_at,
        )

    def get_status(self, api_id: int) -> LifecycleResult:
        with self.repository.transaction():
            status = self._get_required_status(api_id)
            updated_at = self.repository.get_api_updated_at(api_id)

        return LifecycleResult(
            api_id=api_id,
            status=status,
            message="API status loaded successfully.",
            updated_at=updated_at,
        )

    def _get_required_status(self, api_id: int) -> ApiStatus:
        status = self.repository.get_api_status(api_id)
        if status is None:
            raise ApiNotFoundError(api_id)
        return status

    def _get_required_version_id(self, api_id: int) -> int:
        version_id = self.repository.get_current_version_id(api_id)
        if version_id is None:
            raise CurrentVersionNotFoundError(api_id)
        return version_id

    def _to_version_status(self, status: ApiStatus) -> ApiVersionStatus:
        if status == ApiStatus.WITHDRAWN:
            return ApiVersionStatus.ARCHIVED
        return ApiVersionStatus(status.value)
