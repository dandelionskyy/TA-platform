import asyncio

import pytest

from app.core.config import get_settings
from app.services import bridge_tutor


def test_parse_json_object_accepts_fenced_json():
    assert bridge_tutor._parse_json_object('```json\n{"response":"ok"}\n```') == {
        "response": "ok"
    }


def test_deepseek_provider_uses_chat_completions(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "BRIDGE_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(settings, "BRIDGE_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr(settings, "BRIDGE_DEEPSEEK_MODEL", "deepseek-chat")

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {"content": '{"response":"ok"}'}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(bridge_tutor.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    result = asyncio.run(bridge_tutor._local_json("Return JSON"))

    assert result == {"response": "ok"}
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer test-key"
    assert captured["kwargs"]["json"]["model"] == "deepseek-chat"


def test_unknown_bridge_provider_fails_closed(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "BRIDGE_PROVIDER", "unknown")
    assert asyncio.run(bridge_tutor._local_json("Return JSON")) is None
