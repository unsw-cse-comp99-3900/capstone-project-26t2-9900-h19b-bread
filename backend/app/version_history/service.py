from app.version_history.exceptions import (
    ApiNotFoundError,
    VersionConflictError,
    VersionNotFoundError,
    VersionPermissionError,
)
from app.version_history.repository import PostgresVersionHistoryRepository
from app.version_history.schemas import VersionWriteRequest


class VersionHistoryService:
    def __init__(self, repository: PostgresVersionHistoryRepository) -> None:
        self.repository = repository

    def list_versions(self, api_id: int, page: int, page_size: int) -> dict:
        self._require_api(api_id)
        items, total = self.repository.list_versions(api_id, page_size, (page - 1) * page_size)
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def get_version(self, api_id: int, version_id: int) -> dict:
        self._require_api(api_id)
        version = self.repository.get_version_detail(api_id, version_id)
        if version is None:
            raise VersionNotFoundError(api_id, version_id)
        return version

    def get_specification(self, api_id: int, version_id: int) -> dict:
        self._require_api(api_id)
        specification = self.repository.get_specification(api_id, version_id)
        if specification is None:
            raise VersionNotFoundError(api_id, version_id)
        return specification

    def list_events(
        self,
        api_id: int,
        page: int,
        page_size: int,
        version_id: int | None,
        event_type: str | None,
    ) -> dict:
        self._require_api(api_id)
        if version_id is not None and self.repository.get_version(api_id, version_id) is None:
            raise VersionNotFoundError(api_id, version_id)
        items, total = self.repository.list_events(
            api_id, page_size, (page - 1) * page_size, version_id, event_type
        )
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def list_connection_impacts(
        self,
        api_id: int,
        page: int,
        page_size: int,
        version_id: int | None,
        lifecycle_status: str | None,
    ) -> dict:
        self._require_api(api_id)
        if version_id is not None and self.repository.get_version(api_id, version_id) is None:
            raise VersionNotFoundError(api_id, version_id)
        items, total = self.repository.list_connection_impacts(
            api_id,
            page_size,
            (page - 1) * page_size,
            version_id,
            lifecycle_status,
        )
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    def create_version(self, api_id: int, current_user: dict, data: VersionWriteRequest) -> dict:
        with self.repository.transaction():
            api = self.repository.get_api(api_id, for_update=True)
            if api is None:
                raise ApiNotFoundError(api_id)
            self._require_manager(api, current_user)
            if str(api["status"]) == "WITHDRAWN":
                raise VersionConflictError("A withdrawn API cannot receive a new version.")
            previous_id = api["current_version_id"]
            if previous_id is not None:
                current = self.repository.get_version(api_id, previous_id)
                if current is not None and str(current["status"]) in {"DRAFT", "VALIDATING"}:
                    raise VersionConflictError("Finish or discard the current draft before creating a new version.")
            existing_versions, _total = self.repository.list_versions(api_id, 100, 0)
            if any(str(version["version_number"]) == data.version_number for version in existing_versions):
                raise VersionConflictError(
                    f"Version number '{data.version_number}' already exists. Use a new version number."
                )
            version_id = self.repository.create_version(
                api_id, current_user["user_id"], previous_id, data
            )
        return self.get_version(api_id, version_id)

    def update_version(
        self,
        api_id: int,
        version_id: int,
        current_user: dict,
        data: VersionWriteRequest,
    ) -> dict:
        with self.repository.transaction():
            api = self.repository.get_api(api_id, for_update=True)
            if api is None:
                raise ApiNotFoundError(api_id)
            self._require_manager(api, current_user)
            version = self.repository.get_version(api_id, version_id)
            if version is None:
                raise VersionNotFoundError(api_id, version_id)
            if api["current_version_id"] != version_id or str(version["status"]) != "DRAFT":
                raise VersionConflictError("Only the current DRAFT version can be updated.")
            self.repository.update_version(
                api_id, version_id, current_user["user_id"], data
            )
        return self.get_version(api_id, version_id)

    def _require_api(self, api_id: int) -> dict:
        api = self.repository.get_api(api_id)
        if api is None:
            raise ApiNotFoundError(api_id)
        return api

    @staticmethod
    def _require_manager(api: dict, current_user: dict) -> None:
        is_creator = api["submitted_by"] == current_user["user_id"]
        is_admin = str(current_user.get("role", "")).upper() == "ADMIN"
        if not is_creator and not is_admin:
            raise VersionPermissionError()
