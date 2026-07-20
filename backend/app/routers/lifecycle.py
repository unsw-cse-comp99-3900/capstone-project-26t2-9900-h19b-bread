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

try:
    from app.core.security import require_role
except ModuleNotFoundError as exc:
    if exc.name != "app.core.security":
        raise

    def get_lifecycle_actor() -> dict | None:
        return None

    def get_validation_callback_actor() -> dict | None:
        return None
else:
    get_lifecycle_actor = require_role("PUBLISHER", "ADMIN")
    get_validation_callback_actor = require_role("ADMIN")


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
    validation_run_id: int
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


def _resolve_actor_id(body_actor_id: int, current_user: dict | None) -> int:
    if current_user is not None:
        return current_user["user_id"]
    return body_actor_id


def _is_admin(current_user: dict | None) -> bool:
    return current_user is not None and str(current_user.get("role", "")).upper() == "ADMIN"


@router.post("/{api_id}/submit", response_model=LifecycleResponse)
def submit_api_endpoint(
    api_id: int,
    request: SubmitRequest | None = Body(default=None),
    coordinator: SubmissionCoordinator = Depends(get_submission_coordinator),
    current_user: dict | None = Depends(get_lifecycle_actor),
) -> LifecycleResponse:
    body = request or SubmitRequest()
    actor_id = _resolve_actor_id(body.actor_id, current_user)
    if body.spec_content is not None:
        result = coordinator.submit_and_validate(
            api_id=api_id,
            actor_id=actor_id,
            protocol=body.protocol,
            spec_content=body.spec_content,
            is_admin=_is_admin(current_user),
        )
    else:
        result = coordinator.submit_only(
            api_id=api_id,
            actor_id=actor_id,
            is_admin=_is_admin(current_user),
        )
    return _to_response(result)


@router.post("/{api_id}/validation-result", response_model=LifecycleResponse)
def validation_result_endpoint(
    api_id: int,
    request: ValidationResultRequest,
    service: LifecycleService = Depends(get_lifecycle_service),
    _current_user: dict | None = Depends(get_validation_callback_actor),
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
        validation_run_id=request.validation_run_id,
    )
    return _to_response(result)


@router.post("/{api_id}/withdraw", response_model=LifecycleResponse)
def withdraw_api_endpoint(
    api_id: int,
    request: WithdrawRequest | None = Body(default=None),
    service: LifecycleService = Depends(get_lifecycle_service),
    current_user: dict | None = Depends(get_lifecycle_actor),
) -> LifecycleResponse:
    body = request or WithdrawRequest()
    result = service.withdraw_api(
        api_id=api_id,
        actor_id=_resolve_actor_id(body.actor_id, current_user),
        reason=body.reason,
        is_admin=_is_admin(current_user),
    )
    return _to_response(result)


@router.get("/{api_id}/status", response_model=ApiStatusResponse)
def get_status_endpoint(
    api_id: int,
    service: LifecycleService = Depends(get_lifecycle_service),
    _current_user: dict | None = Depends(get_lifecycle_actor),
) -> ApiStatusResponse:
    result = service.get_status(api_id)
    return ApiStatusResponse(
        api_id=result.api_id,
        status=result.status,
        updated_at=result.updated_at,
    )
