"""Student-directory pagination, course boundaries and actual provider usage."""

import asyncio
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai import deepseek_client
from app.core.database import Base
from app.models.base import Conversation, Course, Enrollment, Message, User
from app.routers import teacher
from app.services import chat_service


def user(uid, role="student"):
    return User(id=uid, student_id=uid, phone=uid, password_hash="unused", role=role)


def test_directory_paginates_all_156_students_and_filters_without_course_leaks():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                owner, other = user("T1", "teacher"), user("T2", "teacher")
                students = [user(f"S{i:03}") for i in range(156)]
                db.add_all([owner, other, *students, user("outside"), user("unassigned")])
                await db.flush()
                db.add_all([
                    Course(id="mine", name="My course", teacher_id=owner.id),
                    Course(id="mine2", name="Second course", teacher_id=owner.id),
                    Course(id="other", name="Private course", teacher_id=other.id),
                ])
                await db.flush()
                db.add_all([Enrollment(course_id="mine", student_id=s.id) for s in students])
                db.add_all([
                    Enrollment(course_id="mine2", student_id=students[0].id),
                    Enrollment(course_id="other", student_id=students[0].id),
                    Enrollment(course_id="other", student_id="outside"),
                ])
                await db.flush()
                seen = []
                for page in range(1, 5):
                    result = await teacher.list_students("", page, 50, owner, db)
                    assert result["total"] == 156
                    assert len(result["students"]) == (50 if page < 4 else 6)
                    for student in result["students"]:
                        assert all(c["id"] != "other" for c in student["courses"])
                        assert "password_hash" not in student
                        seen.append(student["id"])
                assert seen == [s.id for s in students]
                filtered = await teacher.list_students("", 1, 50, owner, db, "mine2")
                assert filtered["total"] == 1
                assert filtered["students"][0]["id"] == "S000"
                hidden = await teacher.list_students("", 1, 50, owner, db, "other")
                assert hidden["total"] == 0 and hidden["students"] == []
                search = await teacher.list_students("S155", 1, 50, owner, db)
                assert search["total"] == 1 and search["students"][0]["id"] == "S155"
        finally:
            await engine.dispose()
    asyncio.run(scenario())


def test_usage_totals_models_timestamps_and_messages_stay_course_scoped():
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                owner, other, student = user("T1", "teacher"), user("T2", "teacher"), user("S1")
                db.add_all([owner, other, student, user("outside")])
                await db.flush()
                db.add_all([Course(id="mine", name="Mine", teacher_id=owner.id), Course(id="other", name="Other", teacher_id=other.id)])
                await db.flush()
                db.add_all([
                    Enrollment(course_id="mine", student_id=student.id),
                    Enrollment(course_id="other", student_id=student.id),
                    Conversation(id="chat", user_id=student.id, course_id="mine"),
                    Conversation(id="empty", user_id=student.id, course_id="mine"),
                    Conversation(id="private", user_id=student.id, course_id="other"),
                    Conversation(id="general", user_id=student.id),
                ])
                await db.flush()
                start = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
                rows = [
                    Message(id="m0", conversation_id="chat", role="user", content="Question", created_at=start),
                    Message(id="m1", conversation_id="chat", role="assistant", content="Answer", model_name="deepseek-chat", prompt_tokens=120, completion_tokens=30, token_count=150, response_time_ms=1250, created_at=start + timedelta(seconds=1)),
                    Message(id="m2", conversation_id="chat", role="assistant", content="Historical answer", created_at=start + timedelta(seconds=2)),
                    Message(id="m3", conversation_id="chat", role="assistant", content="Reasoned answer", model_name="deepseek-reasoner", prompt_tokens=200, completion_tokens=50, token_count=250, response_time_ms=2500, created_at=start + timedelta(seconds=3)),
                    Message(id="m4", conversation_id="private", role="assistant", content="Other course", token_count=99999, model_name="hidden"),
                    Message(id="m5", conversation_id="general", role="assistant", content="Private chat", token_count=99999, model_name="hidden"),
                ]
                db.add_all(rows)
                await db.flush()
                usage = await teacher.get_student_usage(student.id, owner, db)
                assert usage["total_chat_messages"] == 4
                assert usage["total_conversations"] == 2
                assert usage["total_ai_responses"] == 3
                assert (usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"]) == (320, 80, 400)
                assert usage["recorded_usage_count"] == usage["recorded_prompt_count"] == usage["recorded_completion_count"] == 2
                assert usage["missing_usage_count"] == 1
                assert usage["first_active_at"].startswith("2026-01-01T10:00:00")
                assert usage["last_active_at"].startswith("2026-01-01T10:00:03")
                models = {row["model_name"]: row for row in usage["models"]}
                assert set(models) == {None, "deepseek-chat", "deepseek-reasoner"}
                assert models[None]["total_tokens"] is None
                assert models["deepseek-chat"]["total_tokens"] == 150
                chats = await teacher.get_student_conversations(student.id, 1, 20, owner, db)
                by_id = {c["id"]: c for c in chats["conversations"]}
                assert by_id["chat"]["message_count"] == 4
                assert by_id["chat"]["total_tokens"] == 400
                assert by_id["empty"]["recorded_usage_count"] == 0
                messages = await teacher.get_student_messages(student.id, "chat", 1, 2, owner, db)
                assert messages["total"] == 4
                answer = messages["messages"][1]
                assert (answer["model_name"], answer["token_count"], answer["response_time_ms"]) == ("deepseek-chat", 150, 1250)
                next_page = await teacher.get_student_messages(student.id, "chat", 2, 2, owner, db)
                assert [m["id"] for m in next_page["messages"]] == ["m2", "m3"]
                assert next_page["messages"][0]["token_count"] is None
                with pytest.raises(HTTPException) as exc:
                    await teacher.get_student_usage("outside", owner, db)
                assert exc.value.status_code == 403
                for cid in ("private", "general"):
                    with pytest.raises(HTTPException) as exc:
                        await teacher.get_student_messages(student.id, cid, 1, 50, owner, db)
                    assert exc.value.status_code == 404
        finally:
            await engine.dispose()
    asyncio.run(scenario())


@pytest.mark.parametrize("with_usage", [True, False])
def test_provider_returns_reported_usage_without_inventing_missing_counts(monkeypatch, with_usage):
    reported = SimpleNamespace(prompt_tokens=80, completion_tokens=20, total_tokens=100) if with_usage else None
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Answer"))], model="deepseek-chat-reported", usage=reported)
    monkeypatch.setattr(deepseek_client.settings, "DEEPSEEK_API_KEY", "test-only")
    monkeypatch.setattr(deepseek_client.client.chat.completions, "create", lambda **kwargs: response)
    result = asyncio.run(deepseek_client.get_deepseek_response("Explain a concept"))
    assert result["model_name"] == "deepseek-chat-reported"
    assert result["usage"]["total_tokens"] == (100 if with_usage else None)


def test_chat_persists_provider_usage_and_elapsed_time(monkeypatch):
    async def fake_response(**kwargs):
        return {"response": "Answer", "model_name": "test-model", "usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}}
    async def empty_history(*args, **kwargs):
        return []
    async def no_cache(*args, **kwargs):
        pass
    monkeypatch.setattr(chat_service, "get_deepseek_response", fake_response)
    monkeypatch.setattr(chat_service.conversation_memory, "get_history", empty_history)
    monkeypatch.setattr(chat_service.conversation_memory, "add_message", no_cache)
    times = iter([10.0, 11.25])
    monkeypatch.setattr(chat_service, "perf_counter", lambda: next(times))

    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                db.add(user("S1"))
                await db.flush()
                result = await chat_service.process_chat(db, "S1", "Question")
                message = await db.scalar(select(Message).where(Message.id == result["message_id"]))
                assert (message.prompt_tokens, message.completion_tokens, message.token_count) == (80, 20, 100)
                assert message.model_name == "test-model"
                assert message.response_time_ms == 1250
        finally:
            await engine.dispose()
    asyncio.run(scenario())


def test_usage_migration_preserves_historical_messages():
    path = Path(__file__).parents[1] / "alembic/versions/0007_message_usage_details.py"
    spec = spec_from_file_location("usage_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE messages (id VARCHAR(36) PRIMARY KEY, content TEXT, token_count INTEGER)"))
            connection.execute(text("INSERT INTO messages (id, content) VALUES ('old', 'Historical answer')"))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.upgrade()  # Also safe after a local schema compatibility update.
            assert {"prompt_tokens", "completion_tokens", "model_name", "response_time_ms"} <= {c["name"] for c in inspect(connection).get_columns("messages")}
            row = connection.execute(text("SELECT content, prompt_tokens, model_name FROM messages WHERE id='old'")).one()
            assert tuple(row) == ("Historical answer", None, None)
    finally:
        engine.dispose()
