from fastapi import APIRouter, Depends, HTTPException, status
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
from app.services.auth_service import register_user, login_user, refresh_access_token
from app.services.sms_service import send_sms

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
async def refresh(req: RefreshRequest):
    result = await refresh_access_token(req.refresh_token)
    return result


@router.post("/send-sms")
async def send_sms_code(req: SendSmsRequest):
    ok = await send_sms(req.phone)
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send SMS")
    return {"message": "SMS code sent", "phone": req.phone}


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user.to_dict()
