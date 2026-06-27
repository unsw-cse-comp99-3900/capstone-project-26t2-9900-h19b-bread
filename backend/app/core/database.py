import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import Connection
from psycopg.rows import dict_row

BACKEND_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

# Load backend/.env if present. Existing OS env vars take precedence.
load_dotenv(BACKEND_ENV_PATH)

DATABASE_URL_ENV = "DATABASE_URL"


class DatabaseConfigError(RuntimeError):
    """Raised when database connection settings are missing or invalid."""


def get_database_url() -> str:
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        raise DatabaseConfigError(
            f"{DATABASE_URL_ENV} is not set. "
            "Set it to a PostgreSQL connection string before using the database."
        )
    return database_url


def create_connection() -> Connection:
    return psycopg.connect(get_database_url(), row_factory=dict_row)


@contextmanager
def get_connection() -> Iterator[Connection]:
    connection = create_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def check_database_connection() -> bool:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS ok")
            row = cursor.fetchone()
            return row is not None and row["ok"] == 1
