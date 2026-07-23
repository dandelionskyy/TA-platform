import base64
from typing import Optional
import httpx
from app.core.config import get_settings

settings = get_settings()


async def transcribe_audio(audio_b64: str, content_type: str = "audio/wav") -> str:
    """Call a configured Alibaba-compatible ASR gateway.

    The gateway keeps provider-specific signing outside the platform. A text
    field can be supplied by the simulator so hardware-less development works.
    """
    if not audio_b64:
        return ""
    if not settings.ALIBABA_ASR_ENDPOINT:
        raise RuntimeError("ASR service is not configured")
    payload = {"audio_base64": audio_b64, "content_type": content_type}
    headers = {"X-App-Key": settings.ALIBABA_NLS_APP_KEY} if settings.ALIBABA_NLS_APP_KEY else {}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(settings.ALIBABA_ASR_ENDPOINT, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    return str(data.get("text") or data.get("result") or "").strip()


async def synthesize_speech(text: str) -> Optional[str]:
    if not text or not settings.ALIBABA_TTS_ENDPOINT:
        return None
    payload = {"text": text, "voice": settings.ALIBABA_TTS_VOICE, "format": "mp3"}
    headers = {"X-App-Key": settings.ALIBABA_NLS_APP_KEY} if settings.ALIBABA_NLS_APP_KEY else {}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(settings.ALIBABA_TTS_ENDPOINT, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    audio = data.get("audio_base64") or data.get("audio")
    if audio:
        return str(audio)
    if data.get("audio_url"):
        async with httpx.AsyncClient(timeout=30) as client:
            audio_response = await client.get(data["audio_url"])
            audio_response.raise_for_status()
            return base64.b64encode(audio_response.content).decode("ascii")
    return None
