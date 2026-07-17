from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    credits: int
    is_admin: bool = False


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


# --- 管理员后台: 用户管理 ---


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    credits: int = Field(default=20, ge=0)


class AdminResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6, max_length=128)


class AdminUpdateCreditsRequest(BaseModel):
    credits: int = Field(ge=0)


class AdminUserItem(BaseModel):
    id: str
    email: EmailStr
    credits: int
    status: str
    is_admin: bool
    created_at: datetime | None = None


class AdminUserListOut(BaseModel):
    users: list[AdminUserItem]
