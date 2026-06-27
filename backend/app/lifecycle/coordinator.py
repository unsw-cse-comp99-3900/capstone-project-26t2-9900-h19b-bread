from collections.abc import Callable

from app.lifecycle.enums import ValidationStage
from app.lifecycle.schemas import LifecycleResult, ValidationResultInput
from app.lifecycle.service import LifecycleService
from app.schemas.validation_schema import (
    Protocol,
    ValidationRequest,
    ValidationResponse,
    ValidationStatus,
)
from app.services.validation_service import validate_specification

ValidateFn = Callable[[Protocol, str], ValidationResponse]


def _default_validate(protocol: Protocol, spec_content: str) -> ValidationResponse:
    return validate_specification(
        ValidationRequest(protocol=protocol, spec_content=spec_content)
    )


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

    def submit_only(self, api_id: int, actor_id: int) -> LifecycleResult:
        return self.service.submit_api(api_id=api_id, actor_id=actor_id)

    def submit_and_validate(
        self,
        api_id: int,
        actor_id: int,
        protocol: Protocol,
        spec_content: str,
    ) -> LifecycleResult:
        self.service.submit_api(api_id=api_id, actor_id=actor_id)

        response = self.validate(protocol, spec_content)
        passed = response.overall_status == ValidationStatus.PASS
        error_detail = (
            "; ".join(error.message for error in response.errors)
            if response.errors
            else None
        )

        validation_result = ValidationResultInput(
            passed=passed,
            stage=ValidationStage.SPECIFICATION_VALIDATION,
            message=(
                "Specification validation passed."
                if passed
                else "Specification validation failed."
            ),
            error_detail=error_detail,
        )
        return self.service.handle_validation_result(
            api_id=api_id,
            validation_result=validation_result,
        )
