import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.services import bridge_tutor


@pytest.fixture
def provider(monkeypatch):
    settings = get_settings()
    for key, value in {
        "BRIDGE_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "test-key",
        "BRIDGE_DEEPSEEK_BASE_URL": "https://api.deepseek.com",
        "BRIDGE_LLM_URL": "http://ollama:11434", "BRIDGE_LLM_MODEL": "qwen2.5:1.5b",
    }.items():
        monkeypatch.setattr(settings, key, value)
    client_type = httpx.AsyncClient
    calls = []

    def respond(payload=None, status=200, handler=None):
        def transport(request):
            calls.append(request)
            return handler(request) if handler else httpx.Response(status, json=payload)
        monkeypatch.setattr(
            bridge_tutor.httpx, "AsyncClient",
            lambda **kwargs: client_type(transport=httpx.MockTransport(transport), **kwargs),
        )
    return settings, calls, respond


@pytest.mark.parametrize("raw", ['preamble {"ok":true} suffix', '{"ok":true', '[]', None])
def test_invalid_json_not_repaired(raw):
    assert bridge_tutor._parse_json_object(raw) is None


@pytest.mark.parametrize("payload", [
    {}, [], {"choices": []}, {"choices": [None]},
    {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
    {"choices": [{"finish_reason": "length", "message": {"content": '{"response":"ok"}'}}]},
])
def test_invalid_deepseek_result_fails_closed(provider, payload):
    _, calls, respond = provider
    respond(payload)
    assert asyncio.run(bridge_tutor._local_json("Return JSON")) is None
    assert len(calls) == 1  # No silent switch to another provider.


@pytest.mark.parametrize("status", [401, 429, 503])
def test_provider_http_errors_fail_closed(provider, status):
    _, calls, respond = provider
    respond({"error": "internal test detail"}, status=status)
    assert asyncio.run(bridge_tutor._local_json("Return JSON")) is None
    assert len(calls) == 1


@pytest.mark.parametrize("url", ["http://api.deepseek.com", "https://user:pass@api.deepseek.com", "https://api.deepseek.com?key=secret"])
def test_deepseek_credentials_not_sent_to_invalid_url(provider, url):
    settings, calls, respond = provider
    settings.BRIDGE_DEEPSEEK_BASE_URL = url
    respond({})
    assert asyncio.run(bridge_tutor._local_json("Return JSON")) is None
    assert not calls


def test_missing_credentials_and_unknown_provider_make_no_requests(provider):
    settings, calls, respond = provider
    respond({})
    settings.DEEPSEEK_API_KEY = ""
    assert asyncio.run(bridge_tutor._local_json("Return JSON")) is None
    settings.BRIDGE_PROVIDER = "unknown"
    assert asyncio.run(bridge_tutor._local_json("Return JSON")) is None
    assert not calls


def test_ollama_protocol_and_no_cloud_authorization(provider):
    settings, calls, respond = provider
    settings.BRIDGE_PROVIDER = "ollama"
    respond({"done": True, "done_reason": "stop", "response": '{"response":"ok"}'})
    assert asyncio.run(bridge_tutor._local_json("Return JSON")) == {"response": "ok"}
    assert str(calls[0].url) == "http://ollama:11434/api/generate"
    assert "authorization" not in calls[0].headers
    assert json.loads(calls[0].content)["options"]["num_predict"] == 768


@pytest.mark.parametrize("payload", [[], {}, {"done": False}, {"done": True, "done_reason": "length", "response": '{}'}])
def test_invalid_ollama_result_fails_closed(provider, payload):
    settings, _, respond = provider
    settings.BRIDGE_PROVIDER = "ollama"
    respond(payload)
    assert asyncio.run(bridge_tutor._local_json("Return JSON")) is None


def test_network_timeout_fails_closed(provider):
    _, calls, respond = provider
    def timeout(request):
        raise httpx.ReadTimeout("test", request=request)
    respond(handler=timeout)
    assert asyncio.run(bridge_tutor._local_json("Return JSON")) is None
    assert len(calls) == 1


def test_parent_cancellation_is_not_swallowed(provider):
    _, _, respond = provider
    def cancel(request):
        raise asyncio.CancelledError()
    respond(handler=cancel)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bridge_tutor._local_json("Return JSON"))


def test_turn_timeout_rolls_back_and_returns_retry(monkeypatch):
    from app.routers import bridge_tutor as router
    from app.schemas.bridge import TutorRequest

    class FakeDB:
        rolled_back = False
        async def rollback(self):
            self.rolled_back = True

    async def load(*args):
        return object()

    async def slow_turn(*args):
        await asyncio.sleep(1)
        pytest.fail("Timed out turn must be cancelled")

    monkeypatch.setattr(router, "load_anonymous_session", load)
    monkeypatch.setattr(router, "run_guarded_tutor", slow_turn)
    monkeypatch.setattr(get_settings(), "BRIDGE_TURN_TIMEOUT_SECONDS", 0.01)
    db = FakeDB()
    with pytest.raises(HTTPException) as error:
        asyncio.run(router.bridge_tutor_turn(TutorRequest(message="help"), "test", db))
    assert error.value.status_code == 503
    assert error.value.headers == {"Retry-After": "5"}
    assert db.rolled_back
