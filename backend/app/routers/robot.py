from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.robot import RobotStatus, RobotQuestion

router = APIRouter(prefix="/api/robot", tags=["robot"])


@router.get("/status")
async def get_robot_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """All roles can see robot status, position, battery."""
    result = await db.execute(
        select(RobotStatus).order_by(RobotStatus.updated_at.desc()).limit(1)
    )
    robot = result.scalar_one_or_none()

    if not robot:
        return {
            "robot_name": "TA-Robot-01",
            "status": "offline",
            "battery_pct": 0,
            "position_x": None,
            "position_y": None,
            "position_label": "",
            "last_seen_at": None,
            "total_questions_today": 0,
        }

    # Count today's questions
    from sqlalchemy import cast, Date
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    question_count = (await db.execute(
        select(func.count(RobotQuestion.id))
        .where(RobotQuestion.robot_id == robot.id)
        .where(cast(RobotQuestion.created_at, Date) == today)
    )).scalar() or 0

    return {
        "robot_name": robot.robot_name,
        "status": robot.status,
        "battery_pct": robot.battery_pct,
        "position_x": robot.position_x,
        "position_y": robot.position_y,
        "position_label": robot.position_label,
        "last_seen_at": robot.last_seen_at.isoformat() if robot.last_seen_at else None,
        "total_questions_today": question_count,
    }


@router.get("/questions")
async def get_robot_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Teachers see full question details; TAs/Students only see count."""
    from app.core.dependencies import RequireTeacher

    if current_user.role != "teacher":
        return {"questions": [], "total": 0, "message": "Only teachers can view detailed questions"}

    offset = (page - 1) * page_size
    result = await db.execute(
        select(RobotQuestion)
        .order_by(RobotQuestion.created_at.desc())
        .offset(offset).limit(page_size)
    )
    questions = result.scalars().all()
    total = (await db.execute(select(func.count(RobotQuestion.id)))).scalar() or 0

    # Get student names
    student_ids = list(set(q.student_id for q in questions if q.student_id))
    student_names = {}
    if student_ids:
        users_result = await db.execute(select(User).where(User.id.in_(student_ids)))
        for u in users_result.scalars():
            student_names[u.id] = u.display_name

    return {
        "questions": [
            {
                "id": q.id,
                "student_id": q.student_id,
                "student_name": student_names.get(q.student_id, "") if q.student_id else "",
                "question_text": q.question_text,
                "response_text": q.response_text,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in questions
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
