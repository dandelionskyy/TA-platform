"""Isolated end-to-end smoke test for assignments and course messaging.

Run manually with: python tests/smoke_academic_messaging.py
"""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def expect(response: httpx.Response, status_code: int) -> dict:
    if response.status_code != status_code:
        raise AssertionError(f"Expected {status_code}, got {response.status_code}: {response.text}")
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    return {}


async def run() -> None:
    with tempfile.TemporaryDirectory(prefix="ta-platform-smoke-") as temp_dir:
        root = Path(temp_dir)
        os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(root / 'smoke.db').as_posix()}"
        os.environ["UPLOAD_DIR"] = str(root / "uploads")
        os.environ["SEED_DEMO_DATA"] = "true"
        os.environ["USE_REDIS"] = "false"

        from app.main import app

        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                async def login(account: str) -> tuple[dict, dict[str, str]]:
                    data = expect(await client.post("/api/auth/login", json={"login": account, "password": "123456"}), 200)
                    return data["user"], {"Authorization": f"Bearer {data['tokens']['access_token']}"}

                teacher, teacher_headers = await login("T00001")
                ta, ta_headers = await login("TA0001")
                student, student_headers = await login("20240001")

                course = expect(await client.post("/api/teacher/courses", headers=teacher_headers, json={"name": "Smoke Course"}), 200)
                expect(await client.post(f"/api/teacher/courses/{course['id']}/students/{student['id']}", headers=teacher_headers), 200)
                expect(await client.post(f"/api/teacher/courses/{course['id']}/tas", headers=teacher_headers, json={"user_id": ta["id"]}), 200)

                outsider = expect(await client.post("/api/auth/provision", headers=teacher_headers, json={
                    "student_id": "TA-SMOKE-2", "phone": "13900009999", "password": "123456", "display_name": "Outside TA", "role": "ta",
                }), 200)
                _, outsider_headers = await login(outsider["student_id"])

                chapter = expect(await client.post(f"/api/courses/{course['id']}/chapters", headers=ta_headers, json={
                    "title": "Chapter One", "description": "Managed course content",
                }), 200)
                material = expect(await client.post(
                    f"/api/courses/chapters/{chapter['id']}/materials",
                    headers=ta_headers,
                    files={"file": ("lesson.txt", b"COURSE-CONTEXT-UNIQUE: Kirchhoff current law.", "text/plain")},
                ), 200)
                student_courses = expect(await client.get("/api/courses", headers=student_headers), 200)["courses"]
                student_chapter = student_courses[0]["chapters"][0]
                if student_chapter["id"] != chapter["id"] or student_chapter["materials"][0]["id"] != material["id"]:
                    raise AssertionError("Student course directory did not include the uploaded chapter material")
                material_file = await client.get(f"/api/courses/materials/{material['id']}/file", headers=student_headers)
                if material_file.status_code != 200 or b"COURSE-CONTEXT-UNIQUE" not in material_file.content:
                    raise AssertionError("Student could not open the course material")
                expect(await client.get(f"/api/courses/materials/{material['id']}/file", headers=outsider_headers), 403)

                import app.services.chat_service as chat_service
                captured_context: dict = {}

                async def fake_ai(**kwargs):
                    captured_context.update(kwargs)
                    return {"response": "Context received", "context_source": "course_material", "filename_display": "lesson.txt"}

                chat_service.get_deepseek_response = fake_ai
                chat_result = expect(await client.post("/api/chat/send", headers=student_headers, data={
                    "message": "What law is in this chapter?",
                    "course_id": course["id"],
                    "chapter_id": chapter["id"],
                    "chapter_index": str(chapter["sort_order"]),
                }), 200)
                if "COURSE-CONTEXT-UNIQUE" not in (captured_context.get("reference_context") or ""):
                    raise AssertionError("Uploaded chapter material was not passed to the AI context")
                conversations = expect(await client.get("/api/chat/conversations", headers=student_headers), 200)["conversations"]
                if not any(item["id"] == chat_result["conversation_id"] and item["chapter_id"] == chapter["id"] for item in conversations):
                    raise AssertionError("Chapter conversation was not persisted with its stable chapter id")

                assignment = expect(await client.post(f"/api/courses/{course['id']}/assignments", headers=ta_headers, json={
                    "title": "Attachment smoke", "instructions": "Upload a text file", "max_score": 100,
                }), 200)
                expect(await client.post(f"/api/assignments/{assignment['id']}/publish", headers=ta_headers), 200)
                submission = expect(await client.post(
                    f"/api/assignments/{assignment['id']}/submit",
                    headers=student_headers,
                    data={"answer_text": "My answer"},
                    files={"file": ("answer.txt", b"attachment-content", "text/plain")},
                ), 200)
                attachment = await client.get(f"/api/submissions/{submission['id']}/file", headers=ta_headers)
                if attachment.status_code != 200 or attachment.content != b"attachment-content":
                    raise AssertionError(f"TA attachment download failed: {attachment.status_code} {attachment.text}")
                expect(await client.get(f"/api/submissions/{submission['id']}/file", headers=outsider_headers), 403)

                contacts = expect(await client.get("/api/messaging/contacts", headers=student_headers), 200)["contacts"]
                teacher_contact = next(item for item in contacts if item["user"]["id"] == teacher["id"])
                ta_contact = next(item for item in contacts if item["user"]["id"] == ta["id"])

                teacher_thread = expect(await client.post("/api/messaging/threads", headers=student_headers, json={
                    "course_id": teacher_contact["course_id"], "recipient_id": teacher["id"],
                }), 200)
                expect(await client.post(f"/api/messaging/threads/{teacher_thread['id']}/messages", headers=student_headers, json={"content": "Teacher, I have a question."}), 200)
                teacher_threads = expect(await client.get("/api/messaging/threads", headers=teacher_headers), 200)["threads"]
                if not any(item["id"] == teacher_thread["id"] for item in teacher_threads):
                    raise AssertionError("Teacher did not receive the student thread")

                expect(await client.patch(
                    f"/api/messaging/permissions/{course['id']}/{student['id']}",
                    headers=teacher_headers,
                    json={"accepted": False},
                ), 200)
                expect(await client.post(f"/api/messaging/threads/{teacher_thread['id']}/messages", headers=student_headers, json={"content": "This must be blocked."}), 403)
                expect(await client.post(f"/api/messaging/threads/{teacher_thread['id']}/messages", headers=teacher_headers, json={"content": "I can still reply."}), 200)

                ta_thread = expect(await client.post("/api/messaging/threads", headers=student_headers, json={
                    "course_id": ta_contact["course_id"], "recipient_id": ta["id"],
                }), 200)
                expect(await client.post(f"/api/messaging/threads/{ta_thread['id']}/messages", headers=student_headers, json={"content": "TA, please help."}), 200)
                ta_detail = expect(await client.get(f"/api/messaging/threads/{ta_thread['id']}", headers=ta_headers), 200)
                if ta_detail["messages"][-1]["content"] != "TA, please help.":
                    raise AssertionError("TA did not receive the student message")

        print("Course materials, chapter AI, attachment and messaging smoke test passed.")


if __name__ == "__main__":
    asyncio.run(run())
