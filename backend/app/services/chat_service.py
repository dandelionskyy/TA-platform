from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.models.conversation import Conversation, Message
from app.models.usage_log import UsageLog
from app.models.user import User
from app.ai.deepseek_client import get_deepseek_response
from app.ai.conversation_memory import conversation_memory
import uuid
from datetime import datetime, timezone


async def get_or_create_conversation(
    db: AsyncSession, user_id: str, conversation_id: Optional[str] = None,
    course_id: Optional[str] = None, chapter_index: Optional[int] = None,
) -> Conversation:
    if conversation_id:
        result = await db.execute(
            select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            return conv

    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=user_id,
        course_id=course_id,
        chapter_index=chapter_index,
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


async def save_message(
    db: AsyncSession, conversation_id: str, role: str, content: str,
    context_source: Optional[str] = None, filename_ref: Optional[str] = None,
) -> Message:
    msg = Message(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role=role,
        content=content,
        context_source=context_source,
        filename_ref=filename_ref,
    )
    db.add(msg)
    # Update conversation's updated_at
    await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = (await db.execute(select(Conversation).where(Conversation.id == conversation_id))).scalar_one_or_none()
    if conv:
        conv.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(msg)
    return msg


async def log_usage(db: AsyncSession, user_id: str, action: str, metadata: dict = None):
    log = UsageLog(user_id=user_id, action=action, metadata_=metadata or {})
    db.add(log)
    await db.flush()


async def process_chat(
    db: AsyncSession,
    user_id: str,
    message: str,
    conversation_id: Optional[str] = None,
    course_id: Optional[str] = None,
    chapter_index: Optional[int] = None,
    file_data: Optional[bytes] = None,
    filename: Optional[str] = None,
) -> dict:
    # Get or create conversation
    conv = await get_or_create_conversation(db, user_id, conversation_id, course_id, chapter_index)

    # Build conversation mode string for knowledge base lookup
    mode = "chatbot"
    if course_id and chapter_index is not None:
        # Fetch course name to construct mode
        from app.models.course import Course
        result = await db.execute(select(Course).where(Course.id == course_id))
        course = result.scalar_one_or_none()
        if course:
            slug = course.knowledge_base_path.replace(" ", "-") if course.knowledge_base_path else course.name.replace(" ", "-")
            mode = f"{slug}-ch{chapter_index}"

    # Get conversation history from Redis
    history = await conversation_memory.get_history(conv.id, max_messages=10)
    # Also get DB history as fallback
    if not history:
        result = await db.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at).limit(10)
        )
        db_messages = result.scalars().all()
        history = [{"role": m.role, "content": m.content} for m in db_messages]

    # Save user message
    user_msg = await save_message(db, conv.id, "user", message, filename_ref=filename)
    await conversation_memory.add_message(conv.id, "user", message)

    # Get AI response
    ai_result = await get_deepseek_response(
        user_question=message,
        mode=mode,
        file_data=file_data,
        filename=filename,
        conversation_history=history,
    )

    # Save AI response
    ai_msg = await save_message(
        db, conv.id, "assistant", ai_result["response"],
        context_source=ai_result.get("context_source"),
        filename_ref=ai_result.get("filename_display"),
    )
    await conversation_memory.add_message(conv.id, "assistant", ai_result["response"])

    # Log usage
    await log_usage(db, user_id, "chat_message", {"conversation_id": conv.id})

    return {
        "message_id": ai_msg.id,
        "conversation_id": conv.id,
        "response": ai_result["response"],
    }


async def get_user_conversations(db: AsyncSession, user_id: str, page: int = 1, page_size: int = 20) -> dict:
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(desc(Conversation.updated_at))
        .offset(offset).limit(page_size)
    )
    conversations = result.scalars().all()
    count_result = await db.execute(
        select(func.count(Conversation.id)).where(Conversation.user_id == user_id)
    )
    total = count_result.scalar() or 0
    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "course_id": c.course_id,
                "chapter_index": c.chapter_index,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_conversation_messages(
    db: AsyncSession, user_id: str, conversation_id: str, page: int = 1, page_size: int = 50
) -> dict:
    # Verify ownership
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
    )
    if not conv_result.scalar_one_or_none():
        return {"messages": [], "total": 0, "error": "Conversation not found"}

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .offset(offset).limit(page_size)
    )
    messages = result.scalars().all()
    count_result = await db.execute(
        select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
    )
    total = count_result.scalar() or 0
    return {
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "context_source": m.context_source,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
