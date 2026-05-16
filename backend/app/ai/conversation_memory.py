from typing import List, Dict, Optional
from datetime import datetime
from collections import defaultdict
from app.core.config import get_settings
import json

settings = get_settings()

# In-memory store — zero dependencies, survives as long as the server is running
_memory_store: Dict[str, list] = defaultdict(list)


class ConversationMemory:
    """Conversation history store. Uses in-memory dict; optionally Redis if configured."""

    def __init__(self):
        self.redis = None
        self._redis_available = False

    async def _init_redis(self):
        if self.redis is not None:
            return
        if not settings.USE_REDIS:
            self._redis_available = False
            return
        try:
            import redis.asyncio as aioredis
            self.redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await self.redis.ping()
            self._redis_available = True
        except Exception:
            self._redis_available = False
            self.redis = None

    async def get_history(self, conversation_id: str, max_messages: int = 10) -> List[Dict[str, str]]:
        await self._init_redis()

        if self._redis_available and self.redis:
            try:
                key = f"conv:{conversation_id}:history"
                raw = await self.redis.lrange(key, -max_messages, -1)
                return [json.loads(m) for m in raw]
            except Exception:
                pass

        # In-memory fallback
        msgs = _memory_store.get(conversation_id, [])
        return msgs[-max_messages:]

    async def add_message(self, conversation_id: str, role: str, content: str):
        await self._init_redis()

        msg = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}

        if self._redis_available and self.redis:
            try:
                key = f"conv:{conversation_id}:history"
                await self.redis.rpush(key, json.dumps(msg))
                await self.redis.ltrim(key, -30, -1)
                await self.redis.expire(key, 60 * 60 * 24 * 7)
                return
            except Exception:
                pass

        # In-memory fallback
        _memory_store[conversation_id].append(msg)
        if len(_memory_store[conversation_id]) > 30:
            _memory_store[conversation_id] = _memory_store[conversation_id][-30:]

    async def clear_history(self, conversation_id: str):
        await self._init_redis()

        if self._redis_available and self.redis:
            try:
                await self.redis.delete(f"conv:{conversation_id}:history")
                return
            except Exception:
                pass

        _memory_store.pop(conversation_id, None)

    async def close(self):
        if self.redis:
            try:
                await self.redis.close()
            except Exception:
                pass
            self.redis = None


conversation_memory = ConversationMemory()
