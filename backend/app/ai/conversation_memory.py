from typing import List, Dict, Optional
from datetime import datetime
import redis.asyncio as aioredis
from app.core.config import get_settings
import json

settings = get_settings()


class ConversationMemory:
    """Redis-backed conversation history store. Replaces the in-memory dict cache."""

    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None

    async def _get_redis(self):
        if self.redis is None:
            self.redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self.redis

    async def get_history(self, conversation_id: str, max_messages: int = 10) -> List[Dict[str, str]]:
        r = await self._get_redis()
        key = f"conv:{conversation_id}:history"
        raw = await r.lrange(key, -max_messages, -1)
        return [json.loads(m) for m in raw]

    async def add_message(self, conversation_id: str, role: str, content: str):
        r = await self._get_redis()
        key = f"conv:{conversation_id}:history"
        msg = json.dumps({"role": role, "content": content, "timestamp": datetime.now().isoformat()})
        await r.rpush(key, msg)
        # Keep max 30 messages in Redis
        await r.ltrim(key, -30, -1)
        # Set TTL of 7 days
        await r.expire(key, 60 * 60 * 24 * 7)

    async def clear_history(self, conversation_id: str):
        r = await self._get_redis()
        key = f"conv:{conversation_id}:history"
        await r.delete(key)

    async def close(self):
        if self.redis:
            await self.redis.close()
            self.redis = None


# Singleton
conversation_memory = ConversationMemory()
