from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    SendSmsRequest,
    AuthResponse,
    TokenResponse,
    RefreshRequest,
)
from app.services.auth_service import register_user, login_user, refresh_access_token, revoke_refresh_token
from app.services.sms_service import issue_registration_code, send_sms
from app.core.dependencies import RequireTeacher
from app.core.security import hash_password
from app.services.audit_service import write_audit


class ProvisionUserRequest(BaseModel):
    student_id: str = Field(..., min_length=1, max_length=20)
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6, max_length=100)
    display_name: str = Field(default="", max_length=100)
    role: str = Field(default="ta", pattern="^(ta|student)$")

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await register_user(
        db=db,
        student_id=req.student_id,
        phone=req.phone,
        password=req.password,
        sms_code=req.sms_code,
        display_name=req.display_name,
    )
    return result


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await login_user(db=db, login=req.login, password=req.password)
    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await refresh_access_token(db, req.refresh_token)
    return result


@router.post("/logout")
async def logout(
    req: RefreshRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await revoke_refresh_token(db, req.refresh_token, current_user.id)
    return {"message": "Logged out"}


@router.post("/send-sms")
async def send_sms_code(req: SendSmsRequest):
    ok = await send_sms(req.phone)
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send SMS")
    return {"message": "SMS code sent", "phone": req.phone}


@router.post("/registration-code")
async def create_registration_code(
    req: SendSmsRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    code = await issue_registration_code(req.phone)
    if code is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait before requesting another code",
        )
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    await write_audit(
        db,
        "registration_code_issued",
        target_type="phone_suffix",
        target_id=req.phone[-4:],
        ip_address=forwarded_for or (request.client.host if request.client else None),
        metadata={"delivery": "on_page"},
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "message": "Registration code created",
        "phone": req.phone,
        "code": code,
        "expires_in": 300,
    }


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()


@router.post("/provision")
async def provision_user(
    req: ProvisionUserRequest,
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(select(User).where((User.student_id == req.student_id) | (User.phone == req.phone)))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student ID or phone already registered")
    user = User(
        student_id=req.student_id,
        phone=req.phone,
        password_hash=hash_password(req.password),
        display_name=req.display_name or req.student_id,
        role=req.role,
    )
    db.add(user)
    await db.flush()
    return user.to_dict()
