from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, List
import json
import asyncio
from datetime import datetime, timezone


class RobotConnectionManager:
    """Manages WebSocket connections for robot telemetry and voice pipeline."""

    def __init__(self):
        self.robot_connections: Dict[str, WebSocket] = {}  # robot_id -> WS
        self.viewer_connections: List[WebSocket] = []  # web clients watching robot status

    async def connect_robot(self, websocket: WebSocket, robot_id: str):
        await websocket.accept()
        self.robot_connections[robot_id] = websocket

    async def disconnect_robot(self, robot_id: str):
        self.robot_connections.pop(robot_id, None)

    async def connect_viewer(self, websocket: WebSocket):
        await websocket.accept()
        self.viewer_connections.append(websocket)

    async def disconnect_viewer(self, websocket: WebSocket):
        if websocket in self.viewer_connections:
            self.viewer_connections.remove(websocket)

    async def broadcast_telemetry(self, data: dict):
        """Broadcast robot status to all viewer clients."""
        dead_connections = []
        message = json.dumps(data)
        for ws in self.viewer_connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead_connections.append(ws)
        for ws in dead_connections:
            if ws in self.viewer_connections:
                self.viewer_connections.remove(ws)

    async def send_to_robot(self, robot_id: str, data: dict):
        """Send command/data to a specific robot."""
        ws = self.robot_connections.get(robot_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                await self.disconnect_robot(robot_id)

    @property
    def active_robots(self) -> List[str]:
        return list(self.robot_connections.keys())


robot_manager = RobotConnectionManager()
