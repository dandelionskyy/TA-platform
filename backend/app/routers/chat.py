from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException, status
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import RequireStudent
from app.models.user import User
from app.services.chat_service import process_chat, get_user_conversations, get_conversation_messages
from app.ai.conversation_memory import conversation_memory
from app.models.conversation import Conversation
from app.models.file_asset import FileAsset
from app.core.config import get_settings
from sqlalchemy import select, delete

settings = get_settings()

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/send")
async def chat_send(
    message: str = Form(...),
    conversation_id: Optional[str] = Form(None),
    course_id: Optional[str] = Form(None),
    chapter_index: Optional[int] = Form(None),
    chapter_id: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: User = Depends(RequireStudent),
    db: AsyncSession = Depends(get_db),
):
    file_data = None
    filename = None
    if file:
        file_data = await file.read()
        if len(file_data) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File is too large")
        filename = file.filename
        allowed = {".pdf", ".pptx", ".docx", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
        import os
        if not filename or os.path.splitext(filename.lower())[1] not in allowed:
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported file type")

    try:
        result = await process_chat(
            db=db,
            user_id=current_user.id,
            message=message,
            conversation_id=conversation_id,
            course_id=course_id,
            chapter_index=chapter_index,
            chapter_id=chapter_id,
            file_data=file_data,
            filename=filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    if file and filename:
        db.add(FileAsset(
            user_id=current_user.id,
            conversation_id=result["conversation_id"],
            filename=filename[:255],
            mime_type=file.content_type,
            size_bytes=len(file_data or b""),
            processing_status="processed",
        ))
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


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(RequireStudent),
    db: AsyncSession = Depends(get_db),
):
    conversation = await db.scalar(select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ))
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    await db.delete(conversation)
    await conversation_memory.clear_history(conversation_id)
    return {"message": "Conversation deleted"}
