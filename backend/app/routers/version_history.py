from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.version_history import (
    HistoryAccessDeniedError,
    PostgresVersionHistoryRepository,
    VersionConflictError,
    VersionHistoryService,
    VersionNotFoundError,
)
from app.version_history.schemas import (
    HistoryAccessRequest,
    HistoryAccessResponse,
    LifecycleHistoryResponse,
    SpecificationContentResponse,
    SpecificationMetadataResponse,
    ValidationRunResponse,
    VersionAuthResponse,
    VersionDetailResponse,
    VersionListResponse,
    VersionMutationResponse,
    VersionWriteRequest,
)

router = APIRouter(prefix="/apis", tags=["version-history"])


def get_version_history_service() -> VersionHistoryService:
    return VersionHistoryService(PostgresVersionHistoryRepository())


def _raise_http_error(exc: Exception) -> None:
    if isinstance(exc, VersionNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, HistoryAccessDeniedError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, VersionConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.get("/{api_id}/versions", response_model=VersionListResponse)
def list_versions(
    api_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VersionHistoryService = Depends(get_version_history_service),
) -> VersionListResponse:
    try:
        total, items = service.list_versions(api_id, current_user, limit, offset)
        return VersionListResponse(api_id=api_id, total=total, limit=limit, offset=offset, items=items)
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/{api_id}/versions/{version_id}", response_model=VersionDetailResponse)
def get_version(
    api_id: int,
    version_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VersionHistoryService = Depends(get_version_history_service),
) -> VersionDetailResponse:
    try:
        version = service.get_version(api_id, version_id, current_user)
        version_fields = {
            key: value for key, value in version.items() if key != "validation_runs"
        }
        return VersionDetailResponse(
            **version_fields,
            authentication=VersionAuthResponse(
                auth_method=version["auth_method"],
                auth_description=version["auth_description"],
                security_scheme_name=version["security_scheme_name"],
                is_complete=version["auth_is_complete"],
            ),
            specification=SpecificationMetadataResponse(**version),
            validation_runs=[ValidationRunResponse(**run) for run in version["validation_runs"]],
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.get(
    "/{api_id}/versions/{version_id}/specification",
    response_model=SpecificationContentResponse,
)
def get_version_specification(
    api_id: int,
    version_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VersionHistoryService = Depends(get_version_history_service),
) -> SpecificationContentResponse:
    try:
        return SpecificationContentResponse(
            **service.get_specification(api_id, version_id, current_user)
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/{api_id}/history", response_model=LifecycleHistoryResponse)
def list_lifecycle_history(
    api_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    version_id: int | None = Query(default=None),
    action: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VersionHistoryService = Depends(get_version_history_service),
) -> LifecycleHistoryResponse:
    try:
        total, items = service.list_events(
            api_id,
            current_user,
            limit,
            offset,
            version_id,
            action,
        )
        return LifecycleHistoryResponse(
            api_id=api_id,
            total=total,
            limit=limit,
            offset=offset,
            items=items,
        )
    except Exception as exc:
        _raise_http_error(exc)


@router.post(
    "/{api_id}/versions",
    response_model=VersionMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    api_id: int,
    request: VersionWriteRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VersionHistoryService = Depends(get_version_history_service),
) -> VersionMutationResponse:
    try:
        version_id = service.create_version(api_id, current_user, request.to_write())
        return VersionMutationResponse(api_id=api_id, version_id=version_id, status="DRAFT")
    except Exception as exc:
        _raise_http_error(exc)


@router.put("/{api_id}/versions/{version_id}", response_model=VersionMutationResponse)
def update_draft_version(
    api_id: int,
    version_id: int,
    request: VersionWriteRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VersionHistoryService = Depends(get_version_history_service),
) -> VersionMutationResponse:
    try:
        service.update_draft(api_id, version_id, current_user, request.to_write())
        return VersionMutationResponse(api_id=api_id, version_id=version_id, status="DRAFT")
    except Exception as exc:
        _raise_http_error(exc)


@router.get("/{api_id}/history-access", response_model=HistoryAccessResponse)
def get_history_access(
    api_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VersionHistoryService = Depends(get_version_history_service),
) -> HistoryAccessResponse:
    try:
        return HistoryAccessResponse(**service.get_access_policy(api_id, current_user))
    except Exception as exc:
        _raise_http_error(exc)


@router.put("/{api_id}/history-access", response_model=HistoryAccessResponse)
def replace_history_access(
    api_id: int,
    request: HistoryAccessRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: VersionHistoryService = Depends(get_version_history_service),
) -> HistoryAccessResponse:
    try:
        policy = service.replace_access_policy(
            api_id,
            current_user,
            request.visibility,
            request.allowed_user_ids,
        )
        return HistoryAccessResponse(**policy)
    except Exception as exc:
        _raise_http_error(exc)
