import json
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect, text
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

AsyncSessionFactory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    # Import all models so they register with Base.metadata before create_all
    from app.models.base import (  # noqa: F401
        User, Course, Enrollment, CourseStaff, CourseChapter, CourseMaterial, Conversation, Message, RobotStatus, RobotQuestion, UsageLog,
        FileAsset,
        AuditLog, RefreshToken, Assignment, Submission, AttendanceSession, AttendanceRecord, Announcement,
        MessagePermission, DirectThread, DirectMessage,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_legacy_columns)
        await conn.run_sync(_migrate_legacy_course_chapters)


def _ensure_legacy_columns(sync_conn):
    """Add nullable/defaulted fields to installations created before migrations."""
    inspector = inspect(sync_conn)
    additions = {
        "users": {"last_login_at": "DATETIME"},
        "conversations": {"chapter_id": "VARCHAR(36)"},
        "file_assets": {
            "stored_path": "VARCHAR(500)",
            "extracted_text": "TEXT DEFAULT ''",
            "page_count": "INTEGER",
            "is_active": "BOOLEAN DEFAULT TRUE",
        },
        "usage_logs": {"course_id": "VARCHAR(36)"},
        "robot_status": {"robot_id": "VARCHAR(100)", "last_heartbeat_at": "DATETIME"},
        "robot_questions": {
            "asr_text": "TEXT",
            "mode": "VARCHAR(20) DEFAULT 'voice'",
            "processing_status": "VARCHAR(20) DEFAULT 'completed'",
        },
    }
    for table, columns in additions.items():
        if table not in inspector.get_table_names():
            continue
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column, definition in columns.items():
            if column not in existing:
                sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


def _migrate_legacy_course_chapters(sync_conn):
    inspector = inspect(sync_conn)
    if not {"courses", "course_chapters"}.issubset(set(inspector.get_table_names())):
        return
    rows = sync_conn.execute(text("SELECT id, chapters_json FROM courses")).mappings().all()
    for row in rows:
        try:
            titles = json.loads(row["chapters_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            titles = []
        titles = [title.strip() for title in titles if isinstance(title, str) and title.strip()]
        if not titles:
            continue
        count = sync_conn.execute(text(
            "SELECT COUNT(*) FROM course_chapters WHERE course_id = :course_id"
        ), {"course_id": row["id"]}).scalar_one()
        if not count:
            for index, title in enumerate(titles):
                sync_conn.execute(text(
                    "INSERT INTO course_chapters (id, course_id, title, description, sort_order) "
                    "VALUES (:id, :course_id, :title, '', :sort_order)"
                ), {"id": str(uuid.uuid4()), "course_id": row["id"], "title": title, "sort_order": index})
        sync_conn.execute(text("UPDATE courses SET chapters_json = '[]' WHERE id = :course_id"), {"course_id": row["id"]})


async def close_db():
    await engine.dispose()
