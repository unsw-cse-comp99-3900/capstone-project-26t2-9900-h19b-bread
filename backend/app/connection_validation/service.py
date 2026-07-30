from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.connection_validation.pipeline import ConnectionValidationPipeline
from app.connection_validation.repository import (
    ConnectionValidationConflictError,
    ConnectionValidationNotFoundError,
    ConnectionValidationPermissionError,
    ConnectionValidationRepository,
)
from app.connection_validation.schemas import (
    ConnectionValidationContext,
    ConnectionLifecycleResponse,
    ConnectionValidationRequest,
    ConnectionValidationResponse,
    MappingContext,
)
from app.services.schema_mapping.compatibility_engine import compare_schemas
from app.services.schema_mapping.data_validator import validate_data
from app.services.schema_mapping.repository import PostgresSchemaMappingRepository
from app.services.schema_mapping.schema_transformer import build_transformer


MappingLoader = Callable[[int], dict[str, Any] | None]


class ConnectionValidationService:
    def __init__(
        self,
        repository: ConnectionValidationRepository,
        *,
        mapping_loader: MappingLoader | None = None,
        pipeline: ConnectionValidationPipeline | None = None,
    ) -> None:
        self.repository = repository
        self.mapping_loader = mapping_loader or PostgresSchemaMappingRepository().get_mapping
        self.pipeline = pipeline or ConnectionValidationPipeline(compare_schemas, validate_data)

    def validate(
        self,
        request: ConnectionValidationRequest,
        *,
        actor_id: int,
        enterprise_id: int,
        is_admin: bool = False,
    ) -> ConnectionValidationResponse:
        source = self.repository.get_version(
            request.source_api_id,
            request.source_version_id,
        )
        if source is None:
            raise ConnectionValidationNotFoundError(
                f"Source API {request.source_api_id} version {request.source_version_id} was not found."
            )
        target = self.repository.get_version(
            request.target_api_id,
            request.target_version_id,
        )
        if target is None:
            raise ConnectionValidationNotFoundError(
                f"Target API {request.target_api_id} version {request.target_version_id} was not found."
            )

        self.repository.assert_actor_can_validate(
            request.source_api_id,
            request.target_api_id,
            enterprise_id,
            is_admin,
        )
        source_schema = self.repository.get_schema(
            request.source_api_id,
            request.source_version_id,
            "OUTPUT",
            request.source_schema_id,
        )
        target_schema = self.repository.get_schema(
            request.target_api_id,
            request.target_version_id,
            "INPUT",
            request.target_schema_id,
        )

        run_id = self.repository.create_run(request, actor_id)
        try:
            mapping = None
            if (
                source.status == "PUBLISHED"
                and target.status == "PUBLISHED"
                and source_schema is not None
                and target_schema is not None
            ):
                metadata = self.repository.prepare_mapping(
                    request,
                    source_schema,
                    target_schema,
                )
                detail = self.mapping_loader(metadata["mapping_id"])
                if detail is not None:
                    mapping = MappingContext(
                        mapping_id=metadata["mapping_id"],
                        lifecycle_status=metadata["lifecycle_status"],
                        completeness=metadata["completeness"],
                        transform=build_transformer(detail["mapping"]),
                    )

            context = ConnectionValidationContext(
                source=source,
                target=target,
                source_schema=source_schema,
                target_schema=target_schema,
                aliases=self.repository.list_format_aliases(),
                mapping=mapping,
                sample_data=request.sample_data,
            )
            decision = self.pipeline.run(context)
            persisted = self.repository.save_decision(
                run_id,
                request,
                context,
                decision,
            )
        except Exception:
            self.repository.cancel_run(run_id)
            raise

        return ConnectionValidationResponse(
            connection_validation_run_id=run_id,
            compatibility_result_id=persisted.compatibility_result_id,
            mapping_id=persisted.mapping_id,
            lifecycle_status=persisted.lifecycle_status,
            is_latest_run=persisted.is_latest_run,
            compatibility_level=(
                decision.compatibility_level
                if persisted.is_latest_run and persisted.lifecycle_status != "DEPRECATED"
                else "MISSING_INFORMATION"
            ),
            reason_code=(
                "CONNECTION_DEPRECATED"
                if persisted.lifecycle_status == "DEPRECATED"
                else decision.reason_code
                if persisted.is_latest_run
                else "STALE_VALIDATION_RUN"
            ),
            reason=(
                "The connection was deprecated while validation was running."
                if persisted.lifecycle_status == "DEPRECATED"
                else decision.reason
                if persisted.is_latest_run
                else "A newer validation run superseded this result."
            ),
            activation_allowed=(
                decision.activation_allowed
                and persisted.is_latest_run
                and persisted.lifecycle_status == "ACTIVE"
            ),
            source_api_id=request.source_api_id,
            source_version_id=request.source_version_id,
            target_api_id=request.target_api_id,
            target_version_id=request.target_version_id,
            source_schema_id=source_schema.schema_id if source_schema else None,
            target_schema_id=target_schema.schema_id if target_schema else None,
            stages=decision.stages,
            reasons=decision.reasons,
        )

    def get_connection(
        self,
        mapping_id: int,
        *,
        enterprise_id: int,
        is_admin: bool = False,
    ) -> ConnectionLifecycleResponse:
        connection = self._get_authorized_connection(mapping_id, enterprise_id, is_admin)
        return ConnectionLifecycleResponse.model_validate(connection)

    def deprecate_connection(
        self,
        mapping_id: int,
        *,
        enterprise_id: int,
        is_admin: bool = False,
    ) -> ConnectionLifecycleResponse:
        connection = self._get_authorized_connection(mapping_id, enterprise_id, is_admin)
        if connection["lifecycle_status"] == "VALIDATING":
            raise ConnectionValidationConflictError(
                "A validating connection cannot be deprecated until its active run completes."
            )
        if connection["lifecycle_status"] != "DEPRECATED":
            connection = self.repository.deprecate_connection(mapping_id)
        return ConnectionLifecycleResponse.model_validate(connection)

    def _get_authorized_connection(
        self,
        mapping_id: int,
        enterprise_id: int,
        is_admin: bool,
    ) -> dict[str, Any]:
        connection = self.repository.get_connection(mapping_id)
        if connection is None:
            raise ConnectionValidationNotFoundError(
                f"Connection mapping {mapping_id} was not found."
            )
        if not is_admin and connection["source_enterprise_id"] != enterprise_id:
            raise ConnectionValidationPermissionError(
                "Only the source API owner or an administrator may manage this connection."
            )
        return connection
