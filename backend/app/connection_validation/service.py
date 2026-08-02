from __future__ import annotations

from app.connection_validation.enums import CompatibilityLevel
from app.connection_validation.pipeline import ConnectionValidationPipeline
from app.connection_validation.repository import (
    ConnectionValidationConflictError,
    ConnectionValidationNotFoundError,
    ConnectionValidationPermissionError,
    ConnectionValidationRepository,
)
from app.connection_validation.schemas import (
    ConnectionValidationContext,
    ConnectionValidationRequest,
    ConnectionValidationResponse,
    ConnectionValidationRunDetail,
)
from app.services.schema_mapping.compatibility_engine import compare_schemas
from app.services.schema_mapping.data_validator import validate_data


class ConnectionValidationService:
    def __init__(
        self,
        repository: ConnectionValidationRepository,
        *,
        pipeline: ConnectionValidationPipeline | None = None,
    ) -> None:
        self.repository = repository
        self.pipeline = pipeline or ConnectionValidationPipeline(
            compare_schemas,
            validate_data,
            allow_mapping=False,
            require_sample=False,
        )

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
                f"Source API {request.source_api_id} version {request.source_version_id} was not found.",
                "SOURCE_VERSION_NOT_FOUND",
            )
        target = self.repository.get_version(
            request.target_api_id,
            request.target_version_id,
        )
        if target is None:
            raise ConnectionValidationNotFoundError(
                f"Target API {request.target_api_id} version {request.target_version_id} was not found.",
                "TARGET_VERSION_NOT_FOUND",
            )
        if request.source_version_id == request.target_version_id:
            raise ConnectionValidationConflictError(
                "Source and target must be different versions."
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
            context = ConnectionValidationContext(
                source=source,
                target=target,
                source_schema=source_schema,
                target_schema=target_schema,
                aliases=self.repository.list_format_aliases(),
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
            transform_run_id=None,
            mapping_id=None,
            lifecycle_status=None,
            is_latest_run=persisted.is_latest_run,
            compatibility_level=(
                decision.compatibility_level
                if persisted.is_latest_run
                else CompatibilityLevel.NOT_ASSESSABLE
            ),
            reason_code=(
                decision.reason_code
                if persisted.is_latest_run
                else "STALE_VALIDATION_RUN"
            ),
            reason=(
                decision.reason
                if persisted.is_latest_run
                else "A newer validation run superseded this result."
            ),
            activation_allowed=(
                decision.activation_allowed
                and persisted.is_latest_run
            ),
            business_rules_diagnostics=decision.business_rules_diagnostics,
            source_api_id=request.source_api_id,
            source_version_id=request.source_version_id,
            target_api_id=request.target_api_id,
            target_version_id=request.target_version_id,
            source_schema_id=source_schema.schema_id if source_schema else None,
            target_schema_id=target_schema.schema_id if target_schema else None,
            stages=decision.stages,
            reasons=decision.reasons,
        )

    def get_run(
        self,
        run_id: int,
        *,
        enterprise_id: int,
        is_admin: bool = False,
    ) -> ConnectionValidationRunDetail:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ConnectionValidationNotFoundError(
                f"Connection validation run {run_id} was not found."
            )
        if not is_admin and run["source_enterprise_id"] != enterprise_id:
            raise ConnectionValidationPermissionError(
                "Only the source API owner or an administrator may read this validation run."
            )
        return ConnectionValidationRunDetail.model_validate(run)
