from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.connection_validation import (
    ConnectionValidationConflictError,
    ConnectionLifecycleResponse,
    ConnectionValidationNotFoundError,
    ConnectionValidationPermissionError,
    ConnectionValidationRequest,
    ConnectionValidationResponse,
    PostgresConnectionValidationRepository,
)
from app.connection_validation.service import ConnectionValidationService
from app.core.security import require_role

router = APIRouter(prefix="/connection-validation", tags=["connection-validation"])
get_connection_validation_actor = require_role("PUBLISHER", "ADMIN")


def get_connection_validation_service() -> ConnectionValidationService:
    return ConnectionValidationService(PostgresConnectionValidationRepository())


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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConnectionValidationPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConnectionValidationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ConnectionValidationPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ConnectionValidationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
