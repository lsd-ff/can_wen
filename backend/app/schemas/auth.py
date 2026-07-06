from __future__ import annotations

from pydantic import BaseModel, Field


class EmailVerificationCodeRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class EmailVerificationCodeResponse(BaseModel):
    status: str
    email: str
    expires_in: int
    dev_code: str | None = None


class PhoneVerificationCodeRequest(BaseModel):
    phone_number: str = Field(min_length=1, max_length=32)


class PhoneVerificationCodeResponse(BaseModel):
    status: str
    phone_number: str
    expires_in: int
    dev_code: str | None = None


class EmailLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=4, max_length=8)
    device_id: str | None = Field(default=None, max_length=128)
    device_name: str | None = Field(default=None, max_length=128)


class PhoneLoginRequest(BaseModel):
    phone_number: str = Field(min_length=1, max_length=32)
    code: str = Field(min_length=4, max_length=8)
    device_id: str | None = Field(default=None, max_length=128)
    device_name: str | None = Field(default=None, max_length=128)


class AuthUserResponse(BaseModel):
    id: str
    display_name: str
    username: str
    email: str = ""
    phone_number: str = ""
    avatar_url: str | None = None


class UpdateUserProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=700_000)


class EmailLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class RefreshTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserResponse


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class LogoutResponse(BaseModel):
    status: str
