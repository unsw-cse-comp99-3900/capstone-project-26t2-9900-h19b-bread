import os

from fastapi import APIRouter, HTTPException
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from app.core.database import get_connection
from app.core.passwords import hash_password, verify_password
from app.core.security import create_access_token
from app.schemas.auth_schema import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UserInfo,
)

router = APIRouter()


def normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    normalized_email = normalize_email(request.email)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    user_id,
                    enterprise_id,
                    email,
                    role,
                    status,
                    password_hash
                FROM app_user
                WHERE email = %s;
                """,
                (normalized_email,),
            )
            row = cursor.fetchone()

    if row is None:
        return LoginResponse(
            status="fail",
            token=None,
            user=None,
            message="Invalid email or password.",
        )

    if row["status"] != "ACTIVE":
        return LoginResponse(
            status="fail",
            token=None,
            user=None,
            message="User account is not active.",
        )

    password_valid, needs_upgrade = verify_password(
        request.password,
        row["password_hash"],
    )
    if not password_valid:
        return LoginResponse(
            status="fail",
            token=None,
            user=None,
            message="Invalid email or password.",
        )

    if needs_upgrade:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE app_user SET password_hash = %s WHERE user_id = %s",
                    (hash_password(request.password), row["user_id"]),
                )

    token = create_access_token(
        user_id=row["user_id"],
        email=row["email"],
        role=row["role"],
        enterprise_id=row["enterprise_id"],
    )

    return LoginResponse(
        status="success",
        token=token,
        user=UserInfo(
            user_id=str(row["user_id"]),
            email=row["email"],
            role=row["role"],
            enterprise_id=str(row["enterprise_id"]),
        ),
        message="Login successful.",
    )


@router.post("/register", response_model=RegisterResponse)
def register(request: RegisterRequest) -> RegisterResponse:
    if os.getenv("ALLOW_PUBLIC_REGISTRATION", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Public registration is disabled.")

    try:
        enterprise_id = int(os.environ["PUBLIC_REGISTRATION_ENTERPRISE_ID"])
        if enterprise_id <= 0:
            raise ValueError
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Public registration is not configured.",
        )

    password_hash = hash_password(request.password)
    normalized_email = normalize_email(request.email)

    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO app_user (
                        enterprise_id,
                        name,
                        email,
                        password_hash,
                        role,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, 'ACTIVE')
                    RETURNING user_id, enterprise_id, email, role;
                    """,
                    (
                        enterprise_id,
                        request.name,
                        normalized_email,
                        password_hash,
                        "PUBLISHER",
                    ),
                )
                row = cursor.fetchone()

        token = create_access_token(
            user_id=row["user_id"],
            email=row["email"],
            role=row["role"],
            enterprise_id=row["enterprise_id"],
        )

        return RegisterResponse(
            status="success",
            token=token,
            user=UserInfo(
                user_id=str(row["user_id"]),
                email=row["email"],
                role=row["role"],
                enterprise_id=str(row["enterprise_id"]),
            ),
            message="User registered successfully.",
        )

    except UniqueViolation:
        raise HTTPException(status_code=409, detail="Email already exists.")

    except ForeignKeyViolation:
        raise HTTPException(status_code=503, detail="Registration enterprise is unavailable.")
