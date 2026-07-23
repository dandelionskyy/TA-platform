#!/usr/bin/env python3
"""
Robot client for TA Platform — runs on Raspberry Pi.
Connects via WebSocket to server for telemetry upload and voice pipeline.
"""
import asyncio
import json
import websockets
import logging
from config import SERVER_URL, ROBOT_ID, AUTH_KEY, VOICE_ENABLED, VOICE_INTERVAL_SECONDS
from telemetry import TelemetryReader
from audio_capture import AudioCapture
from audio_player import AudioPlayer
import uuid

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)


async def main():
    telemetry = TelemetryReader()
    audio_cap = AudioCapture()
    audio_player = AudioPlayer()

    ws_url = f"{SERVER_URL}/ws/robot/connect?robot_id={ROBOT_ID}&key={AUTH_KEY}"

    while True:
        try:
            logger.info(f"Connecting to {ws_url}...")
            async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
                logger.info("Connected!")

                # Start telemetry task
                async def send_telemetry():
                    while True:
                        try:
                            data = telemetry.read()
                            data["type"] = "telemetry"
                            await ws.send(json.dumps(data))
                        except Exception as e:
                            logger.error(f"Telemetry error: {e}")
                        await asyncio.sleep(2)

                telemetry_task = asyncio.create_task(send_telemetry())

                async def send_voice_questions():
                    while VOICE_ENABLED:
                        try:
                            audio_b64 = await asyncio.to_thread(audio_cap.record_to_base64, 5.0)
                            if audio_b64:
                                await ws.send(json.dumps({
                                    "type": "voice_question",
                                    "request_id": str(uuid.uuid4()),
                                    "audio_base64": audio_b64,
                                    "content_type": "audio/wav",
                                }))
                        except Exception as e:
                            logger.error(f"Voice capture error: {e}")
                        await asyncio.sleep(VOICE_INTERVAL_SECONDS)

                voice_task = asyncio.create_task(send_voice_questions()) if VOICE_ENABLED else None

                # Listen for server messages
                try:
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            msg_type = data.get("type")

                            if msg_type == "tts_response":
                                # Play audio response through speaker
                                audio_b64 = data.get("audio", "")
                                text = data.get("text", "")
                                logger.info(f"Playing TTS: {text[:50]}...")
                                await audio_player.play_base64(audio_b64)

                            elif msg_type == "set_status":
                                new_status = data.get("status", "standby")
                                logger.info(f"Status change: {new_status}")
                                telemetry.set_status(new_status)

                            elif msg_type == "move":
                                x, y = data.get("x"), data.get("y")
                                logger.info(f"Move command: ({x}, {y})")
                                if x is not None and y is not None:
                                    logger.info("Move target received; navigation is hardware-specific")

                        except json.JSONDecodeError:
                            logger.warning(f"Invalid message: {message[:100]}")

                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Connection closed")
                finally:
                    telemetry_task.cancel()
                    if voice_task:
                        voice_task.cancel()

        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            logger.error(f"Connection failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        logger.info("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
