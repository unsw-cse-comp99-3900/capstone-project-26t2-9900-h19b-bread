from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from typing import Any

from psycopg import Connection

from app.core.database import get_connection
from app.version_history.models import VersionWrite


class PostgresVersionHistoryRepository:
    def __init__(
        self,
        connection_factory: Callable[[], AbstractContextManager[Connection]] = get_connection,
    ) -> None:
        self.connection_factory = connection_factory
        self._active_connection: Connection | None = None

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._active_connection is not None:
            yield
            return

        with self.connection_factory() as connection:
            self._active_connection = connection
            try:
                yield
            finally:
                self._active_connection = None

    def _connection(self) -> AbstractContextManager[Connection]:
        if self._active_connection is not None:
            return nullcontext(self._active_connection)
        return self.connection_factory()

    def lock_api(self, api_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        api_id,
                        enterprise_id,
                        submitted_by,
                        status,
                        current_version_id,
                        last_published_version_id
                    FROM api_submission
                    WHERE api_id = %s
                    FOR UPDATE
                    """,
                    (api_id,),
                )
                return cursor.fetchone()

    def get_api_context(self, api_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        api_id,
                        enterprise_id,
                        submitted_by,
                        status,
                        current_version_id,
                        last_published_version_id,
                        history_visibility
                    FROM api_submission
                    WHERE api_id = %s
                    """,
                    (api_id,),
                )
                return cursor.fetchone()

    def list_versions(self, api_id: int, limit: int, offset: int) -> tuple[int, list[dict[str, Any]]]:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS total FROM api_version WHERE api_id = %s",
                    (api_id,),
                )
                total = cursor.fetchone()["total"]
                cursor.execute(
                    """
                    SELECT
                        version.version_id,
                        version.version_number,
                        version.status,
                        version.change_note,
                        version.snapshot_origin,
                        version.created_by,
                        creator.name AS created_by_name,
                        version.created_at,
                        version.updated_at,
                        version.version_id = submission.current_version_id AS is_current,
                        version.version_id = submission.last_published_version_id AS is_last_published
                    FROM api_version version
                    JOIN api_submission submission ON submission.api_id = version.api_id
                    JOIN app_user creator ON creator.user_id = version.created_by
                    WHERE version.api_id = %s
                    ORDER BY version.created_at DESC, version.version_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (api_id, limit, offset),
                )
                rows = cursor.fetchall()
        return total, rows

    def get_version_detail(self, api_id: int, version_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        version.*,
                        creator.name AS created_by_name,
                        auth.auth_method,
                        auth.auth_description,
                        auth.security_scheme_name,
                        auth.is_complete AS auth_is_complete,
                        specification.specification_id,
                        specification.spec_type,
                        specification.source_type,
                        specification.file_path,
                        specification.spec_url,
                        specification.checksum,
                        specification.uploaded_at,
                        version.version_id = submission.current_version_id AS is_current,
                        version.version_id = submission.last_published_version_id AS is_last_published
                    FROM api_version version
                    JOIN api_submission submission ON submission.api_id = version.api_id
                    JOIN app_user creator ON creator.user_id = version.created_by
                    JOIN api_version_auth auth ON auth.version_id = version.version_id
                    LEFT JOIN api_specification specification
                      ON specification.version_id = version.version_id
                    WHERE version.api_id = %s
                      AND version.version_id = %s
                    """,
                    (api_id, version_id),
                )
                version = cursor.fetchone()
                if version is None:
                    return None
                cursor.execute(
                    """
                    SELECT
                        validation_run_id,
                        overall_status,
                        started_at,
                        completed_at
                    FROM validation_run
                    WHERE api_id = %s
                      AND version_id = %s
                    ORDER BY started_at DESC, validation_run_id DESC
                    """,
                    (api_id, version_id),
                )
                runs = cursor.fetchall()
                for run in runs:
                    cursor.execute(
                        """
                        SELECT result_id, stage, status, message, error_detail, created_at
                        FROM validation_result
                        WHERE validation_run_id = %s
                        ORDER BY result_id
                        """,
                        (run["validation_run_id"],),
                    )
                    run["results"] = cursor.fetchall()
        version["validation_runs"] = runs
        return version

    def get_specification(self, api_id: int, version_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        specification.specification_id,
                        specification.version_id,
                        specification.spec_type,
                        specification.source_type,
                        specification.file_path,
                        specification.spec_url,
                        specification.raw_content,
                        specification.checksum,
                        specification.uploaded_at
                    FROM api_specification specification
                    JOIN api_version version ON version.version_id = specification.version_id
                    WHERE version.api_id = %s
                      AND version.version_id = %s
                    """,
                    (api_id, version_id),
                )
                return cursor.fetchone()

    def list_events(
        self,
        api_id: int,
        limit: int,
        offset: int,
        version_id: int | None,
        action: str | None,
    ) -> tuple[int, list[dict[str, Any]]]:
        filters = ["event.api_id = %s"]
        parameters: list[Any] = [api_id]
        if version_id is not None:
            filters.append("event.version_id = %s")
            parameters.append(version_id)
        if action is not None:
            filters.append("event.action = %s")
            parameters.append(action)
        where_clause = " AND ".join(filters)
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM api_lifecycle_event event WHERE {where_clause}",
                    parameters,
                )
                total = cursor.fetchone()["total"]
                cursor.execute(
                    f"""
                    SELECT
                        event.event_id,
                        event.api_id,
                        event.version_id,
                        event.action,
                        event.from_status,
                        event.to_status,
                        event.actor_user_id,
                        actor.name AS actor_name,
                        event.validation_run_id,
                        event.reason,
                        event.created_at
                    FROM api_lifecycle_event event
                    LEFT JOIN app_user actor ON actor.user_id = event.actor_user_id
                    WHERE {where_clause}
                    ORDER BY event.created_at DESC, event.event_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*parameters, limit, offset],
                )
                rows = cursor.fetchall()
        return total, rows

    def get_version_status(self, version_id: int) -> str | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT status FROM api_version WHERE version_id = %s",
                    (version_id,),
                )
                row = cursor.fetchone()
        return None if row is None else str(row["status"])

    def create_version(
        self,
        api_id: int,
        actor_id: int,
        previous_status: str,
        data: VersionWrite,
    ) -> int:
        protocol_type, auth_method, spec_type = self._normalized_types(data)
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO api_version (
                        api_id,
                        created_by,
                        version_number,
                        change_note,
                        status,
                        api_name,
                        endpoint_url,
                        protocol_type,
                        input_format,
                        output_format,
                        capability_category,
                        description,
                        snapshot_origin
                    )
                    VALUES (
                        %s, %s, %s, %s, 'DRAFT',
                        %s, %s, %s, %s, %s, %s, %s, 'NATIVE'
                    )
                    RETURNING version_id
                    """,
                    (
                        api_id,
                        actor_id,
                        data.version_number,
                        data.change_note,
                        data.api_name,
                        data.endpoint_url,
                        protocol_type,
                        data.input_format,
                        data.output_format,
                        data.capability_category,
                        data.description,
                    ),
                )
                version_id = cursor.fetchone()["version_id"]
                self._insert_version_children(
                    cursor,
                    api_id,
                    version_id,
                    auth_method,
                    spec_type,
                    data,
                )
                cursor.execute(
                    """
                    UPDATE api_submission
                    SET current_version_id = %s,
                        status = 'DRAFT',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE api_id = %s
                    """,
                    (version_id, api_id),
                )
                cursor.execute(
                    """
                    INSERT INTO api_lifecycle_event (
                        api_id,
                        version_id,
                        action,
                        from_status,
                        to_status,
                        actor_user_id,
                        reason
                    )
                    VALUES (%s, %s, 'VERSION_CREATED', %s, 'DRAFT', %s, %s)
                    """,
                    (api_id, version_id, previous_status, actor_id, data.change_note),
                )
        return version_id

    def update_draft(self, api_id: int, version_id: int, data: VersionWrite) -> None:
        protocol_type, auth_method, spec_type = self._normalized_types(data)
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE api_version
                    SET version_number = %s,
                        change_note = %s,
                        api_name = %s,
                        endpoint_url = %s,
                        protocol_type = %s,
                        input_format = %s,
                        output_format = %s,
                        capability_category = %s,
                        description = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE api_id = %s
                      AND version_id = %s
                      AND status = 'DRAFT'
                    """,
                    (
                        data.version_number,
                        data.change_note,
                        data.api_name,
                        data.endpoint_url,
                        protocol_type,
                        data.input_format,
                        data.output_format,
                        data.capability_category,
                        data.description,
                        api_id,
                        version_id,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("Draft update target disappeared")
                cursor.execute(
                    """
                    UPDATE api_version_auth
                    SET auth_method = %s,
                        auth_description = %s,
                        security_scheme_name = %s,
                        is_complete = TRUE
                    WHERE version_id = %s
                    """,
                    (
                        auth_method,
                        data.auth_description,
                        data.security_scheme_name,
                        version_id,
                    ),
                )
                cursor.execute(
                    """
                    UPDATE api_specification
                    SET spec_type = %s,
                        source_type = 'FILE_UPLOAD',
                        file_path = %s,
                        spec_url = NULL,
                        raw_content = %s,
                        checksum = NULL,
                        uploaded_at = CURRENT_TIMESTAMP
                    WHERE version_id = %s
                    """,
                    (spec_type, f"inline/version_{api_id}_{version_id}.txt", data.spec_content, version_id),
                )

    def _insert_version_children(
        self,
        cursor: Any,
        api_id: int,
        version_id: int,
        auth_method: str,
        spec_type: str,
        data: VersionWrite,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO api_version_auth (
                version_id,
                auth_method,
                auth_description,
                security_scheme_name,
                is_complete
            )
            VALUES (%s, %s, %s, %s, TRUE)
            """,
            (
                version_id,
                auth_method,
                data.auth_description,
                data.security_scheme_name,
            ),
        )
        cursor.execute(
            """
            INSERT INTO api_specification (
                version_id,
                spec_type,
                source_type,
                file_path,
                raw_content
            )
            VALUES (%s, %s, 'FILE_UPLOAD', %s, %s)
            """,
            (version_id, spec_type, f"inline/version_{api_id}_{version_id}.txt", data.spec_content),
        )

    def _normalized_types(self, data: VersionWrite) -> tuple[str, str, str]:
        protocol_type = data.protocol_type.strip().upper()
        if protocol_type not in {"REST", "SOAP"}:
            raise ValueError("protocol_type must be REST or SOAP")
        auth_method = data.auth_method.strip().upper()
        if auth_method not in {"OAUTH2", "API_KEY", "BASIC", "MTLS", "OTHER"}:
            auth_method = "OTHER"
        spec_type = "OPENAPI" if protocol_type == "REST" else "WSDL"
        return protocol_type, auth_method, spec_type
