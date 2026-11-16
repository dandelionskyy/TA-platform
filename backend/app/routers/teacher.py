from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, exists, cast, Date
from app.core.database import get_db
from app.core.dependencies import RequireTeacher
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.models.course import Course, Enrollment

router = APIRouter(prefix="/api/teacher", tags=["teacher"])


async def teacher_can_access_student(db: AsyncSession, teacher_id: str, student_id: str) -> bool:
    return bool(await db.scalar(select(exists().where(
        Enrollment.student_id == student_id,
        Enrollment.course_id == Course.id,
        Course.teacher_id == teacher_id,
    ))))


def teacher_conversation_scope(teacher_id: str):
    """Only chats explicitly belonging to a course taught by this teacher."""
    return exists().where(Course.id == Conversation.course_id, Course.teacher_id == teacher_id)


@router.get("/students")
async def list_students(
    search: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
    course_id: str | None = None,
):
    offset = (page - 1) * page_size
    query = select(User).join(Enrollment, Enrollment.student_id == User.id).join(Course, Course.id == Enrollment.course_id).where(
        User.role == "student", Course.teacher_id == current_user.id
    ).distinct()
    if course_id:
        query = query.where(Course.id == course_id)
    if search:
        query = query.where(
            (User.student_id.ilike(f"%{search}%")) | (User.display_name.ilike(f"%{search}%"))
        )
    result = await db.execute(query.order_by(User.student_id).offset(offset).limit(page_size))
    students = result.scalars().all()

    count_query = select(func.count(func.distinct(User.id))).join(Enrollment, Enrollment.student_id == User.id).join(Course, Course.id == Enrollment.course_id).where(
        User.role == "student", Course.teacher_id == current_user.id
    )
    if course_id:
        count_query = count_query.where(Course.id == course_id)
    if search:
        count_query = count_query.where(
            (User.student_id.ilike(f"%{search}%")) | (User.display_name.ilike(f"%{search}%"))
        )
    total = (await db.execute(count_query)).scalar() or 0

    memberships = (await db.execute(
        select(Enrollment.student_id, Course.id, Course.name)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Enrollment.student_id.in_([s.id for s in students]), Course.teacher_id == current_user.id)
        .order_by(Course.name)
    )).all() if students else []
    course_map = {}
    for uid, cid, name in memberships:
        course_map.setdefault(uid, []).append({"id": cid, "name": name})

    return {
        "students": [{**s.to_dict(), "courses": course_map.get(s.id, [])} for s in students],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/students/{student_id}/conversations")
async def get_student_conversations(
    student_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    """Teacher can view chats from their own courses only."""
    if not await teacher_can_access_student(db, current_user.id, student_id):
        raise HTTPException(status_code=403, detail="Student is outside your courses")
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == student_id, teacher_conversation_scope(current_user.id))
        .order_by(desc(Conversation.updated_at), Conversation.id)
        .offset(offset).limit(page_size)
    )
    conversations = result.scalars().all()
    count = (await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.user_id == student_id, teacher_conversation_scope(current_user.id)
        )
    )).scalar() or 0

    conversation_stats = {}
    if conversations:
        stats = (await db.execute(
            select(
                Message.conversation_id,
                func.count(Message.id),
                func.coalesce(func.sum(Message.token_count), 0),
                func.max(Message.created_at),
                func.count(Message.token_count),
            )
            .where(Message.conversation_id.in_([conversation.id for conversation in conversations]))
            .group_by(Message.conversation_id)
        )).all()
        conversation_stats = {
            conversation_id: {
                "message_count": int(message_count or 0),
                "total_tokens": int(total_tokens or 0),
                "last_message_at": last_message_at.isoformat() if last_message_at else None,
                "recorded_usage_count": recorded_usage_count,
            }
            for conversation_id, message_count, total_tokens, last_message_at, recorded_usage_count in stats
        }

    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "course_id": c.course_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                **conversation_stats.get(c.id, {"message_count": 0, "total_tokens": 0, "last_message_at": None, "recorded_usage_count": 0}),
            }
            for c in conversations
        ],
        "total": count,
        "page": page,
        "page_size": page_size,
    }


@router.get("/students/{student_id}/conversations/{conversation_id}/messages")
async def get_student_messages(
    student_id: str,
    conversation_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    """Teacher can view messages only from a conversation in their course."""
    if not await teacher_can_access_student(db, current_user.id, student_id):
        raise HTTPException(status_code=403, detail="Student is outside your courses")
    allowed = await db.scalar(select(Conversation.id).where(
        Conversation.id == conversation_id,
        Conversation.user_id == student_id,
        teacher_conversation_scope(current_user.id),
    ))
    if not allowed:
        raise HTTPException(status_code=404, detail="Conversation not found")
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Message).join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Message.conversation_id == conversation_id,
            Conversation.user_id == student_id,
            teacher_conversation_scope(current_user.id),
        )
        .order_by(Message.created_at, Message.id)
        .offset(offset).limit(page_size)
    )
    messages = result.scalars().all()
    count = (await db.execute(
        select(func.count(Message.id)).join(Conversation, Message.conversation_id == Conversation.id).where(
            Message.conversation_id == conversation_id,
            Conversation.user_id == student_id,
            teacher_conversation_scope(current_user.id),
        )
    )).scalar() or 0

    return {
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "context_source": m.context_source,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "token_count": m.token_count,
                "prompt_tokens": m.prompt_tokens,
                "completion_tokens": m.completion_tokens,
                "model_name": m.model_name,
                "response_time_ms": m.response_time_ms,
            }
            for m in messages
        ],
        "total": count,
        "page": page,
        "page_size": page_size,
    }


@router.get("/students/{student_id}/usage-stats")
async def get_student_usage(
    student_id: str,
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    """Return detailed, course-scoped AI usage for a student."""
    if not await teacher_can_access_student(db, current_user.id, student_id):
        raise HTTPException(status_code=403, detail="Student is outside your courses")
    # Message count
    msg_count = (await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == student_id, teacher_conversation_scope(current_user.id))
    )).scalar() or 0

    ai_filters = [
        Conversation.user_id == student_id,
        Message.role == "assistant",
        teacher_conversation_scope(current_user.id),
    ]
    ai_count = (await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(*ai_filters)
    )).scalar() or 0
    token_totals = (await db.execute(
        select(
            func.coalesce(func.sum(Message.prompt_tokens), 0),
            func.coalesce(func.sum(Message.completion_tokens), 0),
            func.coalesce(func.sum(Message.token_count), 0),
            func.count(Message.token_count),
            func.count(Message.prompt_tokens),
            func.count(Message.completion_tokens),
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(*ai_filters)
    )).one()

    # Conversation count
    conv_count = (await db.execute(
        select(func.count(Conversation.id)).where(
            Conversation.user_id == student_id, teacher_conversation_scope(current_user.id)
        )
    )).scalar() or 0

    # Last active
    last_msg = (await db.execute(
        select(Message.created_at)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == student_id, teacher_conversation_scope(current_user.id))
        .order_by(desc(Message.created_at))
        .limit(1)
    )).scalar_one_or_none()

    first_msg = (await db.execute(
        select(Message.created_at)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == student_id, teacher_conversation_scope(current_user.id))
        .order_by(Message.created_at)
        .limit(1)
    )).scalar_one_or_none()
    model_rows = (await db.execute(
        select(
            Message.model_name,
            func.count(Message.id),
            func.sum(Message.token_count),
            func.count(Message.token_count),
        )
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(*ai_filters)
        .group_by(Message.model_name)
        .order_by(desc(func.count(Message.id)))
    )).all()

    # Student info
    student_result = await db.execute(select(User).where(User.id == student_id))
    student = student_result.scalar_one_or_none()

    return {
        "user_id": student_id,
        "student_id": student.student_id if student else "",
        "display_name": student.display_name if student else "",
        "total_chat_messages": msg_count,
        "total_conversations": conv_count,
        "last_active_at": last_msg.isoformat() if last_msg else None,
        "total_login_count": None,  # Login and robot events have no reliable course scope.
        "total_robot_questions": None,
        "total_ai_responses": ai_count,
        "prompt_tokens": int(token_totals[0] or 0),
        "completion_tokens": int(token_totals[1] or 0),
        "total_tokens": int(token_totals[2] or 0),
        "first_active_at": first_msg.isoformat() if first_msg else None,
        "recorded_usage_count": token_totals[3],
        "missing_usage_count": ai_count - token_totals[3],
        "recorded_prompt_count": token_totals[4],
        "recorded_completion_count": token_totals[5],
        "models": [
            {"model_name": model_name, "responses": responses, "total_tokens": tokens, "recorded_usage_count": recorded}
            for model_name, responses, tokens, recorded in model_rows
        ],
    }


@router.get("/dashboard")
async def teacher_dashboard(
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    total_students = (await db.execute(
        select(func.count(func.distinct(Enrollment.student_id)))
        .join(Course, Course.id == Enrollment.course_id)
        .where(Course.teacher_id == current_user.id)
    )).scalar() or 0

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    total_messages_today = (await db.execute(
        select(func.count(Message.id)).join(Conversation, Conversation.id == Message.conversation_id)
        .where(cast(Message.created_at, Date) == today, teacher_conversation_scope(current_user.id))
    )).scalar() or 0
    total_conversations = (await db.execute(
        select(func.count(Conversation.id)).where(teacher_conversation_scope(current_user.id))
    )).scalar() or 0

    return {
        "total_students": total_students,
        "total_messages_today": total_messages_today,
        "total_conversations": total_conversations,
        "total_robot_questions": None,
    }
