from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from datetime import datetime

from psycopg import Connection

from app.core.database import get_connection
from app.lifecycle.enums import (
    ApiStatus,
    ApiVersionStatus,
    ValidationOverallStatus,
    ValidationStage,
    ValidationStageStatus,
)


class PostgresLifecycleRepository:
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

    def get_api_status(self, api_id: int) -> ApiStatus | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT status
                    FROM api_submission
                    WHERE api_id = %s
                    """,
                    (api_id,),
                )
                row = cursor.fetchone()

        if row is None:
            return None
        return ApiStatus(row["status"])

    def get_api_updated_at(self, api_id: int) -> datetime | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT updated_at
                    FROM api_submission
                    WHERE api_id = %s
                    """,
                    (api_id,),
                )
                row = cursor.fetchone()

        if row is None:
            return None
        return row["updated_at"]

    def update_api_status(self, api_id: int, status: ApiStatus) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE api_submission
                    SET status = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE api_id = %s
                    """,
                    (status.value, api_id),
                )

    def mark_api_withdrawn(
        self,
        api_id: int,
        actor_id: int,
        reason: str | None,
    ) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE api_submission
                    SET status = %s,
                        withdrawn_reason = %s,
                        withdrawn_at = CURRENT_TIMESTAMP,
                        withdrawn_by = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE api_id = %s
                    """,
                    (ApiStatus.WITHDRAWN.value, reason, actor_id, api_id),
                )

    def get_current_version_id(self, api_id: int) -> int | None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT version_id
                    FROM api_version
                    WHERE api_id = %s
                    ORDER BY created_at DESC, version_id DESC
                    LIMIT 1
                    """,
                    (api_id,),
                )
                row = cursor.fetchone()

        if row is None:
            return None
        return row["version_id"]

    def update_version_status(
        self,
        version_id: int,
        status: ApiVersionStatus,
    ) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE api_version
                    SET status = %s
                    WHERE version_id = %s
                    """,
                    (status.value, version_id),
                )

    def create_validation_run(
        self,
        api_id: int,
        version_id: int,
        overall_status: ValidationOverallStatus,
    ) -> int:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO validation_run (
                        api_id,
                        version_id,
                        overall_status,
                        completed_at
                    )
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    RETURNING validation_run_id
                    """,
                    (api_id, version_id, overall_status.value),
                )
                row = cursor.fetchone()

        return row["validation_run_id"]

    def save_validation_result(
        self,
        validation_run_id: int,
        stage: ValidationStage,
        status: ValidationStageStatus,
        message: str | None,
        error_detail: str | None,
    ) -> None:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO validation_result (
                        validation_run_id,
                        stage,
                        status,
                        message,
                        error_detail
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        validation_run_id,
                        stage.value,
                        status.value,
                        message,
                        error_detail,
                    ),
                )
