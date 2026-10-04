"""Anonymous 30-day BRIDGE sessions; no identifying student details or chat logs."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.bridge import BridgeLearningEvent, BridgeModulePack, BridgeTutorSession
from app.schemas.bridge import SessionResponse


def _utc(value: datetime) -> datetime:
    """SQLite may return naive UTC datetimes despite timezone-aware columns."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def purge_expired_sessions(db: AsyncSession) -> int:
    """Delete learning events *with* expired tokens, even on SQLite without FK ON."""
    now = datetime.now(timezone.utc)
    ids = list((await db.scalars(
        select(BridgeTutorSession.id).where(BridgeTutorSession.expires_at <= now).limit(500)
    )).all())
    if not ids:
        return 0
    await db.execute(delete(BridgeLearningEvent).where(BridgeLearningEvent.session_id.in_(ids)))
    await db.execute(delete(BridgeTutorSession).where(BridgeTutorSession.id.in_(ids)))
    return len(ids)


async def create_anonymous_session(db: AsyncSession, module_id: str, language: str) -> SessionResponse:
    module = await db.scalar(select(BridgeModulePack).where(
        BridgeModulePack.id == module_id, BridgeModulePack.active.is_(True)
    ))
    if module is None:
        raise ValueError("Module is unavailable")
    token = secrets.token_urlsafe(32)
    session = BridgeTutorSession(
        token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        pseudonym=secrets.token_hex(16),
        module_id=module.id,
        language=language,
        stage="greeting",
        scaffold_count=0,
        mastery=False,
        expires_at=datetime.now(timezone.utc) + timedelta(days=get_settings().BRIDGE_SESSION_DAYS),
    )
    db.add(session)
    await db.flush()
    return SessionResponse(
        session_token=token, module_id=module.id, language=language,
        expires_at=session.expires_at, lock_status=bool(module.assessment_locked),
        welcome=("你好！你正在学习哪个概念？" if language == "zh"
                 else "Hello! Which concept are you working on?"),
    )


async def load_anonymous_session(db: AsyncSession, token: str) -> BridgeTutorSession | None:
    if not token or len(token) > 200:
        return None
    session = await db.scalar(select(BridgeTutorSession).where(
        BridgeTutorSession.token_hash == hashlib.sha256(token.encode("utf-8")).hexdigest()
    ))
    if session is None or _utc(session.expires_at) <= datetime.now(timezone.utc):
        return None
    # A pack disabled by staff immediately becomes inaccessible, including via
    # an already-issued token; no client value can override this server lookup.
    active = await db.scalar(select(BridgeModulePack.id).where(
        BridgeModulePack.id == session.module_id, BridgeModulePack.active.is_(True)
    ))
    return session if active else None


async def delete_anonymous_session(db: AsyncSession, session: BridgeTutorSession) -> None:
    await db.execute(delete(BridgeLearningEvent).where(BridgeLearningEvent.session_id == session.id))
    await db.delete(session)
