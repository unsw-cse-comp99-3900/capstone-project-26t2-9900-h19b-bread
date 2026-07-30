from __future__ import annotations

from typing import Protocol

from app.connection_validation.schemas import (
    ConnectionValidationContext,
    ConnectionValidationDecision,
    ConnectionValidationRequest,
    EndpointVersion,
    FormatAlias,
    PayloadSchema,
)


class ConnectionValidationNotFoundError(LookupError):
    pass


class ConnectionValidationConflictError(ValueError):
    pass


class ConnectionValidationPermissionError(PermissionError):
    pass


class ConnectionValidationRepository(Protocol):
    def get_version(self, api_id: int, version_id: int) -> EndpointVersion | None:
        ...

    def get_schema(
        self,
        api_id: int,
        version_id: int,
        direction: str,
        schema_id: int | None = None,
    ) -> PayloadSchema | None:
        ...

    def list_format_aliases(self) -> list[FormatAlias]:
        ...

    def get_mapping_metadata(
        self,
        request: ConnectionValidationRequest,
        source_schema_id: int,
        target_schema_id: int,
    ) -> dict | None:
        ...

    def assert_actor_can_validate(
        self,
        source_api_id: int,
        target_api_id: int,
        enterprise_id: int,
        is_admin: bool,
    ) -> None:
        ...

    def create_run(
        self,
        request: ConnectionValidationRequest,
        created_by: int,
    ) -> int:
        ...

    def save_decision(
        self,
        run_id: int,
        request: ConnectionValidationRequest,
        context: ConnectionValidationContext,
        decision: ConnectionValidationDecision,
    ) -> int:
        ...
