import hashlib

from fastapi import APIRouter, HTTPException
from psycopg.errors import UniqueViolation, ForeignKeyViolation

from app.core.database import get_connection
from app.schemas.auth_schema import (
    LoginRequest,
    LoginResponse,
    UserInfo,
    RegisterRequest,
    RegisterResponse,
)

router = APIRouter()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest):
    # Sprint 1 mock login for frontend integration
    if request.email == "publisher@example.com" and request.password == "password123":
        return LoginResponse(
            status="success",
            token="mock-token-publisher-user-001",
            user=UserInfo(
                user_id="user_001",
                email=request.email,
                role="publisher",
                enterprise_id="ent_001",
            ),
            message="Login successful."
        )

    return LoginResponse(
        status="fail",
        token=None,
        user=None,
        message="Invalid email or password."
    )


@router.post("/register", response_model=RegisterResponse)
def register(request: RegisterRequest):
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

        return RegisterResponse(
            status="success",
            user=UserInfo(
                user_id=str(row["user_id"]),
                enterprise_id=str(row["enterprise_id"]),
                email=row["email"],
                role=row["role"],
            ),
            message="User registered successfully."
        )

    except UniqueViolation:
        raise HTTPException(status_code=409, detail="Email already exists.")

    except ForeignKeyViolation:
        raise HTTPException(status_code=400, detail="Invalid enterprise_id.")