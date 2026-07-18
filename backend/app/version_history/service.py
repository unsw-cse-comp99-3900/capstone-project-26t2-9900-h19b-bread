from typing import Any

from psycopg.errors import UniqueViolation

from app.version_history.exceptions import (
    HistoryAccessDeniedError,
    VersionConflictError,
    VersionNotFoundError,
)
from app.version_history.models import VersionWrite
from app.version_history.repository import PostgresVersionHistoryRepository


class VersionHistoryService:
    def __init__(self, repository: PostgresVersionHistoryRepository) -> None:
        self.repository = repository

    def create_version(self, api_id: int, actor: dict[str, Any], data: VersionWrite) -> int:
        self._validate_input(data)
        try:
            with self.repository.transaction():
                api = self._get_managed_api(api_id, actor)
                current_status = self.repository.get_version_status(api["current_version_id"])
                if current_status in {"DRAFT", "VALIDATING"}:
                    raise VersionConflictError(
                        f"API {api_id} already has a {current_status} current version"
                    )
                return self.repository.create_version(
                    api_id=api_id,
                    actor_id=actor["user_id"],
                    previous_status=str(api["status"]),
                    data=data,
                )
        except UniqueViolation as exc:
            raise VersionConflictError(
                f"Version number '{data.version_number}' already exists for API {api_id}"
            ) from exc

    def list_versions(self, api_id: int, limit: int, offset: int) -> tuple[int, list[dict[str, Any]]]:
        self._get_readable_api(api_id)
        return self.repository.list_versions(api_id, limit, offset)

    def get_version(self, api_id: int, version_id: int) -> dict[str, Any]:
        self._get_readable_api(api_id)
        version = self.repository.get_version_detail(api_id, version_id)
        if version is None:
            raise VersionNotFoundError(api_id, version_id)
        return version

    def get_specification(self, api_id: int, version_id: int) -> dict[str, Any]:
        self._get_readable_api(api_id)
        specification = self.repository.get_specification(api_id, version_id)
        if specification is None:
            raise VersionNotFoundError(api_id, version_id)
        return specification

    def list_events(
        self,
        api_id: int,
        limit: int,
        offset: int,
        version_id: int | None,
        action: str | None,
    ) -> tuple[int, list[dict[str, Any]]]:
        self._get_readable_api(api_id)
        allowed_actions = {
            "API_CREATED",
            "VERSION_CREATED",
            "SUBMIT",
            "RESUBMIT",
            "VALIDATION_PASSED",
            "VALIDATION_FAILED",
            "WITHDRAW",
        }
        normalized_action = action.strip().upper() if action is not None else None
        if normalized_action is not None and normalized_action not in allowed_actions:
            raise ValueError(f"Unsupported lifecycle action '{action}'")
        return self.repository.list_events(
            api_id,
            limit,
            offset,
            version_id,
            normalized_action,
        )

    def update_draft(
        self,
        api_id: int,
        version_id: int,
        actor: dict[str, Any],
        data: VersionWrite,
    ) -> None:
        self._validate_input(data)
        try:
            with self.repository.transaction():
                api = self._get_managed_api(api_id, actor)
                if api["current_version_id"] != version_id:
                    raise VersionNotFoundError(api_id, version_id)
                if self.repository.get_version_status(version_id) != "DRAFT":
                    raise VersionConflictError("Only the current DRAFT version can be updated")
                self.repository.update_draft(api_id, version_id, data)
        except UniqueViolation as exc:
            raise VersionConflictError(
                f"Version number '{data.version_number}' already exists for API {api_id}"
            ) from exc

    def _get_managed_api(self, api_id: int, actor: dict[str, Any]) -> dict[str, Any]:
        api = self.repository.lock_api(api_id)
        if api is None:
            raise VersionNotFoundError(api_id)
        is_creator = api["submitted_by"] == actor["user_id"]
        is_enterprise_admin = (
            actor["role"] == "ADMIN" and api["enterprise_id"] == actor["enterprise_id"]
        )
        if not (is_creator or is_enterprise_admin):
            raise HistoryAccessDeniedError("Only the creator or enterprise admin can manage versions")
        return api

    def _get_readable_api(self, api_id: int) -> dict[str, Any]:
        api = self.repository.get_api_context(api_id)
        if api is None:
            raise VersionNotFoundError(api_id)
        return api

    def _validate_input(self, data: VersionWrite) -> None:
        version_number = data.version_number.strip()
        if not version_number or len(version_number) > 50:
            raise ValueError("version_number must contain 1 to 50 characters")
        if not data.api_name.strip():
            raise ValueError("api_name is required")
        if not data.endpoint_url.strip():
            raise ValueError("endpoint_url is required")
        if not data.input_format.strip() or not data.output_format.strip():
            raise ValueError("input_format and output_format are required")
        if not data.capability_category.strip():
            raise ValueError("capability_category is required")
        if not data.spec_content.strip():
            raise ValueError("spec_content is required")
