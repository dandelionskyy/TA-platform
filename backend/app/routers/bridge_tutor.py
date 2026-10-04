"""Anonymous web tutor endpoints. Each turn is bound to the server-side pack."""

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.bridge import SessionCreate, SessionResponse, TutorRequest, TutorResponse
from app.services.bridge_sessions import (
    create_anonymous_session, delete_anonymous_session, load_anonymous_session,
)
from app.services.bridge_tutor import run_guarded_tutor

router = APIRouter(prefix="/api/bridge", tags=["BRIDGE tutor"])


@router.post("/sessions", response_model=SessionResponse)
async def start_bridge_session(
    data: SessionCreate,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await create_anonymous_session(db, data.module_id, data.language)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Module unavailable") from exc


@router.post("/tutor", response_model=TutorResponse)
async def bridge_tutor_turn(
    data: TutorRequest,
    x_bridge_session: str | None = Header(default=None, alias="X-Bridge-Session"),
    db: AsyncSession = Depends(get_db),
):
    session = await load_anonymous_session(db, x_bridge_session or "")
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired or unavailable")
    if not data.message.strip():
        raise HTTPException(status_code=422, detail="Enter a question")
    try:
        return await run_guarded_tutor(db, session, data.message.strip(), data.language)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Module unavailable") from exc


@router.delete("/sessions/current")
async def remove_bridge_session(
    x_bridge_session: str | None = Header(default=None, alias="X-Bridge-Session"),
    db: AsyncSession = Depends(get_db),
):
    session = await load_anonymous_session(db, x_bridge_session or "")
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired or unavailable")
    await delete_anonymous_session(db, session)
    return {"deleted": True}
