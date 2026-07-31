from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.core.security import get_current_user
from app.version_history import PostgresVersionHistoryRepository, VersionHistoryService
from app.version_history.exceptions import VersionHistoryError
from app.version_history.schemas import (
    EventPage,
    ConnectionImpactPage,
    MappingLifecycleStatus,
    VersionDetail,
    VersionEventType,
    VersionPage,
    VersionWriteRequest,
)

router = APIRouter(prefix="/apis", tags=["version history"])


def get_version_history_service() -> VersionHistoryService:
    return VersionHistoryService(PostgresVersionHistoryRepository())


def _raise_http_error(exc: VersionHistoryError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/{api_id}/versions", response_model=VersionPage)
def list_versions(
    api_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: VersionHistoryService = Depends(get_version_history_service),
    _current_user: dict = Depends(get_current_user),
) -> VersionPage:
    try:
        return VersionPage.model_validate(service.list_versions(api_id, page, page_size))
    except VersionHistoryError as exc:
        _raise_http_error(exc)


@router.get("/{api_id}/versions/{version_id}", response_model=VersionDetail)
def get_version(
    api_id: int,
    version_id: int,
    service: VersionHistoryService = Depends(get_version_history_service),
    _current_user: dict = Depends(get_current_user),
) -> VersionDetail:
    try:
        return VersionDetail.model_validate(service.get_version(api_id, version_id))
    except VersionHistoryError as exc:
        _raise_http_error(exc)


@router.get("/{api_id}/versions/{version_id}/specification")
def get_version_specification(
    api_id: int,
    version_id: int,
    service: VersionHistoryService = Depends(get_version_history_service),
    _current_user: dict = Depends(get_current_user),
) -> Response:
    try:
        specification = service.get_specification(api_id, version_id)
    except VersionHistoryError as exc:
        _raise_http_error(exc)
    media_type = (
        "application/xml"
        if str(specification["spec_type"]) == "WSDL"
        else "application/json"
    )
    return Response(content=specification["raw_content"] or "", media_type=media_type)


@router.get("/{api_id}/history", response_model=EventPage)
def list_version_events(
    api_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    version_id: int | None = Query(default=None),
    event_type: VersionEventType | None = Query(default=None),
    service: VersionHistoryService = Depends(get_version_history_service),
    _current_user: dict = Depends(get_current_user),
) -> EventPage:
    try:
        result = service.list_events(
            api_id,
            page,
            page_size,
            version_id,
            event_type,
        )
        return EventPage.model_validate(result)
    except VersionHistoryError as exc:
        _raise_http_error(exc)


@router.get("/{api_id}/connection-impacts", response_model=ConnectionImpactPage)
def list_connection_impacts(
    api_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    version_id: int | None = Query(default=None),
    lifecycle_status: MappingLifecycleStatus | None = Query(default=None),
    service: VersionHistoryService = Depends(get_version_history_service),
    _current_user: dict = Depends(get_current_user),
) -> ConnectionImpactPage:
    try:
        result = service.list_connection_impacts(
            api_id,
            page,
            page_size,
            version_id,
            lifecycle_status,
        )
        return ConnectionImpactPage.model_validate(result)
    except VersionHistoryError as exc:
        _raise_http_error(exc)


@router.post("/{api_id}/versions", response_model=VersionDetail, status_code=201)
def create_version(
    api_id: int,
    request: VersionWriteRequest,
    service: VersionHistoryService = Depends(get_version_history_service),
    current_user: dict = Depends(get_current_user),
) -> VersionDetail:
    try:
        return VersionDetail.model_validate(
            service.create_version(api_id, current_user, request)
        )
    except VersionHistoryError as exc:
        _raise_http_error(exc)


@router.put("/{api_id}/versions/{version_id}", response_model=VersionDetail)
def update_version(
    api_id: int,
    version_id: int,
    request: VersionWriteRequest,
    service: VersionHistoryService = Depends(get_version_history_service),
    current_user: dict = Depends(get_current_user),
) -> VersionDetail:
    try:
        return VersionDetail.model_validate(
            service.update_version(api_id, version_id, current_user, request)
        )
    except VersionHistoryError as exc:
        _raise_http_error(exc)
