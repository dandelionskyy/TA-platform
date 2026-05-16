from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from app.core.database import get_db
from app.core.dependencies import RequireTA
from app.models.user import User
from app.models.conversation import Conversation, Message
from app.models.robot import RobotQuestion
from app.models.usage_log import UsageLog

router = APIRouter(prefix="/api/ta", tags=["ta"])


@router.get("/students/{student_id}/usage-stats")
async def get_student_usage(
    student_id: str,
    current_user: User = Depends(RequireTA),
    db: AsyncSession = Depends(get_db),
):
    """
    TA can see usage TIME and FREQUENCY only.
    NEVER returns message content.
    """
    # Verify student exists
    student_result = await db.execute(
        select(User).where(User.id == student_id, User.role == "student")
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    # Message count (count only, no content)
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

    # Robot questions count
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

    return {
        "user_id": student_id,
        "student_id": student.student_id,
        "display_name": student.display_name,
        "total_chat_messages": msg_count,
        "total_conversations": conv_count,
        "last_active_at": last_msg.isoformat() if last_msg else None,
        "total_login_count": login_count,
        "total_robot_questions": robot_count,
    }


@router.get("/dashboard")
async def ta_dashboard(
    current_user: User = Depends(RequireTA),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate anonymized stats. No individual student details."""
    total_students = (await db.execute(
        select(func.count(User.id)).where(User.role == "student")
    )).scalar() or 0

    total_messages = (await db.execute(
        select(func.count(Message.id))
    )).scalar() or 0

    total_conversations = (await db.execute(
        select(func.count(Conversation.id))
    )).scalar() or 0

    total_robot_questions = (await db.execute(
        select(func.count(RobotQuestion.id))
    )).scalar() or 0

    return {
        "total_students": total_students,
        "total_messages": total_messages,
        "total_conversations": total_conversations,
        "total_robot_questions": total_robot_questions,
    }
