from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, exists
from app.core.database import get_db
from app.core.dependencies import RequireTeacher
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.models.robot import RobotStatus, RobotQuestion
from app.models.usage_log import UsageLog
from app.schemas.usage import StudentUsageResponse

router = APIRouter(prefix="/api/teacher", tags=["teacher"])


async def teacher_can_access_student(db: AsyncSession, teacher_id: str, student_id: str) -> bool:
    from app.models.course import Course, Enrollment
    return bool(await db.scalar(select(exists().where(
        Enrollment.student_id == student_id,
        Enrollment.course_id == Course.id,
        Course.teacher_id == teacher_id,
    ))))


@router.get("/students")
async def list_students(
    search: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * page_size
    from app.models.course import Course, Enrollment
    query = select(User).join(Enrollment, Enrollment.student_id == User.id).join(Course, Course.id == Enrollment.course_id).where(
        User.role == "student", Course.teacher_id == current_user.id
    ).distinct()
    if search:
        query = query.where(
            (User.student_id.ilike(f"%{search}%")) | (User.display_name.ilike(f"%{search}%"))
        )
    result = await db.execute(query.order_by(User.student_id).offset(offset).limit(page_size))
    students = result.scalars().all()

    count_query = select(func.count(User.id)).join(Enrollment, Enrollment.student_id == User.id).join(Course, Course.id == Enrollment.course_id).where(
        User.role == "student", Course.teacher_id == current_user.id
    ).distinct()
    if search:
        count_query = count_query.where(
            (User.student_id.ilike(f"%{search}%")) | (User.display_name.ilike(f"%{search}%"))
        )
    total = (await db.execute(count_query)).scalar() or 0

    return {
        "students": [s.to_dict() for s in students],
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
    """Teacher can view any student's full conversation list."""
    if not await teacher_can_access_student(db, current_user.id, student_id):
        raise HTTPException(status_code=403, detail="Student is outside your courses")
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == student_id)
        .order_by(desc(Conversation.updated_at))
        .offset(offset).limit(page_size)
    )
    conversations = result.scalars().all()
    count = (await db.execute(
        select(func.count(Conversation.id)).where(Conversation.user_id == student_id)
    )).scalar() or 0

    return {
        "conversations": [
            {
                "id": c.id,
                "title": c.title,
                "course_id": c.course_id,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
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
    """Teacher can view full message content for any student's conversation."""
    if not await teacher_can_access_student(db, current_user.id, student_id):
        raise HTTPException(status_code=403, detail="Student is outside your courses")
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Message).join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.conversation_id == conversation_id, Conversation.user_id == student_id)
        .order_by(Message.created_at)
        .offset(offset).limit(page_size)
    )
    messages = result.scalars().all()
    count = (await db.execute(
        select(func.count(Message.id)).join(Conversation, Message.conversation_id == Conversation.id).where(
            Message.conversation_id == conversation_id, Conversation.user_id == student_id
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
    """Teacher can view detailed usage stats for any student."""
    if not await teacher_can_access_student(db, current_user.id, student_id):
        raise HTTPException(status_code=403, detail="Student is outside your courses")
    # Message count
    msg_count = (await db.execute(
        select(func.count(Message.id))
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == student_id)
    )).scalar() or 0

    # Conversation count
    conv_count = (await db.execute(
        select(func.count(Conversation.id)).where(Conversation.user_id == student_id)
    )).scalar() or 0

    # Login count
    login_count = (await db.execute(
        select(func.count(UsageLog.id)).where(
            UsageLog.user_id == student_id, UsageLog.action == "login"
        )
    )).scalar() or 0

    # Robot questions
    robot_count = (await db.execute(
        select(func.count(RobotQuestion.id)).where(RobotQuestion.student_id == student_id)
    )).scalar() or 0

    # Last active
    last_msg = (await db.execute(
        select(Message.created_at)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == student_id)
        .order_by(desc(Message.created_at))
        .limit(1)
    )).scalar_one_or_none()

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
        "total_login_count": login_count,
        "total_robot_questions": robot_count,
    }


@router.get("/dashboard")
async def teacher_dashboard(
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    total_students = (await db.execute(
        select(func.count(User.id)).where(User.role == "student")
    )).scalar() or 0

    from datetime import datetime, timezone
    from sqlalchemy import cast, Date
    today = datetime.now(timezone.utc).date()
    total_messages_today = (await db.execute(
        select(func.count(Message.id)).where(cast(Message.created_at, Date) == today)
    )).scalar() or 0

    from app.models.course import Course, Enrollment
    total_conversations = (await db.execute(
        select(func.count(Conversation.id)).join(Enrollment, Enrollment.student_id == Conversation.user_id).join(
            Course, Course.id == Enrollment.course_id
        ).where(Course.teacher_id == current_user.id)
    )).scalar() or 0

    total_robot_questions = (await db.execute(
        select(func.count(RobotQuestion.id)).join(User, User.id == RobotQuestion.student_id, isouter=True)
        .join(Enrollment, Enrollment.student_id == User.id, isouter=True)
        .join(Course, Course.id == Enrollment.course_id, isouter=True)
        .where((Course.teacher_id == current_user.id) | (RobotQuestion.student_id.is_(None)))
    )).scalar() or 0

    return {
        "total_students": total_students,
        "total_messages_today": total_messages_today,
        "total_conversations": total_conversations,
        "total_robot_questions": total_robot_questions,
    }
