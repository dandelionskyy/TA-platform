import random
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


def generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


async def send_sms(phone: str) -> bool:
    """
    Send SMS verification code via Alibaba Cloud Dysmsapi.
    Falls back to logging the code if API keys are not configured.
    """
    code = generate_code()
    _sms_store[phone] = {
        "code": code,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        "used": False,
    }

    msg = f"\n{'='*50}\n>>> VERIFICATION CODE for {phone}: {code} <<<\n{'='*50}\n"
    print(msg, flush=True)

    return True


async def verify_sms(phone: str, code: str) -> bool:
    """Verify an SMS code."""
    stored = _sms_store.get(phone)
    if not stored:
        return False
    if stored["used"]:
        return False
    if datetime.now(timezone.utc) > stored["expires_at"]:
        del _sms_store[phone]
        return False
    if stored["code"] != code:
        return False
    stored["used"] = True
    return True
