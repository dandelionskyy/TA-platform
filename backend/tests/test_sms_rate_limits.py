"""Public SMS issuance must share its cooldown across application workers."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import auth
from app.schemas.auth import SendSmsRequest
from app.services import sms_service


PHONE = "13900009999"


class SharedRedis:
    """A minimal shared atomic SET NX implementation for concurrent requests."""

    def __init__(self):
        self.keys = {}

    async def set(self, key, value, *, ex, nx=False):
        if nx and key in self.keys:
            return False
        self.keys[key] = (value, ex)
        return True


def configured_sms():
    return SimpleNamespace(
        ALIBABA_SMS_ACCESS_KEY="configured",
        ALIBABA_SMS_SECRET="configured",
        ALIBABA_SMS_SIGN_NAME="configured",
        ALIBABA_SMS_TEMPLATE_CODE="configured",
    )


def test_cooldown_is_atomic_per_phone_across_concurrent_requests(monkeypatch):
    redis = SharedRedis()

    async def shared_store():
        return redis

    monkeypatch.setattr(sms_service, "_get_redis", shared_store)

    async def scenario():
        codes = await asyncio.gather(*(
            sms_service.issue_registration_code(PHONE, require_redis=True)
            for _ in range(8)
        ))
        assert sum(code is not None for code in codes) == 1
        assert redis.keys[f"sms:rate:{PHONE}"][1] == 60
        assert redis.keys[f"sms:code:{PHONE}"][1] == 300
        assert await sms_service.issue_registration_code("13900008888", require_redis=True)

    asyncio.run(scenario())


def test_billable_sms_fails_closed_when_shared_store_is_unavailable(monkeypatch):
    monkeypatch.setattr(sms_service, "settings", configured_sms())

    async def no_store():
        return None

    monkeypatch.setattr(sms_service, "_get_redis", no_store)
    sms_service._sms_store.pop(PHONE, None)
    with pytest.raises(sms_service.SmsRateStoreUnavailableError):
        asyncio.run(sms_service.send_sms(PHONE))
    assert PHONE not in sms_service._sms_store


def test_billable_sms_fails_closed_if_store_disconnects_after_check(monkeypatch):
    class DeadRedis:
        async def set(self, *_args, **_kwargs):
            raise ConnectionError("lost Redis connection")

    async def disconnected_store():
        return DeadRedis()

    monkeypatch.setattr(sms_service, "settings", configured_sms())
    monkeypatch.setattr(sms_service, "_get_redis", disconnected_store)
    with pytest.raises(sms_service.SmsRateStoreUnavailableError):
        asyncio.run(sms_service.send_sms(PHONE))


def test_sms_endpoint_returns_429_and_retry_after_during_phone_cooldown(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", configured_sms)

    async def phone_on_cooldown(_phone):
        raise sms_service.SmsCooldownError

    monkeypatch.setattr(auth, "send_sms", phone_on_cooldown)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(auth.send_sms_code(SendSmsRequest(phone=PHONE)))
    assert caught.value.status_code == 429
    assert caught.value.headers == {"Retry-After": "60"}


def test_sms_endpoint_returns_503_if_shared_cooldown_store_is_down(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", configured_sms)

    async def unavailable_store(_phone):
        raise sms_service.SmsRateStoreUnavailableError

    monkeypatch.setattr(auth, "send_sms", unavailable_store)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(auth.send_sms_code(SendSmsRequest(phone=PHONE)))
    assert caught.value.status_code == 503


@pytest.mark.parametrize("phone", [
    "13900009999 ", "+8613900009999", "008613900009999",
    "139 0000 9999", "1390000999X", "12900009999", "１３９００００９９９９",
])
def test_sms_phone_must_have_one_canonical_mainland_format(phone):
    with pytest.raises(ValidationError):
        SendSmsRequest(phone=phone)
