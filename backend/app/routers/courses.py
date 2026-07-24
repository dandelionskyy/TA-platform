import json
import mimetypes
import os
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import RequireTeacher, RequireTeacherOrTA, get_current_user
from app.models.course import Course, CourseChapter, CourseMaterial, CourseStaff, Enrollment
from app.models.user import User
from app.services.material_service import extract_material_text

settings = get_settings()
router = APIRouter(prefix="/api/courses", tags=["courses"])
teacher_router = APIRouter(prefix="/api/teacher", tags=["teacher-courses"])


class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    knowledge_base_path: str = Field(default="", max_length=500)
    chapters: list[str] = Field(default_factory=list, max_length=100)


class ChapterCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)


class ChapterUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class MemberRequest(BaseModel):
    user_id: str


class BulkEnrollmentRequest(BaseModel):
    student_ids: list[str] = Field(..., min_length=1, max_length=200)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _material_dict(material: CourseMaterial) -> dict:
    extension = Path(material.filename).suffix.lower()
    if extension == ".pdf":
        preview_kind = "pdf"
    elif extension in {".png", ".jpg", ".jpeg", ".webp"}:
        preview_kind = "image"
    elif extension in {".txt", ".md"}:
        preview_kind = "text"
    elif extension in {".pptx", ".docx"}:
        preview_kind = "office"
    else:
        preview_kind = "download"
    return {
        "id": material.id,
        "course_id": material.course_id,
        "chapter_id": material.chapter_id,
        "filename": material.filename,
        "mime_type": material.mime_type,
        "size_bytes": material.size_bytes,
        "processing_status": material.processing_status,
        "preview_kind": preview_kind,
        "created_at": _iso(material.created_at),
    }


async def _chapter_dict(db: AsyncSession, chapter: CourseChapter) -> dict:
    result = await db.execute(select(CourseMaterial).where(
        CourseMaterial.chapter_id == chapter.id,
    ).order_by(CourseMaterial.created_at, CourseMaterial.filename))
    return {
        "id": chapter.id,
        "course_id": chapter.course_id,
        "title": chapter.title,
        "description": chapter.description,
        "sort_order": chapter.sort_order,
        "created_at": _iso(chapter.created_at),
        "materials": [_material_dict(material) for material in result.scalars().all()],
    }


async def serialize_course(db: AsyncSession, course: Course) -> dict:
    chapter_result = await db.execute(select(CourseChapter).where(
        CourseChapter.course_id == course.id,
    ).order_by(CourseChapter.sort_order, CourseChapter.created_at))
    chapters = [await _chapter_dict(db, chapter) for chapter in chapter_result.scalars().all()]
    if not chapters:
        try:
            legacy = json.loads(course.chapters_json or "[]")
        except json.JSONDecodeError:
            legacy = []
        chapters = [{
            "id": f"legacy-{index}", "course_id": course.id, "title": title,
            "description": "", "sort_order": index, "materials": [], "legacy": True,
        } for index, title in enumerate(legacy) if isinstance(title, str)]
    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "teacher_id": course.teacher_id,
        "knowledge_base_path": course.knowledge_base_path,
        "chapters": chapters,
        "created_at": _iso(course.created_at),
    }


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


async def _staff_course(db: AsyncSession, user: User, course_id: str) -> Course:
    if user.role not in {"teacher", "ta"}:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return await _course_for_user(db, user, course_id)


async def _chapter_for_user(db: AsyncSession, user: User, chapter_id: str, staff_only: bool = False) -> CourseChapter:
    chapter = await db.scalar(select(CourseChapter).where(CourseChapter.id == chapter_id))
    if not chapter:
        raise HTTPException(status_code=404, detail="Course chapter not found")
    if staff_only:
        await _staff_course(db, user, chapter.course_id)
    else:
        await _course_for_user(db, user, chapter.course_id)
    return chapter


@router.get("")
async def list_courses(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
    return {"courses": [await serialize_course(db, course) for course in result.scalars().unique().all()]}


@router.post("/{course_id}/chapters")
async def create_chapter(
    course_id: str,
    payload: ChapterCreate,
    current_user: User = Depends(RequireTeacherOrTA),
    db: AsyncSession = Depends(get_db),
):
    await _staff_course(db, current_user, course_id)
    max_order = await db.scalar(select(func.max(CourseChapter.sort_order)).where(CourseChapter.course_id == course_id))
    chapter = CourseChapter(
        course_id=course_id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        sort_order=(max_order if max_order is not None else -1) + 1,
        created_by=current_user.id,
    )
    db.add(chapter)
    await db.flush()
    return await _chapter_dict(db, chapter)


@router.patch("/chapters/{chapter_id}")
async def update_chapter(
    chapter_id: str,
    payload: ChapterUpdate,
    current_user: User = Depends(RequireTeacherOrTA),
    db: AsyncSession = Depends(get_db),
):
    chapter = await _chapter_for_user(db, current_user, chapter_id, staff_only=True)
    if payload.title is not None:
        chapter.title = payload.title.strip()
    if payload.description is not None:
        chapter.description = payload.description.strip()
    if payload.sort_order is not None:
        chapter.sort_order = payload.sort_order
    await db.flush()
    return await _chapter_dict(db, chapter)


@router.delete("/chapters/{chapter_id}")
async def delete_chapter(
    chapter_id: str,
    current_user: User = Depends(RequireTeacherOrTA),
    db: AsyncSession = Depends(get_db),
):
    chapter = await _chapter_for_user(db, current_user, chapter_id, staff_only=True)
    material_result = await db.execute(select(CourseMaterial).where(CourseMaterial.chapter_id == chapter.id))
    for material in material_result.scalars().all():
        path = Path(material.stored_path).resolve()
        upload_root = Path(settings.UPLOAD_DIR).resolve()
        if path.is_file() and upload_root in path.parents:
            path.unlink(missing_ok=True)
        await db.delete(material)
    await db.delete(chapter)
    return {"message": "Course chapter deleted"}


@router.post("/chapters/{chapter_id}/materials")
async def upload_material(
    chapter_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(RequireTeacherOrTA),
    db: AsyncSession = Depends(get_db),
):
    chapter = await _chapter_for_user(db, current_user, chapter_id, staff_only=True)
    safe_name = os.path.basename(file.filename or "course-material")[:255]
    extension = Path(safe_name).suffix.lower()
    allowed = {".pdf", ".pptx", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}
    if extension not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported course material type")
    data = await file.read(settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 + 1)
    if len(data) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Course material is too large")
    directory = Path(settings.UPLOAD_DIR) / "course_materials" / chapter.course_id / chapter.id
    directory.mkdir(parents=True, exist_ok=True)
    stored_path = directory / f"{uuid.uuid4().hex}{extension}"
    async with aiofiles.open(stored_path, "wb") as target:
        await target.write(data)
    extracted_text, processing_status = extract_material_text(data, extension)
    material = CourseMaterial(
        course_id=chapter.course_id,
        chapter_id=chapter.id,
        uploader_id=current_user.id,
        filename=safe_name,
        stored_path=str(stored_path),
        mime_type=file.content_type or mimetypes.guess_type(safe_name)[0],
        size_bytes=len(data),
        extracted_text=extracted_text,
        processing_status=processing_status,
    )
    db.add(material)
    await db.flush()
    return _material_dict(material)


@router.get("/materials/{material_id}/file")
async def get_material_file(
    material_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    material = await db.scalar(select(CourseMaterial).where(CourseMaterial.id == material_id))
    if not material:
        raise HTTPException(status_code=404, detail="Course material not found")
    await _course_for_user(db, current_user, material.course_id)
    path = Path(material.stored_path).resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    if upload_root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Course material file not found")
    return FileResponse(
        path,
        filename=material.filename,
        media_type=material.mime_type or mimetypes.guess_type(material.filename)[0] or "application/octet-stream",
    )


@router.delete("/materials/{material_id}")
async def delete_material(
    material_id: str,
    current_user: User = Depends(RequireTeacherOrTA),
    db: AsyncSession = Depends(get_db),
):
    material = await db.scalar(select(CourseMaterial).where(CourseMaterial.id == material_id))
    if not material:
        raise HTTPException(status_code=404, detail="Course material not found")
    await _staff_course(db, current_user, material.course_id)
    path = Path(material.stored_path).resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    if path.is_file() and upload_root in path.parents:
        path.unlink(missing_ok=True)
    await db.delete(material)
    return {"message": "Course material deleted"}


@teacher_router.get("/courses")
async def teacher_courses(current_user: User = Depends(RequireTeacher), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Course).where(Course.teacher_id == current_user.id).order_by(Course.name))
    return {"courses": [await serialize_course(db, course) for course in result.scalars().all()]}


@teacher_router.post("/courses")
async def create_course(
    payload: CourseCreate,
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    course = Course(
        id=str(uuid.uuid4()),
        name=payload.name.strip(),
        description=payload.description.strip(),
        teacher_id=current_user.id,
        knowledge_base_path=payload.knowledge_base_path.strip(),
        chapters_json="[]",
    )
    db.add(course)
    await db.flush()
    for index, title in enumerate(payload.chapters):
        if title.strip():
            db.add(CourseChapter(course_id=course.id, title=title.strip(), sort_order=index, created_by=current_user.id))
    await db.flush()
    return await serialize_course(db, course)


@teacher_router.post("/courses/{course_id}/students/bulk")
async def enroll_students_bulk(
    course_id: str,
    payload: BulkEnrollmentRequest,
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    owns = await db.scalar(select(exists().where(Course.id == course_id, Course.teacher_id == current_user.id)))
    if not owns:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Course access denied")

    requested_ids = list(dict.fromkeys(payload.student_ids))
    student_result = await db.execute(select(User).where(
        User.id.in_(requested_ids), User.role == "student", User.is_active.is_(True),
    ))
    students = student_result.scalars().all()
    valid_ids = {student.id for student in students}

    existing_result = await db.execute(select(Enrollment.student_id).where(
        Enrollment.course_id == course_id, Enrollment.student_id.in_(valid_ids or {""}),
    ))
    existing_ids = set(existing_result.scalars().all())
    added_ids = []
    for student in students:
        if student.id not in existing_ids:
            db.add(Enrollment(course_id=course_id, student_id=student.id))
            added_ids.append(student.id)

    return {
        "message": "Students enrolled",
        "added_count": len(added_ids),
        "skipped_count": len(requested_ids) - len(added_ids),
        "student_ids": added_ids,
    }


@teacher_router.get("/courses/{course_id}/available-students")
async def available_course_students(
    course_id: str,
    search: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    owns = await db.scalar(select(exists().where(Course.id == course_id, Course.teacher_id == current_user.id)))
    if not owns:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Course access denied")

    enrolled_ids = select(Enrollment.student_id).where(Enrollment.course_id == course_id)
    query = select(User).where(
        User.role == "student",
        User.is_active.is_(True),
        ~User.id.in_(enrolled_ids),
    )
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            (User.student_id.ilike(term))
            | (User.display_name.ilike(term))
            | (User.phone.ilike(term))
        )

    count = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar() or 0
    result = await db.execute(query.order_by(User.student_id).offset((page - 1) * page_size).limit(page_size))
    return {
        "students": [student.to_dict() for student in result.scalars().all()],
        "total": count,
        "page": page,
        "page_size": page_size,
    }


@teacher_router.post("/courses/{course_id}/students/{student_id}")
async def enroll_student(
    course_id: str,
    student_id: str,
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    owns = await db.scalar(select(exists().where(Course.id == course_id, Course.teacher_id == current_user.id)))
    student = await db.scalar(select(User).where(User.id == student_id, User.role == "student"))
    if not owns or not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course or student not found")
    existing = await db.scalar(select(Enrollment).where(
        Enrollment.course_id == course_id, Enrollment.student_id == student_id,
    ))
    if not existing:
        db.add(Enrollment(course_id=course_id, student_id=student_id))
    return {"message": "Student enrolled"}


@teacher_router.post("/courses/{course_id}/tas")
async def assign_ta(
    course_id: str,
    payload: MemberRequest,
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    owns = await db.scalar(select(exists().where(Course.id == course_id, Course.teacher_id == current_user.id)))
    ta = await db.scalar(select(User).where(User.id == payload.user_id, User.role == "ta"))
    if not owns or not ta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course or TA not found")
    existing = await db.scalar(select(CourseStaff).where(
        CourseStaff.course_id == course_id, CourseStaff.user_id == ta.id,
    ))
    if not existing:
        db.add(CourseStaff(course_id=course_id, user_id=ta.id, role="ta"))
    return {"message": "TA assigned"}


@teacher_router.get("/courses/{course_id}/students")
async def course_students(
    course_id: str,
    current_user: User = Depends(RequireTeacher),
    db: AsyncSession = Depends(get_db),
):
    owns = await db.scalar(select(exists().where(Course.id == course_id, Course.teacher_id == current_user.id)))
    if not owns:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Course access denied")
    result = await db.execute(select(User).join(Enrollment, Enrollment.student_id == User.id).where(
        Enrollment.course_id == course_id, User.role == "student",
    ).order_by(User.student_id))
    return {"students": [student.to_dict() for student in result.scalars().all()]}
