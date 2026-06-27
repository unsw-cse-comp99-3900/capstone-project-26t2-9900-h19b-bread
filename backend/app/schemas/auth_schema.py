from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class UserInfo(BaseModel):
    user_id: str
    email: str
    role: str
    enterprise_id: str


class LoginResponse(BaseModel):
    status: str
    token: str | None = None
    user: UserInfo | None = None
    message: str