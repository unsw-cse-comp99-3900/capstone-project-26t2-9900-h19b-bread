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
    PersistedDecision,
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
                    "SELECT pg_advisory_xact_lock(%s, %s)",
                    (request.source_version_id, request.target_version_id),
                )
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

    def prepare_mapping(
        self,
        request: ConnectionValidationRequest,
        source_schema: PayloadSchema,
        target_schema: PayloadSchema,
    ) -> dict[str, Any]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s, %s)",
                    (request.source_version_id, request.target_version_id),
                )
                cursor.execute(
                    """
                    INSERT INTO schema_mapping (
                        source_api_id, target_api_id, source_version_id, target_version_id,
                        source_schema_id, target_schema_id, source_schema_format,
                        target_schema_format, overview_note, lifecycle_status, completeness
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'VALIDATING', 'PARTIAL')
                    ON CONFLICT (source_schema_id, target_schema_id)
                    DO UPDATE SET
                        lifecycle_status = CASE
                            WHEN schema_mapping.lifecycle_status = 'DEPRECATED'
                                THEN schema_mapping.lifecycle_status
                            ELSE 'VALIDATING'::mapping_lifecycle_status
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING mapping_id, lifecycle_status, completeness
                    """,
                    (
                        request.source_api_id,
                        request.target_api_id,
                        request.source_version_id,
                        request.target_version_id,
                        source_schema.schema_id,
                        target_schema.schema_id,
                        source_schema.format,
                        target_schema.format,
                        "Connection validation lifecycle record.",
                    ),
                )
                mapping = cursor.fetchone()
        if mapping["lifecycle_status"] == "DEPRECATED":
            raise ConnectionValidationConflictError(
                "Deprecated connections cannot be revalidated. Create a new version-pair connection."
            )
        return mapping

    def get_connection(self, mapping_id: int) -> dict[str, Any] | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT mapping.mapping_id, mapping.source_api_id,
                           mapping.source_version_id, mapping.target_api_id,
                           mapping.target_version_id, mapping.source_schema_id,
                           mapping.target_schema_id, mapping.compatibility_result_id,
                           mapping.lifecycle_status, mapping.completeness,
                           mapping.updated_at, source.enterprise_id AS source_enterprise_id
                    FROM schema_mapping mapping
                    JOIN api_submission source ON source.api_id = mapping.source_api_id
                    WHERE mapping.mapping_id = %s
                    """,
                    (mapping_id,),
                )
                return cursor.fetchone()

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT run.connection_validation_run_id, run.source_api_id,
                           run.source_version_id, run.target_api_id,
                           run.target_version_id, run.compatibility_result_id,
                           run.status, run.trigger_type, run.created_by,
                           run.started_at, run.completed_at,
                           source.enterprise_id AS source_enterprise_id
                    FROM connection_validation_run run
                    JOIN api_submission source ON source.api_id = run.source_api_id
                    WHERE run.connection_validation_run_id = %s
                    """,
                    (run_id,),
                )
                run = cursor.fetchone()
                if run is None:
                    return None
                cursor.execute(
                    """
                    SELECT stage, status, message, COALESCE(payload, '{}'::jsonb) AS payload
                    FROM connection_validation_stage_result
                    WHERE connection_validation_run_id = %s
                    ORDER BY stage
                    """,
                    (run_id,),
                )
                run["stages"] = cursor.fetchall()
                return run

    def list_runs(
        self,
        source_api_id: int,
        source_version_id: int,
        target_api_id: int,
        target_version_id: int,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, Any]], int]:
        parameters = (
            source_api_id,
            source_version_id,
            target_api_id,
            target_version_id,
        )
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS total
                    FROM connection_validation_run
                    WHERE source_api_id = %s
                      AND source_version_id = %s
                      AND target_api_id = %s
                      AND target_version_id = %s
                    """,
                    parameters,
                )
                total = cursor.fetchone()["total"]
                cursor.execute(
                    """
                    SELECT connection_validation_run_id, source_api_id,
                           source_version_id, target_api_id, target_version_id,
                           compatibility_result_id, status, trigger_type,
                           created_by, started_at, completed_at
                    FROM connection_validation_run
                    WHERE source_api_id = %s
                      AND source_version_id = %s
                      AND target_api_id = %s
                      AND target_version_id = %s
                    ORDER BY started_at DESC, connection_validation_run_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (*parameters, limit, offset),
                )
                return cursor.fetchall(), total

    def deprecate_connection(self, mapping_id: int) -> dict[str, Any] | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE schema_mapping
                    SET lifecycle_status = 'DEPRECATED', updated_at = CURRENT_TIMESTAMP
                    WHERE mapping_id = %s
                      AND lifecycle_status <> 'VALIDATING'
                    RETURNING mapping_id
                    """,
                    (mapping_id,),
                )
                updated = cursor.fetchone()
        if updated is None:
            return None
        return self.get_connection(mapping_id)

    def save_decision(
        self,
        run_id: int,
        request: ConnectionValidationRequest,
        context: ConnectionValidationContext,
        decision: ConnectionValidationDecision,
    ) -> PersistedDecision:
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
                    "SELECT pg_advisory_xact_lock(%s, %s)",
                    (request.source_version_id, request.target_version_id),
                )
                cursor.execute(
                    """
                    SELECT connection_validation_run_id, status
                    FROM connection_validation_run
                    WHERE source_version_id = %s AND target_version_id = %s
                    ORDER BY started_at DESC, connection_validation_run_id DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (request.source_version_id, request.target_version_id),
                )
                latest = cursor.fetchone()
                is_latest = (
                    latest is not None
                    and latest["connection_validation_run_id"] == run_id
                )

                self._save_stage_results(cursor, run_id, decision)
                mapping_id = context.mapping.mapping_id if context.mapping else None
                if is_latest and latest["status"] == "CANCELLED":
                    lifecycle_status = None
                    if mapping_id is not None:
                        cursor.execute(
                            "SELECT lifecycle_status FROM schema_mapping WHERE mapping_id = %s",
                            (mapping_id,),
                        )
                        mapping_row = cursor.fetchone()
                        lifecycle_status = (
                            mapping_row["lifecycle_status"] if mapping_row else None
                        )
                    return PersistedDecision(
                        compatibility_result_id=None,
                        mapping_id=mapping_id,
                        lifecycle_status=lifecycle_status,
                        is_latest_run=True,
                    )
                if not is_latest:
                    cursor.execute(
                        """
                        UPDATE connection_validation_run
                        SET status = 'STALE', completed_at = CURRENT_TIMESTAMP
                        WHERE connection_validation_run_id = %s
                          AND status = 'RUNNING'
                        """,
                        (run_id,),
                    )
                    lifecycle_status = None
                    if mapping_id is not None:
                        cursor.execute(
                            "SELECT lifecycle_status FROM schema_mapping WHERE mapping_id = %s",
                            (mapping_id,),
                        )
                        mapping_row = cursor.fetchone()
                        lifecycle_status = mapping_row["lifecycle_status"] if mapping_row else None
                    return PersistedDecision(
                        compatibility_result_id=None,
                        mapping_id=mapping_id,
                        lifecycle_status=lifecycle_status,
                        is_latest_run=False,
                    )

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

                lifecycle_status = None
                if mapping_id is not None:
                    lifecycle_status = "ACTIVE" if decision.activation_allowed else "FAILED"
                    cursor.execute(
                        """
                        UPDATE schema_mapping
                        SET compatibility_result_id = %s,
                            lifecycle_status = %s,
                            completeness = CASE
                                WHEN %s = 'DIRECTLY_COMPATIBLE' THEN 'FULL'::mapping_completeness
                                ELSE completeness
                            END,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE mapping_id = %s
                          AND lifecycle_status <> 'DEPRECATED'
                        """,
                        (result_id, lifecycle_status, decision.reason_code, mapping_id),
                    )
                    cursor.execute(
                        "SELECT lifecycle_status FROM schema_mapping WHERE mapping_id = %s",
                        (mapping_id,),
                    )
                    mapping_row = cursor.fetchone()
                    lifecycle_status = mapping_row["lifecycle_status"] if mapping_row else None

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
                      AND status = 'RUNNING'
                    """,
                    (result_id, run_status, run_id),
                )
                return PersistedDecision(
                    compatibility_result_id=result_id,
                    mapping_id=mapping_id,
                    lifecycle_status=lifecycle_status,
                    is_latest_run=True,
                )

    def cancel_run(self, run_id: int) -> None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE connection_validation_run
                    SET status = 'CANCELLED', completed_at = CURRENT_TIMESTAMP
                    WHERE connection_validation_run_id = %s
                      AND status = 'RUNNING'
                    """,
                    (run_id,),
                )
                cursor.execute(
                    """
                    UPDATE schema_mapping mapping
                    SET lifecycle_status = 'FAILED', updated_at = CURRENT_TIMESTAMP
                    FROM connection_validation_run run
                    WHERE run.connection_validation_run_id = %s
                      AND mapping.source_version_id = run.source_version_id
                      AND mapping.target_version_id = run.target_version_id
                      AND mapping.lifecycle_status = 'VALIDATING'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM connection_validation_run newer
                          WHERE newer.source_version_id = run.source_version_id
                            AND newer.target_version_id = run.target_version_id
                            AND newer.connection_validation_run_id > run.connection_validation_run_id
                      )
                    """,
                    (run_id,),
                )

    @staticmethod
    def _save_stage_results(cursor, run_id: int, decision: ConnectionValidationDecision) -> None:
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
