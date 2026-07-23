import mimetypes
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import RequireStudent, RequireTeacherOrTA, get_current_user
from app.models.academic import Announcement, Assignment, AttendanceRecord, AttendanceSession, Submission
from app.models.course import Course, CourseStaff, Enrollment
from app.models.user import User

settings = get_settings()
router = APIRouter(prefix="/api", tags=["academic"])


class AssignmentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=20000)
    due_at: Optional[datetime] = None
    max_score: int = Field(default=100, ge=1, le=1000)
    allow_late: bool = False
    allow_resubmit: bool = True


class AssignmentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    instructions: Optional[str] = Field(default=None, max_length=20000)
    due_at: Optional[datetime] = None
    max_score: Optional[int] = Field(default=None, ge=1, le=1000)
    allow_late: Optional[bool] = None
    allow_resubmit: Optional[bool] = None


class GradeRequest(BaseModel):
    score: int = Field(..., ge=0, le=1000)
    feedback: str = Field(default="", max_length=10000)


class AttendanceCreate(BaseModel):
    title: str = Field(default="Class attendance", min_length=1, max_length=200)
    starts_at: datetime
    ends_at: datetime
    code: Optional[str] = Field(default=None, min_length=4, max_length=12)


class CheckInRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=12)


class AttendanceUpdate(BaseModel):
    status: Literal["present", "late", "absent", "excused"]
    note: str = Field(default="", max_length=500)


class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(default="", max_length=20000)
    expires_at: Optional[datetime] = None


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def _course_for_user(db: AsyncSession, user: User, course_id: str) -> Course:
    course = await db.scalar(select(Course).where(Course.id == course_id))
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if user.role == "teacher":
        allowed = course.teacher_id == user.id
    elif user.role == "ta":
        allowed = bool(await db.scalar(select(exists().where(
            CourseStaff.course_id == course_id,
            CourseStaff.user_id == user.id,
            CourseStaff.role == "ta",
        ))))
    else:
        allowed = bool(await db.scalar(select(exists().where(
            Enrollment.course_id == course_id,
            Enrollment.student_id == user.id,
        ))))
    if not allowed:
        raise HTTPException(status_code=403, detail="Course access denied")
    return course


async def _assignment_for_user(db: AsyncSession, user: User, assignment_id: str) -> Assignment:
    assignment = await db.scalar(select(Assignment).where(Assignment.id == assignment_id))
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await _course_for_user(db, user, assignment.course_id)
    if user.role == "student" and assignment.status not in {"published", "closed"}:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


def _assignment_dict(assignment: Assignment, submission: Optional[Submission] = None, submission_count: int = 0) -> dict:
    return {
        "id": assignment.id,
        "course_id": assignment.course_id,
        "title": assignment.title,
        "instructions": assignment.instructions,
        "status": assignment.status,
        "due_at": _iso(assignment.due_at),
        "max_score": assignment.max_score,
        "allow_late": assignment.allow_late,
        "allow_resubmit": assignment.allow_resubmit,
        "created_at": _iso(assignment.created_at),
        "updated_at": _iso(assignment.updated_at),
        "submission_count": submission_count,
        "submission": _submission_dict(submission) if submission else None,
    }


def _submission_dict(submission: Optional[Submission]) -> Optional[dict]:
    if not submission:
        return None
    return {
        "id": submission.id,
        "assignment_id": submission.assignment_id,
        "student_id": submission.student_id,
        "answer_text": submission.answer_text,
        "file_name": submission.file_name,
        "status": submission.status,
        "score": submission.score,
        "feedback": submission.feedback,
        "submitted_at": _iso(submission.submitted_at),
        "updated_at": _iso(submission.updated_at),
        "graded_at": _iso(submission.graded_at),
    }


@router.get("/courses/{course_id}/assignments")
async def list_assignments(course_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _course_for_user(db, current_user, course_id)
    query = select(Assignment).where(Assignment.course_id == course_id)
    if current_user.role == "student":
        query = query.where(Assignment.status.in_(["published", "closed"]))
    result = await db.execute(query.order_by(Assignment.due_at.is_(None), Assignment.due_at, desc(Assignment.created_at)))
    assignments = result.scalars().all()
    output = []
    for assignment in assignments:
        submission = await db.scalar(select(Submission).where(
            Submission.assignment_id == assignment.id,
            Submission.student_id == current_user.id,
        )) if current_user.role == "student" else None
        count = await db.scalar(select(func.count(Submission.id)).where(Submission.assignment_id == assignment.id))
        output.append(_assignment_dict(assignment, submission, count or 0))
    return {"assignments": output}


@router.post("/courses/{course_id}/assignments")
async def create_assignment(course_id: str, payload: AssignmentCreate, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    await _course_for_user(db, current_user, course_id)
    if payload.due_at and payload.due_at.tzinfo is None:
        payload.due_at = payload.due_at.replace(tzinfo=timezone.utc)
    assignment = Assignment(
        id=str(uuid.uuid4()), course_id=course_id, creator_id=current_user.id,
        title=payload.title.strip(), instructions=payload.instructions.strip(), due_at=payload.due_at,
        max_score=payload.max_score, allow_late=payload.allow_late, allow_resubmit=payload.allow_resubmit,
    )
    db.add(assignment)
    await db.flush()
    return _assignment_dict(assignment)


@router.get("/assignments/{assignment_id}")
async def get_assignment(assignment_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    assignment = await _assignment_for_user(db, current_user, assignment_id)
    submission = await db.scalar(select(Submission).where(
        Submission.assignment_id == assignment.id,
        Submission.student_id == current_user.id,
    )) if current_user.role == "student" else None
    count = await db.scalar(select(func.count(Submission.id)).where(Submission.assignment_id == assignment.id))
    return _assignment_dict(assignment, submission, count or 0)


@router.patch("/assignments/{assignment_id}")
async def update_assignment(assignment_id: str, payload: AssignmentUpdate, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    assignment = await _assignment_for_user(db, current_user, assignment_id)
    for field in ("title", "instructions", "due_at", "max_score", "allow_late", "allow_resubmit"):
        value = getattr(payload, field)
        if value is not None:
            setattr(assignment, field, value.strip() if isinstance(value, str) else value)
    return _assignment_dict(assignment)


@router.post("/assignments/{assignment_id}/publish")
async def publish_assignment(assignment_id: str, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    assignment = await _assignment_for_user(db, current_user, assignment_id)
    assignment.status = "published"
    return {"message": "Assignment published", "assignment": _assignment_dict(assignment)}


@router.post("/assignments/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: str,
    answer_text: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    current_user: User = Depends(RequireStudent),
    db: AsyncSession = Depends(get_db),
):
    assignment = await _assignment_for_user(db, current_user, assignment_id)
    now = datetime.now(timezone.utc)
    if assignment.due_at and now > _utc(assignment.due_at) and not assignment.allow_late:
        raise HTTPException(status_code=400, detail="This assignment is past its deadline")
    existing = await db.scalar(select(Submission).where(
        Submission.assignment_id == assignment.id, Submission.student_id == current_user.id,
    ))
    if existing and not assignment.allow_resubmit:
        raise HTTPException(status_code=400, detail="Resubmission is disabled for this assignment")
    file_name = existing.file_name if existing else None
    file_path = existing.file_path if existing else None
    if file:
        safe_name = os.path.basename(file.filename or "submission")
        allowed = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".png", ".jpg", ".jpeg", ".zip"}
        extension = os.path.splitext(safe_name)[1].lower()
        if extension not in allowed:
            raise HTTPException(status_code=400, detail="Unsupported submission file type")
        data = await file.read(settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1)
        if len(data) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Submission file is too large")
        os.makedirs(os.path.join(settings.UPLOAD_DIR, "assignments"), exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}{extension}"
        file_path = os.path.join(settings.UPLOAD_DIR, "assignments", stored_name)
        async with aiofiles.open(file_path, "wb") as target:
            await target.write(data)
        file_name = safe_name[:255]
    submission_status = "late" if assignment.due_at and now > _utc(assignment.due_at) else "submitted"
    if existing:
        existing.answer_text = answer_text.strip()
        existing.file_name = file_name
        existing.file_path = file_path
        existing.status = submission_status
        existing.score = None
        existing.feedback = ""
        existing.graded_by = None
        existing.graded_at = None
        submission = existing
    else:
        submission = Submission(
            id=str(uuid.uuid4()), assignment_id=assignment.id, student_id=current_user.id,
            answer_text=answer_text.strip(), file_name=file_name, file_path=file_path, status=submission_status,
        )
        db.add(submission)
    await db.flush()
    return _submission_dict(submission)


@router.get("/assignments/{assignment_id}/submissions")
async def list_submissions(assignment_id: str, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    assignment = await _assignment_for_user(db, current_user, assignment_id)
    result = await db.execute(select(Submission, User).join(User, User.id == Submission.student_id).where(
        Submission.assignment_id == assignment.id
    ).order_by(desc(Submission.submitted_at)))
    return {"submissions": [
        {**(_submission_dict(submission) or {}), "student_name": user.display_name, "student_id_number": user.student_id}
        for submission, user in result.all()
    ]}


@router.get("/submissions/{submission_id}")
async def get_submission(submission_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    submission = await db.scalar(select(Submission).where(Submission.id == submission_id))
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    assignment = await _assignment_for_user(db, current_user, submission.assignment_id)
    if current_user.role == "student" and submission.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Submission access denied")
    return {"assignment": _assignment_dict(assignment), "submission": _submission_dict(submission)}


@router.get("/submissions/{submission_id}/file")
async def get_submission_file(
    submission_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return an uploaded assignment file after checking the course boundary."""
    submission = await db.scalar(select(Submission).where(Submission.id == submission_id))
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    await _assignment_for_user(db, current_user, submission.assignment_id)
    if current_user.role == "student" and submission.student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Submission access denied")
    if not submission.file_path:
        raise HTTPException(status_code=404, detail="Submission attachment not found")
    file_path = Path(submission.file_path).resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    if file_path != upload_root and upload_root not in file_path.parents:
        raise HTTPException(status_code=403, detail="Submission access denied")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Submission attachment not found")
    return FileResponse(
        file_path,
        filename=submission.file_name or "submission-file",
        media_type=mimetypes.guess_type(submission.file_name or "")[0] or "application/octet-stream",
    )


@router.post("/submissions/{submission_id}/grade")
async def grade_submission(submission_id: str, payload: GradeRequest, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    submission = await db.scalar(select(Submission).where(Submission.id == submission_id))
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    assignment = await _assignment_for_user(db, current_user, submission.assignment_id)
    if payload.score > assignment.max_score:
        raise HTTPException(status_code=400, detail="Score exceeds assignment maximum")
    submission.score = payload.score
    submission.feedback = payload.feedback.strip()
    submission.status = "graded"
    submission.graded_by = current_user.id
    submission.graded_at = datetime.now(timezone.utc)
    return _submission_dict(submission)


@router.post("/submissions/{submission_id}/return")
async def return_submission(submission_id: str, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    submission = await db.scalar(select(Submission).where(Submission.id == submission_id))
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    await _assignment_for_user(db, current_user, submission.assignment_id)
    submission.status = "returned"
    return _submission_dict(submission)


def _attendance_dict(session: AttendanceSession, record: Optional[AttendanceRecord] = None, present_count: int = 0) -> dict:
    return {
        "id": session.id, "course_id": session.course_id, "title": session.title, "code": session.code,
        "starts_at": _iso(session.starts_at), "ends_at": _iso(session.ends_at), "status": session.status,
        "created_at": _iso(session.created_at), "present_count": present_count,
        "my_record": {"id": record.id, "status": record.status, "checked_in_at": _iso(record.checked_in_at), "note": record.note} if record else None,
    }


@router.post("/courses/{course_id}/attendance/sessions")
async def create_attendance(course_id: str, payload: AttendanceCreate, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    await _course_for_user(db, current_user, course_id)
    if payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=400, detail="Attendance end time must be after start time")
    code = (payload.code or str(secrets.randbelow(900000) + 100000)).upper()
    session = AttendanceSession(
        id=str(uuid.uuid4()), course_id=course_id, creator_id=current_user.id, title=payload.title.strip(), code=code,
        starts_at=payload.starts_at, ends_at=payload.ends_at,
    )
    db.add(session)
    await db.flush()
    return _attendance_dict(session)


@router.get("/courses/{course_id}/attendance/sessions")
async def list_attendance(course_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _course_for_user(db, current_user, course_id)
    result = await db.execute(select(AttendanceSession).where(AttendanceSession.course_id == course_id).order_by(desc(AttendanceSession.starts_at)))
    sessions = result.scalars().all()
    output = []
    for session in sessions:
        record = await db.scalar(select(AttendanceRecord).where(
            AttendanceRecord.session_id == session.id, AttendanceRecord.student_id == current_user.id,
        )) if current_user.role == "student" else None
        count = await db.scalar(select(func.count(AttendanceRecord.id)).where(
            AttendanceRecord.session_id == session.id, AttendanceRecord.status.in_(["present", "late"]),
        ))
        output.append(_attendance_dict(session, record, count or 0))
    return {"sessions": output}


@router.post("/attendance/sessions/{session_id}/check-in")
async def check_in(session_id: str, payload: CheckInRequest, current_user: User = Depends(RequireStudent), db: AsyncSession = Depends(get_db)):
    session = await db.scalar(select(AttendanceSession).where(AttendanceSession.id == session_id))
    if not session:
        raise HTTPException(status_code=404, detail="Attendance session not found")
    await _course_for_user(db, current_user, session.course_id)
    if payload.code.strip().upper() != session.code.upper():
        raise HTTPException(status_code=400, detail="Invalid attendance code")
    now = datetime.now(timezone.utc)
    starts_at, ends_at = _utc(session.starts_at), _utc(session.ends_at)
    if session.status != "open" or now < starts_at or now > ends_at:
        raise HTTPException(status_code=400, detail="Attendance session is not open")
    record = await db.scalar(select(AttendanceRecord).where(
        AttendanceRecord.session_id == session.id, AttendanceRecord.student_id == current_user.id,
    ))
    attendance_status = "late" if now > starts_at else "present"
    if record:
        record.status, record.checked_in_at = attendance_status, now
    else:
        record = AttendanceRecord(
            id=str(uuid.uuid4()), session_id=session.id, student_id=current_user.id,
            status=attendance_status, checked_in_at=now,
        )
        db.add(record)
    return {"message": "Checked in successfully", "record": {"status": attendance_status, "checked_in_at": now.isoformat()}}


@router.get("/attendance/sessions/{session_id}/records")
async def attendance_records(session_id: str, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    session = await db.scalar(select(AttendanceSession).where(AttendanceSession.id == session_id))
    if not session:
        raise HTTPException(status_code=404, detail="Attendance session not found")
    await _course_for_user(db, current_user, session.course_id)
    result = await db.execute(select(Enrollment, User).join(User, User.id == Enrollment.student_id).where(
        Enrollment.course_id == session.course_id, User.role == "student"
    ).order_by(User.student_id))
    records = {record.student_id: record for record in (await db.scalars(select(AttendanceRecord).where(AttendanceRecord.session_id == session.id))).all()}
    return {"records": [
        {
            "student_id": user.id, "student_id_number": user.student_id, "student_name": user.display_name,
            "record_id": records[user.id].id if user.id in records else None,
            "status": records[user.id].status if user.id in records else "absent",
            "checked_in_at": _iso(records[user.id].checked_in_at) if user.id in records else None,
            "note": records[user.id].note if user.id in records else "",
        }
        for _, user in result.all()
    ]}


@router.post("/attendance/sessions/{session_id}/records/{student_id}")
async def upsert_attendance_record(
    session_id: str,
    student_id: str,
    payload: AttendanceUpdate,
    current_user: User = Depends(RequireTeacherOrTA),
    db: AsyncSession = Depends(get_db),
):
    session = await db.scalar(select(AttendanceSession).where(AttendanceSession.id == session_id))
    if not session:
        raise HTTPException(status_code=404, detail="Attendance session not found")
    await _course_for_user(db, current_user, session.course_id)
    enrolled = await db.scalar(select(exists().where(
        Enrollment.course_id == session.course_id,
        Enrollment.student_id == student_id,
    )))
    if not enrolled:
        raise HTTPException(status_code=404, detail="Student is not enrolled in this course")
    record = await db.scalar(select(AttendanceRecord).where(
        AttendanceRecord.session_id == session_id,
        AttendanceRecord.student_id == student_id,
    ))
    if not record:
        record = AttendanceRecord(id=str(uuid.uuid4()), session_id=session_id, student_id=student_id)
        db.add(record)
    record.status, record.note = payload.status, payload.note.strip()
    if payload.status in {"present", "late"} and not record.checked_in_at:
        record.checked_in_at = datetime.now(timezone.utc)
    return {"id": record.id, "status": record.status, "note": record.note, "checked_in_at": _iso(record.checked_in_at)}


@router.patch("/attendance/records/{record_id}")
async def update_attendance(record_id: str, payload: AttendanceUpdate, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    record = await db.scalar(select(AttendanceRecord).where(AttendanceRecord.id == record_id))
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    session = await db.scalar(select(AttendanceSession).where(AttendanceSession.id == record.session_id))
    await _course_for_user(db, current_user, session.course_id)
    record.status, record.note = payload.status, payload.note.strip()
    return {"id": record.id, "status": record.status, "note": record.note, "checked_in_at": _iso(record.checked_in_at)}


@router.get("/courses/{course_id}/announcements")
async def list_announcements(course_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _course_for_user(db, current_user, course_id)
    result = await db.execute(select(Announcement).where(Announcement.course_id == course_id).order_by(desc(Announcement.published_at), desc(Announcement.created_at)))
    return {"announcements": [
        {"id": item.id, "course_id": item.course_id, "title": item.title, "content": item.content,
         "published_at": _iso(item.published_at), "expires_at": _iso(item.expires_at), "created_at": _iso(item.created_at)}
        for item in result.scalars().all()
    ]}


@router.post("/courses/{course_id}/announcements")
async def create_announcement(course_id: str, payload: AnnouncementCreate, current_user: User = Depends(RequireTeacherOrTA), db: AsyncSession = Depends(get_db)):
    await _course_for_user(db, current_user, course_id)
    item = Announcement(
        id=str(uuid.uuid4()), course_id=course_id, author_id=current_user.id, title=payload.title.strip(),
        content=payload.content.strip(), published_at=datetime.now(timezone.utc), expires_at=payload.expires_at,
    )
    db.add(item)
    await db.flush()
    return {"id": item.id, "course_id": item.course_id, "title": item.title, "content": item.content, "published_at": _iso(item.published_at), "expires_at": _iso(item.expires_at)}
