from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from app.connection_validation.enums import CompatibilityLevel
from app.connection_validation.repository import (
    ConnectionValidationConflictError,
    ConnectionValidationPermissionError,
)
from app.connection_validation.schemas import (
    ConnectionValidationContext,
    ConnectionValidationDecision,
    ConnectionValidationRequest,
    EndpointVersion,
    FormatAlias,
    PayloadSchema,
)
from app.core.database import get_connection
from app.services.schema_mapping.repository import PostgresSchemaMappingRepository


def _format_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


class PostgresConnectionValidationRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager[Connection]] = get_connection,
    ) -> None:
        self.connection_factory = connection_factory
        self.schema_repository = PostgresSchemaMappingRepository(connection_factory)

    def get_version(self, api_id: int, version_id: int) -> EndpointVersion | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT api_id, version_id, status, input_formats, output_formats,
                           input_format, output_format
                    FROM api_version
                    WHERE api_id = %s AND version_id = %s
                    """,
                    (api_id, version_id),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        input_formats = _format_list(row.get("input_formats")) or _format_list(row.get("input_format"))
        output_formats = _format_list(row.get("output_formats")) or _format_list(row.get("output_format"))
        return EndpointVersion(
            api_id=row["api_id"],
            version_id=row["version_id"],
            status=row["status"],
            input_formats=input_formats,
            output_formats=output_formats,
        )

    def get_schema(
        self,
        api_id: int,
        version_id: int,
        direction: str,
        schema_id: int | None = None,
    ) -> PayloadSchema | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                parameters: list[Any] = [api_id, version_id, direction]
                schema_filter = ""
                if schema_id is not None:
                    schema_filter = "AND schema_id = %s"
                    parameters.append(schema_id)
                cursor.execute(
                    f"""
                    SELECT schema_id
                    FROM api_schema
                    WHERE api_id = %s
                      AND version_id = %s
                      AND direction = %s
                      {schema_filter}
                    ORDER BY schema_version DESC, schema_id DESC
                    """,
                    parameters,
                )
                rows = cursor.fetchall()
        if not rows:
            return None
        if schema_id is None and len(rows) > 1:
            raise ConnectionValidationConflictError(
                f"API {api_id} version {version_id} has multiple {direction} schemas; "
                "provide the corresponding schema ID."
            )
        row = self.schema_repository.get_api_schema(rows[0]["schema_id"])
        if row is None:
            return None
        return PayloadSchema(
            schema_id=row["schema_id"],
            direction=row["direction"],
            format=row["format"],
            definition=row["schema_definition"],
        )

    def list_format_aliases(self) -> list[FormatAlias]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT raw_value, normalized_value, family, is_terminal_output
                    FROM format_alias
                    ORDER BY alias_id
                    """
                )
                rows = cursor.fetchall()
        return [FormatAlias(**row) for row in rows]

    def get_mapping_metadata(
        self,
        request: ConnectionValidationRequest,
        source_schema_id: int,
        target_schema_id: int,
    ) -> dict[str, Any] | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT mapping_id, lifecycle_status, completeness
                    FROM schema_mapping
                    WHERE source_api_id = %s
                      AND source_version_id = %s
                      AND target_api_id = %s
                      AND target_version_id = %s
                      AND source_schema_id = %s
                      AND target_schema_id = %s
                    ORDER BY
                        CASE lifecycle_status
                            WHEN 'ACTIVE' THEN 1
                            WHEN 'VALIDATING' THEN 2
                            WHEN 'DRAFT' THEN 3
                            ELSE 4
                        END,
                        updated_at DESC
                    LIMIT 1
                    """,
                    (
                        request.source_api_id,
                        request.source_version_id,
                        request.target_api_id,
                        request.target_version_id,
                        source_schema_id,
                        target_schema_id,
                    ),
                )
                return cursor.fetchone()

    def assert_actor_can_validate(
        self,
        source_api_id: int,
        target_api_id: int,
        enterprise_id: int,
        is_admin: bool,
    ) -> None:
        if is_admin:
            return
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT api_id, enterprise_id
                    FROM api_submission
                    WHERE api_id = ANY(%s)
                    """,
                    ([source_api_id, target_api_id],),
                )
                ownership = {row["api_id"]: row["enterprise_id"] for row in cursor.fetchall()}
        if ownership.get(source_api_id) != enterprise_id:
            raise ConnectionValidationPermissionError(
                "Only the source API owner or an administrator may run connection validation."
            )

    def create_run(
        self,
        request: ConnectionValidationRequest,
        created_by: int,
    ) -> int:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO connection_validation_run (
                        source_api_id, target_api_id, source_version_id, target_version_id,
                        trigger_type, created_by
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING connection_validation_run_id
                    """,
                    (
                        request.source_api_id,
                        request.target_api_id,
                        request.source_version_id,
                        request.target_version_id,
                        request.trigger_type.value,
                        created_by,
                    ),
                )
                return cursor.fetchone()["connection_validation_run_id"]

    def save_decision(
        self,
        run_id: int,
        request: ConnectionValidationRequest,
        context: ConnectionValidationContext,
        decision: ConnectionValidationDecision,
    ) -> int:
        response_summary = {
            "activation_allowed": decision.activation_allowed,
            "reason_code": decision.reason_code,
            "stage_statuses": {
                stage.stage.value: stage.status.value for stage in decision.stages
            },
        }
        full_result = {
            "compatibility_level": decision.compatibility_level.value,
            "reason_code": decision.reason_code,
            "reason": decision.reason,
            "activation_allowed": decision.activation_allowed,
            "stages": [stage.model_dump(mode="json") for stage in decision.stages],
            "reasons": [reason.model_dump(mode="json") for reason in decision.reasons],
        }
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO compatibility_result (
                        source_api_id, target_api_id, source_version_id, target_version_id,
                        source_schema_id, target_schema_id, compatibility_level,
                        reason_code, reason, reason_details, summary, full_result
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_version_id, target_version_id)
                    DO UPDATE SET
                        source_api_id = EXCLUDED.source_api_id,
                        target_api_id = EXCLUDED.target_api_id,
                        source_schema_id = EXCLUDED.source_schema_id,
                        target_schema_id = EXCLUDED.target_schema_id,
                        compatibility_level = EXCLUDED.compatibility_level,
                        reason_code = EXCLUDED.reason_code,
                        reason = EXCLUDED.reason,
                        reason_details = EXCLUDED.reason_details,
                        summary = EXCLUDED.summary,
                        full_result = EXCLUDED.full_result,
                        created_at = CURRENT_TIMESTAMP
                    RETURNING result_id
                    """,
                    (
                        request.source_api_id,
                        request.target_api_id,
                        request.source_version_id,
                        request.target_version_id,
                        context.source_schema.schema_id if context.source_schema else None,
                        context.target_schema.schema_id if context.target_schema else None,
                        decision.compatibility_level.value,
                        decision.reason_code,
                        decision.reason,
                        Jsonb(decision.reasons[0].details if decision.reasons else {}),
                        Jsonb(response_summary),
                        Jsonb(full_result),
                    ),
                )
                result_id = cursor.fetchone()["result_id"]

                cursor.execute(
                    "DELETE FROM compatibility_reason_item WHERE result_id = %s",
                    (result_id,),
                )
                for reason in decision.reasons:
                    cursor.execute(
                        """
                        INSERT INTO compatibility_reason_item (
                            result_id, reason_code, stage, severity, source_path,
                            target_path, message, details
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            result_id,
                            reason.reason_code,
                            reason.stage.value,
                            reason.severity.value,
                            reason.source_path,
                            reason.target_path,
                            reason.message,
                            Jsonb(reason.details),
                        ),
                    )

                for stage in decision.stages:
                    cursor.execute(
                        """
                        INSERT INTO connection_validation_stage_result (
                            connection_validation_run_id, stage, status, message, payload
                        ) VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (connection_validation_run_id, stage)
                        DO UPDATE SET
                            status = EXCLUDED.status,
                            message = EXCLUDED.message,
                            payload = EXCLUDED.payload
                        """,
                        (
                            run_id,
                            stage.stage.value,
                            stage.status.value,
                            stage.message,
                            Jsonb(stage.payload),
                        ),
                    )

                run_status = (
                    "PASSED"
                    if decision.compatibility_level == CompatibilityLevel.COMPATIBLE
                    else "FAILED"
                )
                cursor.execute(
                    """
                    UPDATE connection_validation_run
                    SET compatibility_result_id = %s,
                        status = %s,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE connection_validation_run_id = %s
                    """,
                    (result_id, run_status, run_id),
                )
                return result_id
