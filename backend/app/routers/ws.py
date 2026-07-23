import base64
import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionFactory
from app.core.security import decode_token
from app.models.user import User
from app.models.robot import RobotStatus, RobotQuestion
from app.models.usage_log import UsageLog
from app.services.voice_service import transcribe_audio, synthesize_speech
from app.ai.deepseek_client import get_deepseek_response
from app.websocket.robot_ws import robot_manager

settings = get_settings()
router = APIRouter(tags=["websocket"])


def robot_key_valid(robot_id: str, key: str) -> bool:
    pairs = {}
    for item in settings.ROBOT_AUTH_KEYS.split(","):
        if ":" in item:
            name, secret = item.split(":", 1)
            pairs[name.strip()] = secret.strip()
    return bool(robot_id and key and pairs.get(robot_id) == key)


async def upsert_robot(robot_id: str, data: dict) -> dict:
    now = datetime.now(timezone.utc)
    async with AsyncSessionFactory() as db:
        robot = await db.scalar(select(RobotStatus).where(RobotStatus.robot_id == robot_id))
        if not robot:
            robot = RobotStatus(robot_id=robot_id, robot_name=robot_id)
            db.add(robot)
            await db.flush()
        requested_status = str(data.get("status", robot.status))
        robot.status = requested_status if requested_status in {"active", "standby", "offline", "charging"} else "standby"
        robot.battery_pct = max(0, min(100, int(data.get("battery", robot.battery_pct or 0))))
        robot.position_x = data.get("position_x", robot.position_x)
        robot.position_y = data.get("position_y", robot.position_y)
        robot.position_label = str(data.get("position_label", robot.position_label or ""))[:200]
        robot.last_seen_at = now
        robot.last_heartbeat_at = now
        await db.commit()
        return {
            "type": "robot_status",
            "robot_id": robot.robot_id,
            "robot_name": robot.robot_name,
            "status": robot.status,
            "battery_pct": robot.battery_pct,
            "position_x": robot.position_x,
            "position_y": robot.position_y,
            "position_label": robot.position_label,
            "last_seen_at": now.isoformat(),
        }


async def robot_voice_question(robot_id: str, data: dict) -> dict:
    request_id = data.get("request_id") or ""
    student_id = data.get("student_id")
    text = str(data.get("text") or "").strip()
    try:
        if not text:
            audio_b64 = str(data.get("audio_base64") or "")
            if len(audio_b64) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024 * 2:
                raise ValueError("Audio is too large")
            text = await transcribe_audio(audio_b64, str(data.get("content_type") or "audio/wav"))
        if not text:
            raise ValueError("No speech was recognized")
        ai_result = await get_deepseek_response(
            user_question=text,
            mode="voice_chat",
            conversation_history=data.get("history") or [],
        )
        response_text = ai_result.get("response", "")
        audio = await synthesize_speech(response_text)
        async with AsyncSessionFactory() as db:
            robot = await db.scalar(select(RobotStatus).where(RobotStatus.robot_id == robot_id))
            if robot:
                valid_student = await db.scalar(select(User).where(User.id == student_id)) if student_id else None
                question = RobotQuestion(
                    robot_id=robot.id,
                    student_id=valid_student.id if valid_student else None,
                    question_text=text,
                    asr_text=text,
                    response_text=response_text,
                    mode="voice",
                    processing_status="completed",
                )
                db.add(question)
                if valid_student:
                    db.add(UsageLog(user_id=valid_student.id, action="robot_question"))
                await db.commit()
        return {"type": "tts_response", "request_id": request_id, "text": response_text, "audio": audio or ""}
    except Exception as exc:
        print(f"Robot voice request failed: {type(exc).__name__}: {exc}")
        return {"type": "voice_error", "request_id": request_id, "message": "Voice service is temporarily unavailable"}


@router.websocket("/ws/robot/connect")
async def robot_connect(websocket: WebSocket):
    robot_id = websocket.query_params.get("robot_id", "")
    key = websocket.query_params.get("key", "")
    if not robot_key_valid(robot_id, key):
        await websocket.close(code=4403, reason="Invalid robot credentials")
        return
    await robot_manager.connect_robot(websocket, robot_id)
    try:
        async for raw in websocket.iter_text():
            data = json.loads(raw)
            if data.get("type") == "telemetry":
                status = await upsert_robot(robot_id, data)
                await robot_manager.broadcast_telemetry(status)
            elif data.get("type") == "voice_question":
                await websocket.send_json(await robot_voice_question(robot_id, data))
    except (WebSocketDisconnect, ValueError, json.JSONDecodeError):
        pass
    finally:
        await robot_manager.disconnect_robot(robot_id)
        async with AsyncSessionFactory() as db:
            robot = await db.scalar(select(RobotStatus).where(RobotStatus.robot_id == robot_id))
            if robot:
                robot.status = "offline"
                robot.last_seen_at = datetime.now(timezone.utc)
                await db.commit()
        await robot_manager.broadcast_telemetry({"type": "robot_offline", "robot_id": robot_id})


@router.websocket("/ws/robot/viewer")
async def robot_viewer(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4401, reason="Invalid token")
        return
    await robot_manager.connect_viewer(websocket)
    try:
        async with AsyncSessionFactory() as db:
            result = await db.execute(select(RobotStatus))
            for robot in result.scalars().all():
                await websocket.send_json({
                    "type": "robot_status",
                    "robot_id": robot.robot_id,
                    "robot_name": robot.robot_name,
                    "status": robot.status,
                    "battery_pct": robot.battery_pct,
                    "position_x": robot.position_x,
                    "position_y": robot.position_y,
                    "position_label": robot.position_label,
                    "last_seen_at": robot.last_seen_at.isoformat() if robot.last_seen_at else None,
                })
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await robot_manager.disconnect_viewer(websocket)
