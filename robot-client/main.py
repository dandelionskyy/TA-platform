#!/usr/bin/env python3
"""
Robot client for TA Platform — runs on Raspberry Pi.
Connects via WebSocket to server for telemetry upload and voice pipeline.
"""
import asyncio
import json
import websockets
import logging
from config import SERVER_URL, ROBOT_ID, AUTH_KEY
from telemetry import TelemetryReader
from audio_capture import AudioCapture
from audio_player import AudioPlayer

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
                                # TODO: Send motor commands via motor_controller

                        except json.JSONDecodeError:
                            logger.warning(f"Invalid message: {message[:100]}")

                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Connection closed")
                finally:
                    telemetry_task.cancel()

        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            logger.error(f"Connection failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        logger.info("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
