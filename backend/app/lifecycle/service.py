from app.lifecycle.enums import (
    ApiStatus,
    ApiVersionStatus,
    LifecycleAction,
    ValidationOverallStatus,
    ValidationStage,
    ValidationStageStatus,
    VersionEventType,
)
from app.lifecycle.exceptions import (
    ApiNotFoundError,
    ApiPermissionError,
    CurrentValidationRunNotFoundError,
    CurrentVersionNotFoundError,
)
from app.lifecycle.repository import LifecycleRepository
from app.lifecycle.schemas import LifecycleResult, ValidationResultInput
from app.lifecycle.state_machine import ensure_transition_allowed


class LifecycleService:
    REQUIRED_VALIDATION_STAGES = frozenset(ValidationStage)

    def __init__(self, repository: LifecycleRepository) -> None:
        self.repository = repository

    def submit_api(
        self,
        api_id: int,
        actor_id: int,
        is_admin: bool = False,
    ) -> LifecycleResult:
        with self.repository.transaction():
            current_status = self._get_required_status(api_id)
            self._ensure_actor_can_manage(api_id, actor_id, is_admin)
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
            validation_run_id = self.repository.create_validation_run(
                api_id=api_id,
                version_id=version_id,
                overall_status=ValidationOverallStatus.RUNNING,
            )
            self.repository.create_version_event(
                api_id,
                version_id,
                VersionEventType.SUBMITTED_FOR_VALIDATION,
                ApiVersionStatus(current_status.value),
                ApiVersionStatus.VALIDATING,
                actor_id,
                "API submitted for validation.",
            )
            updated_at = self.repository.get_api_updated_at(api_id)

        return LifecycleResult(
            api_id=api_id,
            status=target_status,
            action=action,
            message="API submitted for validation.",
            version_id=version_id,
            validation_run_id=validation_run_id,
            updated_at=updated_at,
        )

    def handle_validation_result(
        self,
        api_id: int,
        validation_result: ValidationResultInput,
        validation_run_id: int | None = None,
    ) -> LifecycleResult:
        with self.repository.transaction():
            current_status = self._get_required_status(api_id)
            version_id = self._get_required_version_id(api_id)
            active_run_id = self.repository.get_active_validation_run_id(
                api_id,
                version_id,
                validation_run_id,
            )
            if active_run_id is None:
                raise CurrentValidationRunNotFoundError(api_id)

            stage_status = (
                ValidationStageStatus.PASSED
                if validation_result.passed
                else ValidationStageStatus.FAILED
            )
            self.repository.save_validation_result(
                validation_run_id=active_run_id,
                stage=validation_result.stage,
                status=stage_status,
                message=validation_result.message,
                error_detail=validation_result.error_detail,
            )
            stage_statuses = self.repository.get_validation_stage_statuses(active_run_id)

            if not validation_result.passed:
                target_status = ApiStatus.REJECTED
                overall_status = ValidationOverallStatus.FAILED
                action = LifecycleAction.VALIDATION_FAILED
            elif self._all_required_stages_passed(stage_statuses):
                target_status = ApiStatus.PUBLISHED
                overall_status = ValidationOverallStatus.PASSED
                action = LifecycleAction.VALIDATION_PASSED
            else:
                self.repository.update_validation_run_status(
                    active_run_id,
                    ValidationOverallStatus.PARTIAL,
                    completed=False,
                )
                updated_at = self.repository.get_api_updated_at(api_id)
                return LifecycleResult(
                    api_id=api_id,
                    status=ApiStatus.VALIDATING,
                    message="Validation stage recorded; awaiting remaining required stages.",
                    version_id=version_id,
                    validation_run_id=active_run_id,
                    updated_at=updated_at,
                )

            ensure_transition_allowed(current_status, target_status)
            self.repository.update_validation_run_status(
                active_run_id,
                overall_status,
                completed=True,
            )
            if target_status == ApiStatus.PUBLISHED:
                self.repository.archive_previous_version(api_id, version_id)
            self.repository.update_version_status(
                version_id,
                self._to_version_status(target_status),
            )
            restored_status: ApiStatus | None = None
            if target_status == ApiStatus.REJECTED:
                previous_published_id = self.repository.get_previous_published_version_id(
                    api_id,
                    version_id,
                )
                if previous_published_id is not None:
                    self.repository.restore_api_current_version(
                        api_id,
                        previous_published_id,
                        ApiStatus.PUBLISHED,
                    )
                    restored_status = ApiStatus.PUBLISHED
                else:
                    self.repository.update_api_status(api_id, target_status)
            else:
                self.repository.update_api_status(api_id, target_status)
            self.repository.create_version_event(
                api_id,
                version_id,
                (
                    VersionEventType.VALIDATION_PASSED
                    if validation_result.passed
                    else VersionEventType.VALIDATION_FAILED
                ),
                ApiVersionStatus.VALIDATING,
                self._to_version_status(target_status),
                None,
                validation_result.message or validation_result.error_detail,
            )
            updated_at = self.repository.get_api_updated_at(api_id)

        return LifecycleResult(
            api_id=api_id,
            status=target_status,
            action=action,
            message=(
                "Validation passed. API published successfully."
                if validation_result.passed
                else (
                    "Validation failed. Previous published version remains active."
                    if restored_status == ApiStatus.PUBLISHED
                    else "Validation failed. API rejected."
                )
            ),
            version_id=version_id,
            validation_run_id=active_run_id,
            updated_at=updated_at,
        )

    def withdraw_api(
        self,
        api_id: int,
        actor_id: int,
        reason: str | None = None,
        is_admin: bool = False,
    ) -> LifecycleResult:
        with self.repository.transaction():
            current_status = self._get_required_status(api_id)
            self._ensure_actor_can_manage(api_id, actor_id, is_admin)
            target_status = ApiStatus.WITHDRAWN
            ensure_transition_allowed(current_status, target_status)

            version_id = self._get_required_version_id(api_id)
            self.repository.mark_api_withdrawn(
                api_id=api_id,
                actor_id=actor_id,
                reason=reason,
            )
            self.repository.update_version_status(version_id, ApiVersionStatus.ARCHIVED)
            self.repository.create_version_event(
                api_id,
                version_id,
                VersionEventType.ARCHIVED,
                self._to_version_status(current_status),
                ApiVersionStatus.ARCHIVED,
                actor_id,
                reason,
            )
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

    def get_validation_context(self, api_id: int, version_id: int) -> dict:
        context = self.repository.get_validation_context(api_id, version_id)
        if context is None:
            raise CurrentVersionNotFoundError(api_id)
        return context

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

    def _ensure_actor_can_manage(
        self,
        api_id: int,
        actor_id: int,
        is_admin: bool,
    ) -> None:
        if is_admin:
            return
        if self.repository.get_api_submitted_by(api_id) != actor_id:
            raise ApiPermissionError()

    def _to_version_status(self, status: ApiStatus) -> ApiVersionStatus:
        if status == ApiStatus.WITHDRAWN:
            return ApiVersionStatus.ARCHIVED
        return ApiVersionStatus(status.value)

    def _all_required_stages_passed(
        self,
        statuses: dict[ValidationStage, ValidationStageStatus],
    ) -> bool:
        return all(
            statuses.get(stage) == ValidationStageStatus.PASSED
            for stage in self.REQUIRED_VALIDATION_STAGES
        )
