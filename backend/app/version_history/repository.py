from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext

from psycopg import Connection

from app.core.database import get_connection
from app.services.schema_mapping.spec_schema_extractor import sync_api_schemas_from_spec
from app.version_history.schemas import VersionWriteRequest


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

    def get_api(self, api_id: int, *, for_update: bool = False) -> dict | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT api_id, enterprise_id, submitted_by, status, current_version_id
                    FROM api_submission
                    WHERE api_id = %s
                    """ + suffix,
                    (api_id,),
                )
                return cursor.fetchone()

    def get_version(self, api_id: int, version_id: int) -> dict | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM api_version
                    WHERE api_id = %s AND version_id = %s
                    """,
                    (api_id, version_id),
                )
                return cursor.fetchone()

    def list_versions(self, api_id: int, limit: int, offset: int) -> tuple[list[dict], int]:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS total FROM api_version WHERE api_id = %s", (api_id,))
                total = cursor.fetchone()["total"]
                cursor.execute(
                    """
                    SELECT version_id, version_number, change_note, status, is_current,
                           previous_version_id, created_by, api_name, created_at,
                           published_at, archived_at
                    FROM api_version
                    WHERE api_id = %s
                    ORDER BY created_at DESC, version_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (api_id, limit, offset),
                )
                return cursor.fetchall(), total

    def get_version_detail(self, api_id: int, version_id: int) -> dict | None:
        version = self.get_version(api_id, version_id)
        if version is None:
            return None
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT auth_method, auth_description, security_scheme_name, is_complete
                    FROM auth_metadata
                    WHERE api_id = %s AND version_id = %s
                    ORDER BY auth_id DESC LIMIT 1
                    """,
                    (api_id, version_id),
                )
                auth = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT specification_id, spec_type, source_type, file_path, spec_url,
                           checksum, uploaded_at
                    FROM api_specification WHERE version_id = %s
                    """,
                    (version_id,),
                )
                specification = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT validation_run_id, overall_status, started_at, completed_at
                    FROM validation_run
                    WHERE api_id = %s AND version_id = %s
                    ORDER BY started_at DESC, validation_run_id DESC
                    """,
                    (api_id, version_id),
                )
                runs = cursor.fetchall()
                for run in runs:
                    cursor.execute(
                        """
                        SELECT stage, status, message, error_detail
                        FROM validation_result
                        WHERE validation_run_id = %s
                        ORDER BY result_id
                        """,
                        (run["validation_run_id"],),
                    )
                    run["results"] = cursor.fetchall()
        version["auth"] = auth
        version["specification"] = specification
        version["validation_runs"] = runs
        return version

    def get_specification(self, api_id: int, version_id: int) -> dict | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT specification.raw_content, specification.spec_type
                    FROM api_specification specification
                    JOIN api_version version ON version.version_id = specification.version_id
                    WHERE version.api_id = %s AND version.version_id = %s
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
        event_type: str | None,
    ) -> tuple[list[dict], int]:
        filters = ["api_id = %s"]
        params: list[object] = [api_id]
        if version_id is not None:
            filters.append("version_id = %s")
            params.append(version_id)
        if event_type is not None:
            filters.append("event_type = %s")
            params.append(event_type)
        where = " AND ".join(filters)
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"SELECT COUNT(*) AS total FROM api_version_event WHERE {where}", params)
                total = cursor.fetchone()["total"]
                cursor.execute(
                    f"""
                    SELECT event_id, version_id, api_id, actor_user_id, event_type,
                           from_status, to_status, message, created_at
                    FROM api_version_event
                    WHERE {where}
                    ORDER BY created_at DESC, event_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    [*params, limit, offset],
                )
                return cursor.fetchall(), total

    def list_connection_impacts(
        self,
        api_id: int,
        limit: int,
        offset: int,
        version_id: int | None,
        lifecycle_status: str | None,
    ) -> tuple[list[dict], int]:
        filters = ["(mapping.source_api_id = %s OR mapping.target_api_id = %s)"]
        params: list[object] = [api_id, api_id]
        if version_id is not None:
            filters.append(
                "((mapping.source_api_id = %s AND mapping.source_version_id = %s) "
                "OR (mapping.target_api_id = %s AND mapping.target_version_id = %s))"
            )
            params.extend([api_id, version_id, api_id, version_id])
        if lifecycle_status is not None:
            filters.append("mapping.lifecycle_status = %s")
            params.append(lifecycle_status)
        where = " AND ".join(filters)

        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM schema_mapping mapping WHERE {where}",
                    params,
                )
                total = cursor.fetchone()["total"]
                cursor.execute(
                    f"""
                    SELECT mapping.mapping_id,
                           CASE WHEN mapping.source_api_id = %s THEN 'SOURCE' ELSE 'TARGET' END AS role,
                           CASE WHEN mapping.source_api_id = %s
                               THEN mapping.source_version_id ELSE mapping.target_version_id
                           END AS api_version_id,
                           CASE WHEN mapping.source_api_id = %s
                               THEN mapping.target_api_id ELSE mapping.source_api_id
                           END AS counterpart_api_id,
                           CASE WHEN mapping.source_api_id = %s
                               THEN mapping.target_version_id ELSE mapping.source_version_id
                           END AS counterpart_version_id,
                           mapping.lifecycle_status, mapping.completeness,
                           latest.connection_validation_run_id AS latest_validation_run_id,
                           latest.status AS latest_validation_run_status,
                           mapping.updated_at
                    FROM schema_mapping mapping
                    LEFT JOIN LATERAL (
                        SELECT run.connection_validation_run_id, run.status
                        FROM connection_validation_run run
                        WHERE run.source_version_id = mapping.source_version_id
                          AND run.target_version_id = mapping.target_version_id
                        ORDER BY run.started_at DESC,
                                 run.connection_validation_run_id DESC
                        LIMIT 1
                    ) latest ON TRUE
                    WHERE {where}
                    ORDER BY mapping.updated_at DESC, mapping.mapping_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    [api_id, api_id, api_id, api_id, *params, limit, offset],
                )
                return cursor.fetchall(), total

    def create_version(self, api_id: int, actor_id: int, previous_id: int | None, data: VersionWriteRequest) -> int:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                if previous_id is not None:
                    cursor.execute("UPDATE api_version SET is_current = FALSE WHERE api_id = %s AND version_id = %s", (api_id, previous_id))
                cursor.execute(
                    """
                    INSERT INTO api_version (
                        api_id, created_by, version_number, change_note, status, is_current,
                        previous_version_id, api_name, endpoint_url, protocol_type, category,
                        capability_category, description, input_format, output_format
                    ) VALUES (
                        %s, %s, %s, %s, 'DRAFT', TRUE, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    ) RETURNING version_id
                    """,
                    (
                        api_id, actor_id, data.version_number, data.change_note, previous_id,
                        data.api_name, data.endpoint_url, data.protocol_type, data.category,
                        data.capability_category, data.description, data.input_format, data.output_format,
                    ),
                )
                version_id = cursor.fetchone()["version_id"]
                self._save_version_children(cursor, api_id, version_id, data, insert=True)
                cursor.execute(
                    """
                    UPDATE api_submission
                    SET current_version_id = %s, api_name = %s, status = 'DRAFT',
                        withdrawn_reason = NULL, withdrawn_at = NULL, withdrawn_by = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE api_id = %s
                    """,
                    (version_id, data.api_name, api_id),
                )
                cursor.execute(
                    """
                    INSERT INTO api_version_event
                        (version_id, api_id, actor_user_id, event_type, from_status, to_status, message)
                    VALUES (%s, %s, %s, 'CREATED', NULL, 'DRAFT', %s)
                    """,
                    (version_id, api_id, actor_id, data.change_note),
                )
                return version_id

    def update_version(self, api_id: int, version_id: int, actor_id: int, data: VersionWriteRequest) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE api_version SET
                        version_number = %s, change_note = %s, api_name = %s,
                        endpoint_url = %s, protocol_type = %s, category = %s,
                        capability_category = %s, description = %s,
                        input_format = %s, output_format = %s
                    WHERE api_id = %s AND version_id = %s
                    """,
                    (
                        data.version_number, data.change_note, data.api_name, data.endpoint_url,
                        data.protocol_type, data.category, data.capability_category, data.description,
                        data.input_format, data.output_format, api_id, version_id,
                    ),
                )
                self._save_version_children(cursor, api_id, version_id, data, insert=False)
                cursor.execute("UPDATE api_submission SET api_name = %s, updated_at = CURRENT_TIMESTAMP WHERE api_id = %s", (data.api_name, api_id))
                cursor.execute(
                    """
                    INSERT INTO api_version_event
                        (version_id, api_id, actor_user_id, event_type, from_status, to_status, message)
                    VALUES (%s, %s, %s, 'UPDATED', 'DRAFT', 'DRAFT', %s)
                    """,
                    (version_id, api_id, actor_id, data.change_note),
                )

    @staticmethod
    def _save_version_children(cursor, api_id: int, version_id: int, data: VersionWriteRequest, *, insert: bool) -> None:
        if insert:
            cursor.execute(
                """
                INSERT INTO auth_metadata
                    (api_id, version_id, auth_method, auth_description, security_scheme_name, is_complete)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (api_id, version_id, data.auth_method, data.auth_description, data.security_scheme_name, data.auth_is_complete),
            )
            cursor.execute(
                """
                INSERT INTO api_specification
                    (version_id, spec_type, source_type, file_path, raw_content)
                VALUES (%s, %s, 'FILE_UPLOAD', %s, %s)
                """,
                (version_id, data.spec_type, f"inline/version_{version_id}.txt", data.specification),
            )
            sync_api_schemas_from_spec(
                cursor,
                api_id=api_id,
                version_id=version_id,
                spec_type=data.spec_type,
                spec_content=data.specification,
                input_format=data.input_format,
                output_format=data.output_format,
            )
            return
        cursor.execute(
            """
            UPDATE auth_metadata SET auth_method = %s, auth_description = %s,
                security_scheme_name = %s, is_complete = %s
            WHERE auth_id = (
                SELECT auth_id FROM auth_metadata WHERE api_id = %s AND version_id = %s
                ORDER BY auth_id DESC LIMIT 1
            )
            """,
            (data.auth_method, data.auth_description, data.security_scheme_name, data.auth_is_complete, api_id, version_id),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO auth_metadata
                    (api_id, version_id, auth_method, auth_description, security_scheme_name, is_complete)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (api_id, version_id, data.auth_method, data.auth_description, data.security_scheme_name, data.auth_is_complete),
            )
        cursor.execute(
            """
            UPDATE api_specification SET spec_type = %s, source_type = 'FILE_UPLOAD',
                file_path = %s, spec_url = NULL, raw_content = %s, uploaded_at = CURRENT_TIMESTAMP
            WHERE version_id = %s
            """,
            (data.spec_type, f"inline/version_{version_id}.txt", data.specification, version_id),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO api_specification
                    (version_id, spec_type, source_type, file_path, raw_content)
                VALUES (%s, %s, 'FILE_UPLOAD', %s, %s)
                """,
                (version_id, data.spec_type, f"inline/version_{version_id}.txt", data.specification),
            )
        sync_api_schemas_from_spec(
            cursor,
            api_id=api_id,
            version_id=version_id,
            spec_type=data.spec_type,
            spec_content=data.specification,
            input_format=data.input_format,
            output_format=data.output_format,
        )
