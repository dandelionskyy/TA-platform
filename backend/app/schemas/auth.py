from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    student_id: str = Field(..., min_length=1, max_length=20)
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6, max_length=100)
    sms_code: str = Field(..., min_length=4, max_length=6)
    display_name: str = Field(default="", max_length=100)


class LoginRequest(BaseModel):
    login: str = Field(..., min_length=1, max_length=20)  # student_id or phone
    password: str = Field(..., min_length=1, max_length=100)


class SendSmsRequest(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    student_id: str
    phone: str
    display_name: str
    role: str
    is_active: bool


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: TokenResponse


class RefreshRequest(BaseModel):
    refresh_token: str
