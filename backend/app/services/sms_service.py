import secrets
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


class SmsCooldownError(Exception):
    """A verification code was requested for this phone too recently."""


class SmsRateStoreUnavailableError(Exception):
    """A shared rate limit store is required before sending a public SMS."""


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
    return f"{secrets.randbelow(1_000_000):06d}"


async def issue_registration_code(phone: str, *, require_redis: bool = False) -> str | None:
    """Create a short-lived code for delivery through the configured SMS service."""
    redis = await _get_redis()
    if require_redis and redis is None:
        # The local demo can issue codes without Redis, but an external SMS
        # delivery must use a cooldown shared by all application workers.
        raise SmsRateStoreUnavailableError
    code = generate_code()
    now = datetime.now(timezone.utc)
    record = {
        "code": code,
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
        "used": False,
        "attempts": 0,
    }

    if redis:
        rate_key = f"sms:rate:{phone}"
        try:
            if not await redis.set(rate_key, "1", ex=60, nx=True):
                return None
            await redis.set(f"sms:code:{phone}", json.dumps(record), ex=300)
        except Exception as exc:
            # Redis may disconnect after _get_redis succeeds. Never fall back
            # to a per-worker store for a public, billable SMS request.
            raise SmsRateStoreUnavailableError from exc
    else:
        existing = _sms_store.get(phone)
        sent_at = existing.get("sent_at") if existing else None
        if isinstance(sent_at, str):
            sent_at = datetime.fromisoformat(sent_at)
        if sent_at and now < sent_at + timedelta(seconds=60):
            return None
        record["sent_at"] = now
        record["expires_at"] = now + timedelta(minutes=5)
        _sms_store[phone] = record
    return code


async def send_sms(phone: str) -> bool:
    """
    Send SMS verification code via Alibaba Cloud Dysmsapi.
    Fail closed when no delivery service is configured.
    """
    if not all((settings.ALIBABA_SMS_ACCESS_KEY, settings.ALIBABA_SMS_SECRET,
                settings.ALIBABA_SMS_SIGN_NAME, settings.ALIBABA_SMS_TEMPLATE_CODE)):
        return False
    code = await issue_registration_code(phone, require_redis=True)
    if code is None:
        raise SmsCooldownError

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
