from fastapi import APIRouter
from app.schemas.auth_schema import LoginRequest, LoginResponse, UserInfo

router = APIRouter()


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