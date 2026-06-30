import hashlib

from fastapi import APIRouter, HTTPException
from psycopg.errors import ForeignKeyViolation, UniqueViolation

from app.core.database import get_connection
from app.core.security import create_access_token
from app.schemas.auth_schema import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    UserInfo,
)

router = APIRouter()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    password_hash = hash_password(request.password)

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
                (request.email,),
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

    if row["password_hash"] != password_hash:
        return LoginResponse(
            status="fail",
            token=None,
            user=None,
            message="Invalid email or password.",
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
    password_hash = hash_password(request.password)

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
                        request.enterprise_id,
                        request.name,
                        request.email,
                        password_hash,
                        request.role,
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
        raise HTTPException(status_code=400, detail="Invalid enterprise_id.")