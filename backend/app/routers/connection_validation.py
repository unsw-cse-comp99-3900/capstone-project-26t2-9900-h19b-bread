from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.connection_validation import (
    ConnectionValidationConflictError,
    ConnectionLifecycleResponse,
    ConnectionValidationNotFoundError,
    ConnectionValidationPermissionError,
    ConnectionValidationRequest,
    ConnectionValidationResponse,
    ConnectionValidationRunDetail,
    ConnectionValidationRunPage,
    PostgresConnectionValidationRepository,
)
from app.connection_validation.service import ConnectionValidationService
from app.core.security import require_role

router = APIRouter(prefix="/connection-validation", tags=["connection-validation"])
get_connection_validation_actor = require_role("PUBLISHER", "ADMIN")


def get_connection_validation_service() -> ConnectionValidationService:
    return ConnectionValidationService(PostgresConnectionValidationRepository())


def _not_found_detail(exc: ConnectionValidationNotFoundError) -> dict[str, str]:
    return {"reason_code": exc.reason_code, "message": str(exc)}


@router.post("/runs", response_model=ConnectionValidationResponse)
def validate_connection_endpoint(
    request: ConnectionValidationRequest,
    service: ConnectionValidationService = Depends(get_connection_validation_service),
    current_user: dict[str, Any] = Depends(get_connection_validation_actor),
) -> ConnectionValidationResponse:
    try:
        return service.validate(
            request,
            actor_id=current_user["user_id"],
            enterprise_id=current_user["enterprise_id"],
            is_admin=str(current_user["role"]).upper() == "ADMIN",
        )
    except ConnectionValidationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_not_found_detail(exc)) from exc
    except ConnectionValidationPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConnectionValidationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=ConnectionValidationRunDetail)
def get_validation_run_endpoint(
    run_id: int,
    service: ConnectionValidationService = Depends(get_connection_validation_service),
    current_user: dict[str, Any] = Depends(get_connection_validation_actor),
) -> ConnectionValidationRunDetail:
    try:
        return service.get_run(
            run_id,
            enterprise_id=current_user["enterprise_id"],
            is_admin=str(current_user["role"]).upper() == "ADMIN",
        )
    except ConnectionValidationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_not_found_detail(exc)) from exc
    except ConnectionValidationPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/connections/{mapping_id}", response_model=ConnectionLifecycleResponse)
def get_connection_endpoint(
    mapping_id: int,
    service: ConnectionValidationService = Depends(get_connection_validation_service),
    current_user: dict[str, Any] = Depends(get_connection_validation_actor),
) -> ConnectionLifecycleResponse:
    try:
        return service.get_connection(
            mapping_id,
            enterprise_id=current_user["enterprise_id"],
            is_admin=str(current_user["role"]).upper() == "ADMIN",
        )
    except ConnectionValidationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_not_found_detail(exc)) from exc
    except ConnectionValidationPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get(
    "/connections/{mapping_id}/runs",
    response_model=ConnectionValidationRunPage,
)
def list_connection_runs_endpoint(
    mapping_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: ConnectionValidationService = Depends(get_connection_validation_service),
    current_user: dict[str, Any] = Depends(get_connection_validation_actor),
) -> ConnectionValidationRunPage:
    try:
        return service.list_connection_runs(
            mapping_id,
            page,
            page_size,
            enterprise_id=current_user["enterprise_id"],
            is_admin=str(current_user["role"]).upper() == "ADMIN",
        )
    except ConnectionValidationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_not_found_detail(exc)) from exc
    except ConnectionValidationPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/connections/{mapping_id}/deprecate",
    response_model=ConnectionLifecycleResponse,
)
def deprecate_connection_endpoint(
    mapping_id: int,
    service: ConnectionValidationService = Depends(get_connection_validation_service),
    current_user: dict[str, Any] = Depends(get_connection_validation_actor),
) -> ConnectionLifecycleResponse:
    try:
        return service.deprecate_connection(
            mapping_id,
            enterprise_id=current_user["enterprise_id"],
            is_admin=str(current_user["role"]).upper() == "ADMIN",
        )
    except ConnectionValidationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_not_found_detail(exc)) from exc
    except ConnectionValidationPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConnectionValidationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
