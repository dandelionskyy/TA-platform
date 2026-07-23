from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import RequireTeacher, get_current_user
from app.models.course import Course, CourseStaff, Enrollment
from app.models.messaging import DirectMessage, DirectThread, MessagePermission
from app.models.user import User

router = APIRouter(prefix="/api/messaging", tags=["messaging"])


class ThreadCreate(BaseModel):
    course_id: str
    recipient_id: str


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class PermissionUpdate(BaseModel):
    accepted: bool


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _user_dict(user: User | None) -> dict | None:
    if not user:
        return None
    return {
        "id": user.id,
        "student_id": user.student_id,
        "display_name": user.display_name,
        "role": user.role,
    }


def _canonical_participants(first: str, second: str) -> tuple[str, str]:
    return (first, second) if first < second else (second, first)


async def _course_for_user(db: AsyncSession, current_user: User, course_id: str) -> Course:
    course = await db.scalar(select(Course).where(Course.id == course_id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if current_user.role == "teacher":
        allowed = course.teacher_id == current_user.id
    elif current_user.role == "ta":
        allowed = bool(await db.scalar(select(exists().where(
            CourseStaff.course_id == course_id,
            CourseStaff.user_id == current_user.id,
            CourseStaff.role == "ta",
        ))))
    else:
        allowed = bool(await db.scalar(select(exists().where(
            Enrollment.course_id == course_id,
            Enrollment.student_id == current_user.id,
        ))))
    if not allowed:
        raise HTTPException(status_code=403, detail="Course access denied")
    return course


async def _member_in_course(db: AsyncSession, course: Course, user: User) -> bool:
    if user.role == "teacher":
        return course.teacher_id == user.id
    if user.role == "ta":
        return bool(await db.scalar(select(exists().where(
            CourseStaff.course_id == course.id,
            CourseStaff.user_id == user.id,
            CourseStaff.role == "ta",
        ))))
    return bool(await db.scalar(select(exists().where(
        Enrollment.course_id == course.id,
        Enrollment.student_id == user.id,
    ))))


async def _teacher_permission(db: AsyncSession, course_id: str, student_id: str) -> bool:
    permission = await db.scalar(select(MessagePermission).where(
        MessagePermission.course_id == course_id,
        MessagePermission.student_id == student_id,
    ))
    return permission.accepted if permission else True


async def _thread_for_user(db: AsyncSession, thread_id: str, current_user: User) -> DirectThread:
    thread = await db.scalar(select(DirectThread).where(DirectThread.id == thread_id))
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if current_user.id not in {thread.participant_a_id, thread.participant_b_id}:
        raise HTTPException(status_code=403, detail="Thread access denied")
    await _course_for_user(db, current_user, thread.course_id)
    return thread


async def _thread_dict(db: AsyncSession, thread: DirectThread, current_user: User) -> dict:
    other_id = thread.participant_b_id if thread.participant_a_id == current_user.id else thread.participant_a_id
    other = await db.scalar(select(User).where(User.id == other_id))
    course = await db.scalar(select(Course).where(Course.id == thread.course_id))
    last_message = await db.scalar(select(DirectMessage).where(
        DirectMessage.thread_id == thread.id,
    ).order_by(DirectMessage.created_at.desc()).limit(1))
    unread = await db.scalar(select(func.count(DirectMessage.id)).where(
        DirectMessage.thread_id == thread.id,
        DirectMessage.sender_id != current_user.id,
        DirectMessage.is_read.is_(False),
    ))
    return {
        "id": thread.id,
        "course_id": thread.course_id,
        "course_name": course.name if course else "",
        "other_user": _user_dict(other),
        "last_message": last_message.content if last_message else "",
        "last_message_at": _iso(last_message.created_at) if last_message else None,
        "unread_count": unread or 0,
        "updated_at": _iso(thread.updated_at),
    }


@router.get("/contacts")
async def list_contacts(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == "student":
        result = await db.execute(select(Course).join(Enrollment, Enrollment.course_id == Course.id).where(
            Enrollment.student_id == current_user.id,
        ).order_by(Course.name))
    elif current_user.role == "ta":
        result = await db.execute(select(Course).join(CourseStaff, CourseStaff.course_id == Course.id).where(
            CourseStaff.user_id == current_user.id, CourseStaff.role == "ta",
        ).order_by(Course.name))
    else:
        result = await db.execute(select(Course).where(Course.teacher_id == current_user.id).order_by(Course.name))

    contacts: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for course in result.scalars().unique().all():
        members: list[User] = []
        if current_user.role == "student":
            teacher = await db.scalar(select(User).where(User.id == course.teacher_id))
            if teacher:
                members.append(teacher)
            ta_result = await db.execute(select(User).join(CourseStaff, CourseStaff.user_id == User.id).where(
                CourseStaff.course_id == course.id, CourseStaff.role == "ta",
            ).order_by(User.display_name, User.student_id))
            members.extend(ta_result.scalars().all())
        elif current_user.role == "teacher":
            student_result = await db.execute(select(User).join(Enrollment, Enrollment.student_id == User.id).where(
                Enrollment.course_id == course.id, User.role == "student",
            ).order_by(User.display_name, User.student_id))
            members.extend(student_result.scalars().all())
            ta_result = await db.execute(select(User).join(CourseStaff, CourseStaff.user_id == User.id).where(
                CourseStaff.course_id == course.id, CourseStaff.role == "ta",
            ).order_by(User.display_name, User.student_id))
            members.extend(ta_result.scalars().all())
        else:
            teacher = await db.scalar(select(User).where(User.id == course.teacher_id))
            if teacher:
                members.append(teacher)
            student_result = await db.execute(select(User).join(Enrollment, Enrollment.student_id == User.id).where(
                Enrollment.course_id == course.id, User.role == "student",
            ).order_by(User.display_name, User.student_id))
            members.extend(student_result.scalars().all())

        for member in members:
            if member.id == current_user.id or (course.id, member.id) in seen:
                continue
            seen.add((course.id, member.id))
            accepted = True
            if current_user.role == "student" and member.role == "teacher":
                accepted = await _teacher_permission(db, course.id, current_user.id)
            contacts.append({
                "course_id": course.id,
                "course_name": course.name,
                "user": _user_dict(member),
                "can_message": accepted or current_user.role != "student" or member.role != "teacher",
                "accepted": accepted,
            })
    return {"contacts": contacts}


@router.get("/threads")
async def list_threads(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DirectThread).where(or_(
        DirectThread.participant_a_id == current_user.id,
        DirectThread.participant_b_id == current_user.id,
    )).order_by(DirectThread.updated_at.desc()))
    return {"threads": [await _thread_dict(db, thread, current_user) for thread in result.scalars().all()]}


@router.post("/threads")
async def create_thread(payload: ThreadCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    course = await _course_for_user(db, current_user, payload.course_id)
    recipient = await db.scalar(select(User).where(User.id == payload.recipient_id, User.is_active.is_(True)))
    if not recipient or recipient.id == current_user.id or not await _member_in_course(db, course, recipient):
        raise HTTPException(status_code=404, detail="Recipient is not in this course")
    if current_user.role == "student" and recipient.role == "teacher" and not await _teacher_permission(db, course.id, current_user.id):
        raise HTTPException(status_code=403, detail="Message permission denied")
    first, second = _canonical_participants(current_user.id, recipient.id)
    thread = await db.scalar(select(DirectThread).where(
        DirectThread.course_id == course.id,
        DirectThread.participant_a_id == first,
        DirectThread.participant_b_id == second,
    ))
    if not thread:
        thread = DirectThread(
            course_id=course.id,
            participant_a_id=first,
            participant_b_id=second,
        )
        db.add(thread)
        await db.flush()
    return await _thread_dict(db, thread, current_user)


@router.get("/threads/{thread_id}")
async def get_thread(thread_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    thread = await _thread_for_user(db, thread_id, current_user)
    message_result = await db.execute(select(DirectMessage, User).join(User, User.id == DirectMessage.sender_id).where(
        DirectMessage.thread_id == thread.id,
    ).order_by(DirectMessage.created_at, DirectMessage.id))
    messages = []
    for message, sender in message_result.all():
        if message.sender_id != current_user.id:
            message.is_read = True
        messages.append({
            "id": message.id,
            "content": message.content,
            "sender_id": message.sender_id,
            "sender": _user_dict(sender),
            "is_read": message.is_read,
            "created_at": _iso(message.created_at),
        })
    return {"thread": await _thread_dict(db, thread, current_user), "messages": messages}


@router.post("/threads/{thread_id}/messages")
async def send_message(thread_id: str, payload: MessageCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    thread = await _thread_for_user(db, thread_id, current_user)
    other_id = thread.participant_b_id if thread.participant_a_id == current_user.id else thread.participant_a_id
    other = await db.scalar(select(User).where(User.id == other_id))
    if not other:
        raise HTTPException(status_code=404, detail="Recipient not found")
    if current_user.role == "student" and other.role == "teacher" and not await _teacher_permission(db, thread.course_id, current_user.id):
        raise HTTPException(status_code=403, detail="Message permission denied")
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message cannot be empty")
    message = DirectMessage(thread_id=thread.id, sender_id=current_user.id, content=content)
    db.add(message)
    thread.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "id": message.id,
        "content": message.content,
        "sender_id": message.sender_id,
        "created_at": _iso(message.created_at),
    }


@router.get("/permissions")
async def list_permissions(
    course_id: str = Query(...),
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    course = await db.scalar(select(Course).where(Course.id == course_id, Course.teacher_id == current_user.id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    result = await db.execute(select(User).join(Enrollment, Enrollment.student_id == User.id).where(
        Enrollment.course_id == course_id, User.role == "student",
    ).order_by(User.display_name, User.student_id))
    permissions = []
    for student in result.scalars().all():
        permissions.append({
            "course_id": course_id,
            "student": _user_dict(student),
            "accepted": await _teacher_permission(db, course_id, student.id),
        })
    return {"permissions": permissions}


@router.patch("/permissions/{course_id}/{student_id}")
async def update_permission(
    course_id: str,
    student_id: str,
    payload: PermissionUpdate,
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    course = await db.scalar(select(Course).where(Course.id == course_id, Course.teacher_id == current_user.id))
    student = await db.scalar(select(User).where(User.id == student_id, User.role == "student"))
    enrolled = await db.scalar(select(exists().where(
        Enrollment.course_id == course_id, Enrollment.student_id == student_id,
    )))
    if not course or not student or not enrolled:
        raise HTTPException(status_code=404, detail="Course or student not found")
    permission = await db.scalar(select(MessagePermission).where(
        MessagePermission.course_id == course_id,
        MessagePermission.student_id == student_id,
    ))
    if not permission:
        permission = MessagePermission(
            course_id=course_id,
            student_id=student_id,
            teacher_id=current_user.id,
            accepted=payload.accepted,
        )
        db.add(permission)
    else:
        permission.accepted = payload.accepted
        permission.teacher_id = current_user.id
    await db.flush()
    return {
        "course_id": course_id,
        "student": _user_dict(student),
        "accepted": permission.accepted,
    }
