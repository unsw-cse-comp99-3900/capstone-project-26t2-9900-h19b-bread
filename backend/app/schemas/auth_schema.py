from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("name", "email")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class RegisterResponse(BaseModel):
    status: str
    token: str | None = None
    user: UserInfo | None = None
    message: str
