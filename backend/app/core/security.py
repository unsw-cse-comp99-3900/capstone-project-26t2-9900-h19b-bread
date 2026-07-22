import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.core.database import get_connection

BACKEND_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(BACKEND_ENV_PATH)

security = HTTPBearer()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def create_access_token(
    user_id: int,
    email: str,
    role: str,
    enterprise_id: int,
) -> str:
    secret_key = os.getenv("JWT_SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")

    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "enterprise_id": str(enterprise_id),
        "exp": expire,
    }

    return jwt.encode(payload, secret_key, algorithm=algorithm)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    secret_key = os.getenv("JWT_SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")

    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not configured.")

    token = credentials.credentials

    try:
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])

        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")
        enterprise_id = payload.get("enterprise_id")

        if not user_id or not email or not role or not enterprise_id:
            raise _unauthorized("Invalid token payload.")

        try:
            user_id_int = int(user_id)
            enterprise_id_int = int(enterprise_id)
        except (TypeError, ValueError):
            raise _unauthorized("Invalid token payload.")

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, email, role, enterprise_id, status
                    FROM app_user
                    WHERE user_id = %s
                    """,
                    (user_id_int,),
                )
                user = cursor.fetchone()

        if user is None:
            raise _unauthorized("User session is no longer valid. Please sign in again.")

        if user["status"] != "ACTIVE":
            raise _unauthorized("User account is not active.")

        if (
            normalize_email := str(user["email"]).lower()
        ) != str(email).lower() or str(user["role"]) != str(role) or int(user["enterprise_id"]) != enterprise_id_int:
            raise _unauthorized("User session is stale. Please sign in again.")

        return {
            "user_id": user_id_int,
            "email": normalize_email,
            "role": user["role"],
            "enterprise_id": enterprise_id_int,
        }

    except JWTError:
        raise _unauthorized("Invalid or expired token.")


def require_role(*allowed_roles: str):
    def role_checker(current_user: dict[str, Any] = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permission.",
            )

        return current_user

    return role_checker
