from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from app.models.user import User
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.services.sms_service import verify_sms


async def register_user(
    db: AsyncSession,
    student_id: str,
    phone: str,
    password: str,
    sms_code: str,
    display_name: str = "",
) -> dict:
    # Verify SMS
    if not await verify_sms(phone, sms_code):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired SMS code")

    # Check if student_id or phone already exists
    existing = await db.execute(
        select(User).where((User.student_id == student_id) | (User.phone == phone))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Student ID or phone already registered")

    # Determine role (default to student for self-registration)
    role = "student"

    user = User(
        student_id=student_id,
        phone=phone,
        password_hash=hash_password(password),
        display_name=display_name or f"Student_{student_id}",
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id, user.role)

    return {
        "user": user.to_dict(),
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
    }


async def login_user(db: AsyncSession, login: str, password: str) -> dict:
    # Login by student_id or phone
    result = await db.execute(
        select(User).where((User.student_id == login) | (User.phone == login))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id, user.role)

    return {
        "user": user.to_dict(),
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
    }


async def refresh_access_token(refresh_token: str) -> dict:
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    role = payload.get("role", "student")

    new_access = create_access_token(user_id, role)
    new_refresh = create_refresh_token(user_id, role)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }
