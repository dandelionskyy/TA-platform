from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import RequireStudent
from app.models.user import User
from app.services.chat_service import process_chat, get_user_conversations, get_conversation_messages

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/send")
async def chat_send(
    message: str = Form(...),
    conversation_id: Optional[str] = Form(None),
    course_id: Optional[str] = Form(None),
    chapter_index: Optional[int] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(RequireStudent),
    db: AsyncSession = Depends(get_db),
):
    file_data = None
    filename = None
    if file:
        file_data = await file.read()
        filename = file.filename

    result = await process_chat(
        db=db,
        user_id=current_user.id,
        message=message,
        conversation_id=conversation_id,
        course_id=course_id,
        chapter_index=chapter_index,
        file_data=file_data,
        filename=filename,
    )
    return result


@router.get("/conversations")
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(RequireStudent),
    db: AsyncSession = Depends(get_db),
):
    return await get_user_conversations(db, current_user.id, page, page_size)


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(RequireStudent),
    db: AsyncSession = Depends(get_db),
):
    return await get_conversation_messages(db, current_user.id, conversation_id, page, page_size)
