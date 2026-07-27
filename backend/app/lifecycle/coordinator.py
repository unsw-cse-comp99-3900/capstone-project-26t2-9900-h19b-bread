from collections.abc import Callable

from app.lifecycle.enums import ApiStatus, ValidationStage
from app.lifecycle.schemas import LifecycleResult, ValidationResultInput
from app.lifecycle.service import LifecycleService
from app.schemas.validation_schema import (
    Protocol,
    ValidationRequest,
    ValidationResponse,
    ValidationStatus,
)
from app.services.validation_service import validate_specification

ValidateFn = Callable[[ValidationRequest], ValidationResponse]


def _default_validate(request: ValidationRequest) -> ValidationResponse:
    return validate_specification(request)


class SubmissionCoordinator:
    """Coordinates the submit -> validate -> publish/reject workflow.

    The lifecycle layer only consumes the validation outcome; it does not
    implement any parsing or validation rules itself.
    """

    def __init__(
        self,
        service: LifecycleService,
        validate: ValidateFn = _default_validate,
    ) -> None:
        self.service = service
        self.validate = validate

    def submit_only(
        self,
        api_id: int,
        actor_id: int,
        is_admin: bool = False,
    ) -> LifecycleResult:
        return self.service.submit_api(
            api_id=api_id,
            actor_id=actor_id,
            is_admin=is_admin,
        )

    def submit_and_validate(
        self,
        api_id: int,
        actor_id: int,
        protocol: Protocol,
        spec_content: str,
        is_admin: bool = False,
    ) -> LifecycleResult:
        result = self.service.submit_api(
            api_id=api_id,
            actor_id=actor_id,
            is_admin=is_admin,
        )

        context = self.service.get_validation_context(api_id, result.version_id)
        response = self.validate(
            ValidationRequest(
                protocol=Protocol(str(context.get("protocol_type") or protocol)),
                spec_content=str(context.get("spec_content") or spec_content),
                auth_method=context.get("auth_method"),
                endpoint_url=context.get("endpoint_url"),
                input_format=context.get("input_format"),
                output_format=context.get("output_format"),
                capability_category=context.get("capability_category"),
            )
        )
        for stage_result in response.stages:
            if stage_result.status == ValidationStatus.NOT_RUN:
                continue
            stage = ValidationStage(stage_result.stage.value.upper())
            stage_errors = [
                error.message
                for error in response.errors
                if error.stage is not None and error.stage.value == stage_result.stage.value
            ]
            result = self.service.handle_validation_result(
                api_id=api_id,
                validation_run_id=result.validation_run_id,
                validation_result=ValidationResultInput(
                    passed=stage_result.status == ValidationStatus.PASS,
                    stage=stage,
                    message=f"{stage.value} {stage_result.status.value}.",
                    error_detail="; ".join(stage_errors) or None,
                ),
            )
            if result.status in {ApiStatus.PUBLISHED, ApiStatus.REJECTED}:
                break
        return result
