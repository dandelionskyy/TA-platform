"""Regression checks for legacy course isolation and registration verification."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.base import Course, CourseStaff, Enrollment, User, Conversation, Message
from app.routers import auth, ta, teacher
from app.schemas.auth import SendSmsRequest
from app.services.chat_service import get_or_create_conversation
from app.services import sms_service


def test_teacher_and_ta_cannot_read_activity_from_another_course():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as db:
                t1 = User(id="teacher-1", student_id="T1", phone="10000000001", password_hash="x", role="teacher")
                t2 = User(id="teacher-2", student_id="T2", phone="10000000002", password_hash="x", role="teacher")
                assistant = User(id="ta-1", student_id="TA1", phone="10000000003", password_hash="x", role="ta")
                student = User(id="student-1", student_id="S1", phone="10000000004", password_hash="x", role="student")
                db.add_all([t1, t2, assistant, student])
                await db.flush()
                db.add_all([
                    Course(id="course-1", name="Mine", teacher_id=t1.id),
                    Course(id="course-2", name="Other", teacher_id=t2.id),
                ])
                await db.flush()
                db.add_all([
                    Enrollment(course_id="course-1", student_id=student.id),
                    Enrollment(course_id="course-2", student_id=student.id),
                    CourseStaff(course_id="course-1", user_id=assistant.id, role="ta"),
                    Conversation(id="chat-1", user_id=student.id, course_id="course-1"),
                    Conversation(id="chat-2", user_id=student.id, course_id="course-2"),
                    Conversation(id="chat-general", user_id=student.id, course_id=None),
                ])
                await db.flush()
                db.add_all([
                    Message(conversation_id="chat-1", role="user", content="Mine"),
                    Message(conversation_id="chat-2", role="user", content="Private course"),
                    Message(conversation_id="chat-general", role="user", content="General chat"),
                ])
                await db.flush()

                chats = await teacher.get_student_conversations(student.id, 1, 20, t1, db)
                assert chats["total"] == 1
                assert [row["id"] for row in chats["conversations"]] == ["chat-1"]
                with pytest.raises(HTTPException) as exc:
                    await teacher.get_student_messages(student.id, "chat-2", 1, 20, t1, db)
                assert exc.value.status_code == 404
                own = await teacher.get_student_messages(student.id, "chat-1", 1, 20, t1, db)
                assert [row["content"] for row in own["messages"]] == ["Mine"]

                t1_usage = await teacher.get_student_usage(student.id, t1, db)
                ta_usage = await ta.get_student_usage(student.id, assistant, db)
                assert t1_usage["total_chat_messages"] == ta_usage["total_chat_messages"] == 1
                assert t1_usage["total_conversations"] == ta_usage["total_conversations"] == 1
                assert t1_usage["total_login_count"] is None
                ta_rows = await ta.list_student_usage(assistant, db)
                assert ta_rows["students"][0]["total_chat_messages"] == 1
                teacher_summary = await teacher.teacher_dashboard(t1, db)
                ta_summary = await ta.ta_dashboard(assistant, db)
                assert teacher_summary["total_conversations"] == 1
                assert teacher_summary["total_students"] == 1
                assert ta_summary["total_conversations"] == 1
                assert ta_summary["total_messages"] == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_on_page_registration_code_is_retired():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.create_registration_code())
    assert exc.value.status_code == 410


def test_sms_endpoint_fails_closed_without_delivery(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(
        ALIBABA_SMS_ACCESS_KEY="", ALIBABA_SMS_SECRET="",
        ALIBABA_SMS_SIGN_NAME="", ALIBABA_SMS_TEMPLATE_CODE="",
    ))

    async def must_not_send(_phone):
        raise AssertionError("SMS fallback would disclose an OTP in server logs")

    monkeypatch.setattr(auth, "send_sms", must_not_send)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth.send_sms_code(SendSmsRequest(phone="13900009999")))
    assert exc.value.status_code == 503


def test_sms_service_never_logs_or_issues_code_without_delivery(monkeypatch, capsys):
    monkeypatch.setattr(sms_service, "settings", SimpleNamespace(
        ALIBABA_SMS_ACCESS_KEY="", ALIBABA_SMS_SECRET="",
        ALIBABA_SMS_SIGN_NAME="", ALIBABA_SMS_TEMPLATE_CODE="",
    ))

    async def must_not_issue(_phone):
        raise AssertionError("A code was generated without a delivery service")

    monkeypatch.setattr(sms_service, "issue_registration_code", must_not_issue)
    assert asyncio.run(sms_service.send_sms("13900009999")) is False
    assert capsys.readouterr().out == ""


def test_sms_response_does_not_echo_code(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: SimpleNamespace(
        ALIBABA_SMS_ACCESS_KEY="configured", ALIBABA_SMS_SECRET="configured",
        ALIBABA_SMS_SIGN_NAME="configured", ALIBABA_SMS_TEMPLATE_CODE="configured",
    ))

    async def successful_send(_phone):
        return True

    monkeypatch.setattr(auth, "send_sms", successful_send)
    response = asyncio.run(auth.send_sms_code(SendSmsRequest(phone="13900009999")))
    assert response == {"message": "SMS code sent", "phone": "13900009999"}


def test_private_chat_is_not_relabelled_as_course_chat():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as db:
                db.add(User(id="student-private", student_id="S2", phone="10000000005", password_hash="x", role="student"))
                await db.flush()
                old = Conversation(id="private-conv", user_id="student-private", course_id=None)
                db.add(old)
                await db.flush()
                db.add(Message(conversation_id=old.id, role="user", content="Earlier private question"))
                await db.flush()
                new = await get_or_create_conversation(db, "student-private", old.id, course_id="course-1")
                assert new.id != old.id
                assert new.course_id == "course-1"
                assert old.course_id is None
        finally:
            await engine.dispose()

    asyncio.run(scenario())
