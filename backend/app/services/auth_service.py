from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, status
from app.models.user import User
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token, hash_token
from app.models.usage_log import UsageLog, RefreshToken
from app.services.audit_service import write_audit
from app.core.config import get_settings

settings = get_settings()
from app.services.sms_service import verify_sms


async def register_user(
    db: AsyncSession,
    student_id: str,
    phone: str,
    password: str,
    sms_code: str,
    display_name: str = "",
) -> dict:
    # Verify the one-time registration code. It may come from SMS or the on-page flow.
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

    access_token, refresh_token = await issue_tokens(db, user)
    await write_audit(db, "register", actor_id=user.id, target_type="user", target_id=user.id)

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

    user.last_login_at = datetime.now(timezone.utc)
    db.add(UsageLog(user_id=user.id, action="login"))
    access_token, refresh_token = await issue_tokens(db, user)
    await write_audit(db, "login", actor_id=user.id, target_type="user", target_id=user.id)

    return {
        "user": user.to_dict(),
        "tokens": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
    }


async def issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id, user.role)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
    ))
    await db.flush()
    return access_token, refresh_token


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict:
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    stored = await db.scalar(select(RefreshToken).where(
        RefreshToken.token_hash == hash_token(refresh_token),
        RefreshToken.revoked_at.is_(None),
    ))
    if not stored or stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked or expired")

    user = await db.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    stored.revoked_at = datetime.now(timezone.utc)
    new_access, new_refresh = await issue_tokens(db, user)

    await write_audit(db, "token_refresh", actor_id=user.id, target_type="user", target_id=user.id)

    return {
        "access_token": new_access,
            "refresh_token": new_refresh,
        "token_type": "bearer",
    }


async def revoke_refresh_token(db: AsyncSession, refresh_token: str, user_id: str | None = None) -> None:
    query = select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
    stored = await db.scalar(query)
    if stored and (user_id is None or stored.user_id == user_id):
        stored.revoked_at = datetime.now(timezone.utc)
        await db.flush()
