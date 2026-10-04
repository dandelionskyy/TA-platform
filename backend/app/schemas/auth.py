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
    # Match the registration form and use a single canonical Redis key per
    # mainland China mobile number. Alternate spellings cannot reset cooldown.
    phone: str = Field(..., min_length=11, max_length=11, pattern=r"^1[3-9][0-9]{9}$")


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
