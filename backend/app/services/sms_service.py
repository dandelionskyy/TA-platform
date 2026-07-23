import random
import json
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.usage_log import UsageLog  # using existing table; in production use a dedicated sms_codes table
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# In-memory store for SMS codes (replace with Redis in production)
_sms_store: dict[str, dict] = {}
_redis = None


async def _get_redis():
    global _redis
    if _redis is not None or not settings.USE_REDIS:
        return _redis
    try:
        import redis.asyncio as aioredis
        _redis = await aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis.ping()
        return _redis
    except Exception:
        _redis = None
        return None


def generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


async def send_sms(phone: str) -> bool:
    """
    Send SMS verification code via Alibaba Cloud Dysmsapi.
    Falls back to logging the code if API keys are not configured.
    """
    redis = await _get_redis()
    code = generate_code()
    record = {
        "code": code,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "used": False,
        "attempts": 0,
    }

    if redis:
        rate_key = f"sms:rate:{phone}"
        if await redis.exists(rate_key):
            return False
        await redis.set(rate_key, "1", ex=60)
        await redis.set(f"sms:code:{phone}", json.dumps(record), ex=300)
    else:
        existing = _sms_store.get(phone)
        if existing and datetime.now(timezone.utc) < existing["sent_at"] + timedelta(seconds=60):
            return False
        record["sent_at"] = datetime.now(timezone.utc).isoformat()
        record["expires_at"] = datetime.now(timezone.utc) + timedelta(minutes=5)
        _sms_store[phone] = record

    if settings.ALIBABA_SMS_ACCESS_KEY and settings.ALIBABA_SMS_SECRET and settings.ALIBABA_SMS_SIGN_NAME and settings.ALIBABA_SMS_TEMPLATE_CODE:
        try:
            import asyncio
            import json as json_module
            from alibabacloud_tea_openapi import models as open_api_models
            from alibabacloud_dysmsapi20170525.client import Client
            from alibabacloud_dysmsapi20170525 import models as sms_models
            config = open_api_models.Config(
                access_key_id=settings.ALIBABA_SMS_ACCESS_KEY,
                access_key_secret=settings.ALIBABA_SMS_SECRET,
                endpoint="dysmsapi.aliyuncs.com",
            )
            client = Client(config)
            request = sms_models.SendSmsRequest(
                phone_numbers=phone,
                sign_name=settings.ALIBABA_SMS_SIGN_NAME,
                template_code=settings.ALIBABA_SMS_TEMPLATE_CODE,
                template_param=json_module.dumps({"code": code}),
            )
            response = await asyncio.to_thread(client.send_sms, request)
            if getattr(response.body, "code", "OK") != "OK":
                return False
        except Exception as exc:
            logger.error("Alibaba SMS request failed: %s", exc)
            return False
    else:
        msg = f"\n{'='*50}\n>>> DEV VERIFICATION CODE for {phone}: {code} <<<\n{'='*50}\n"
        print(msg, flush=True)

    return True


async def verify_sms(phone: str, code: str) -> bool:
    """Verify an SMS code."""
    redis = await _get_redis()
    if redis:
        raw = await redis.get(f"sms:code:{phone}")
        stored = json.loads(raw) if raw else None
    else:
        stored = _sms_store.get(phone)
    if not stored:
        return False
    if stored["used"]:
        return False
    expires_at = stored["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if datetime.now(timezone.utc) > expires_at:
        if redis:
            await redis.delete(f"sms:code:{phone}")
        else:
            del _sms_store[phone]
        return False
    if stored.get("attempts", 0) >= 5:
        return False
    if stored["code"] != code:
        stored["attempts"] = stored.get("attempts", 0) + 1
        if redis:
            await redis.set(f"sms:code:{phone}", json.dumps(stored), ex=300)
        return False
    stored["used"] = True
    if redis:
        await redis.delete(f"sms:code:{phone}")
    return True
