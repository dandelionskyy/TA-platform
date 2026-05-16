from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict
from app.core.security import decode_token


class ChatWebSocketManager:
    """Manages WebSocket connections for streaming chat responses."""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str):
        # Authenticate via token query param
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=4001, reason="Missing token")
            return False
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token")
            return False

        await websocket.accept()
        self.active_connections[conversation_id] = websocket
        return True

    def disconnect(self, conversation_id: str):
        self.active_connections.pop(conversation_id, None)

    async def send_message(self, conversation_id: str, data: str):
        ws = self.active_connections.get(conversation_id)
        if ws:
            try:
                await ws.send_text(data)
            except Exception:
                self.disconnect(conversation_id)

    async def stream_response(self, conversation_id: str, full_text: str, chunk_size: int = 10):
        """Simulate streaming by sending text in chunks."""
        ws = self.active_connections.get(conversation_id)
        if not ws:
            return
        for i in range(0, len(full_text), chunk_size):
            chunk = full_text[i:i + chunk_size]
            await ws.send_text(chunk)


chat_manager = ChatWebSocketManager()
