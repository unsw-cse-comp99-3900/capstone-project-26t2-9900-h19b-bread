from app.lifecycle.coordinator import SubmissionCoordinator
from app.lifecycle.enums import ApiStatus, ValidationStage
from app.lifecycle.schemas import LifecycleResult
from app.schemas.validation_schema import (
    Protocol,
    StageResult,
    ValidationResponse,
    ValidationStage as ResponseStage,
    ValidationStatus,
)


class FakeLifecycleService:
    def __init__(self) -> None:
        self.results = []

    def submit_api(self, api_id, actor_id, is_admin=False):
        return LifecycleResult(
            api_id=api_id,
            status=ApiStatus.VALIDATING,
            message="submitted",
            version_id=7,
            validation_run_id=90,
        )

    def handle_validation_result(
        self,
        api_id,
        validation_result,
        validation_run_id=None,
    ):
        self.results.append((validation_run_id, validation_result))
        status = (
            ApiStatus.REJECTED
            if not validation_result.passed
            else (
                ApiStatus.PUBLISHED
                if len(self.results) == 3
                else ApiStatus.VALIDATING
            )
        )
        return LifecycleResult(
            api_id=api_id,
            status=status,
            message="stage handled",
            version_id=7,
            validation_run_id=90,
        )


def test_coordinator_forwards_all_passed_stages_to_one_run() -> None:
    service = FakeLifecycleService()
    response = ValidationResponse(
        overall_status=ValidationStatus.PASS,
        stages=[
            StageResult(stage=stage, status=ValidationStatus.PASS)
            for stage in ResponseStage
        ],
        errors=[],
    )
    coordinator = SubmissionCoordinator(service, validate=lambda protocol, spec: response)

    result = coordinator.submit_and_validate(1, 42, Protocol.REST, "spec")

    assert result.status == ApiStatus.PUBLISHED
    assert [run_id for run_id, _ in service.results] == [90, 90, 90]
    assert [item.stage for _, item in service.results] == list(ValidationStage)


def test_coordinator_stops_after_failed_stage() -> None:
    service = FakeLifecycleService()
    response = ValidationResponse(
        overall_status=ValidationStatus.FAIL,
        stages=[
            StageResult(
                stage=ResponseStage.SPECIFICATION_VALIDATION,
                status=ValidationStatus.PASS,
            ),
            StageResult(
                stage=ResponseStage.DOMAIN_COMPLIANCE_VALIDATION,
                status=ValidationStatus.FAIL,
            ),
            StageResult(
                stage=ResponseStage.SECURITY_VALIDATION,
                status=ValidationStatus.NOT_RUN,
            ),
        ],
        errors=[],
    )
    coordinator = SubmissionCoordinator(service, validate=lambda protocol, spec: response)

    result = coordinator.submit_and_validate(1, 42, Protocol.REST, "spec")

    assert result.status == ApiStatus.REJECTED
    assert len(service.results) == 2
    assert service.results[-1][1].stage == ValidationStage.DOMAIN_COMPLIANCE_VALIDATION
