import json
from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from app.lifecycle import (
    ApiStatus,
    LifecycleAction,
    LifecycleResult,
    LifecycleService,
    PostgresLifecycleRepository,
    ValidationResultInput,
    ValidationStage,
)
from app.lifecycle.coordinator import SubmissionCoordinator
from app.schemas.validation_schema import Protocol

router = APIRouter(prefix="/apis", tags=["lifecycle"])


def get_lifecycle_service() -> LifecycleService:
    """Build a per-request service so repository connection state is not shared."""
    return LifecycleService(PostgresLifecycleRepository())


def get_submission_coordinator() -> SubmissionCoordinator:
    return SubmissionCoordinator(LifecycleService(PostgresLifecycleRepository()))


class SubmitRequest(BaseModel):
    actor_id: int = 0
    protocol: Protocol = Protocol.REST
    spec_content: str | None = None


class ValidationResultRequest(BaseModel):
    passed: bool | None = None
    overall_status: str | None = None
    stage: str = ValidationStage.SPECIFICATION_VALIDATION.value
    result_json: dict | None = None
    error_message: str | None = None


class WithdrawRequest(BaseModel):
    actor_id: int = 0
    reason: str | None = None


class LifecycleResponse(BaseModel):
    api_id: int
    status: ApiStatus
    message: str
    updated_at: datetime | None = None
    action: LifecycleAction | None = None
    version_id: int | None = None
    validation_run_id: int | None = None


class ApiStatusResponse(BaseModel):
    api_id: int
    status: ApiStatus
    updated_at: datetime | None = None


def _to_response(result: LifecycleResult) -> LifecycleResponse:
    return LifecycleResponse(
        api_id=result.api_id,
        status=result.status,
        message=result.message,
        updated_at=result.updated_at,
        action=result.action,
        version_id=result.version_id,
        validation_run_id=result.validation_run_id,
    )


def _parse_validation_stage(stage: str) -> ValidationStage:
    normalized = stage.strip().replace("-", "_").upper()
    try:
        return ValidationStage(normalized)
    except ValueError as exc:
        allowed = ", ".join(validation_stage.value for validation_stage in ValidationStage)
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported validation stage '{stage}'. Expected one of: {allowed}",
        ) from exc


def _parse_validation_passed(request: ValidationResultRequest) -> bool:
    if request.passed is not None:
        return request.passed

    if request.overall_status is None:
        raise HTTPException(
            status_code=422,
            detail="Either 'passed' or 'overall_status' is required.",
        )

    normalized = request.overall_status.strip().lower()
    if normalized in {"pass", "passed", "success", "validated", "published"}:
        return True
    if normalized in {"fail", "failed", "rejected"}:
        return False

    raise HTTPException(
        status_code=422,
        detail=(
            "Unsupported overall_status "
            f"'{request.overall_status}'. Expected pass/fail."
        ),
    )


@router.post("/{api_id}/submit", response_model=LifecycleResponse)
def submit_api_endpoint(
    api_id: int,
    request: SubmitRequest | None = Body(default=None),
    coordinator: SubmissionCoordinator = Depends(get_submission_coordinator),
) -> LifecycleResponse:
    body = request or SubmitRequest()
    if body.spec_content is not None:
        result = coordinator.submit_and_validate(
            api_id=api_id,
            actor_id=body.actor_id,
            protocol=body.protocol,
            spec_content=body.spec_content,
        )
    else:
        result = coordinator.submit_only(api_id=api_id, actor_id=body.actor_id)
    return _to_response(result)


@router.post("/{api_id}/validation-result", response_model=LifecycleResponse)
def validation_result_endpoint(
    api_id: int,
    request: ValidationResultRequest,
    service: LifecycleService = Depends(get_lifecycle_service),
) -> LifecycleResponse:
    message = json.dumps(request.result_json) if request.result_json is not None else None
    validation_result = ValidationResultInput(
        passed=_parse_validation_passed(request),
        stage=_parse_validation_stage(request.stage),
        message=message,
        error_detail=request.error_message,
    )
    result = service.handle_validation_result(
        api_id=api_id,
        validation_result=validation_result,
    )
    return _to_response(result)


@router.post("/{api_id}/withdraw", response_model=LifecycleResponse)
def withdraw_api_endpoint(
    api_id: int,
    request: WithdrawRequest | None = Body(default=None),
    service: LifecycleService = Depends(get_lifecycle_service),
) -> LifecycleResponse:
    body = request or WithdrawRequest()
    result = service.withdraw_api(
        api_id=api_id,
        actor_id=body.actor_id,
        reason=body.reason,
    )
    return _to_response(result)


@router.get("/{api_id}/status", response_model=ApiStatusResponse)
def get_status_endpoint(
    api_id: int,
    service: LifecycleService = Depends(get_lifecycle_service),
) -> ApiStatusResponse:
    result = service.get_status(api_id)
    return ApiStatusResponse(
        api_id=result.api_id,
        status=result.status,
        updated_at=result.updated_at,
    )
