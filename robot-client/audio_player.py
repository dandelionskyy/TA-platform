"""
Audio playback through speaker for TTS responses.
Supports both PyAudio playback and system command fallback.
"""
import base64
import tempfile
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


class AudioPlayer:
    def __init__(self):
        self._audio = None
        if HAS_PYAUDIO:
            self._audio = pyaudio.PyAudio()

    async def play_base64(self, audio_b64: str):
        """Decode base64 audio and play through speaker."""
        if not audio_b64:
            return

        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception:
            logger.error("Invalid base64 audio data")
            return

        # Write to temp file and play with system command (most reliable cross-platform)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            tmp_path = f.name

        try:
            if os.name == "nt":
                subprocess.run(["start", tmp_path], shell=True)
            else:
                # Linux (Raspberry Pi): try mpg123, aplay, or ffplay
                for player in ["mpg123", "aplay", "ffplay", "paplay"]:
                    try:
                        subprocess.run([player, tmp_path], timeout=15, check=True)
                        break
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        continue
        except Exception as e:
            logger.error(f"Playback error: {e}")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def close(self):
        if self._audio:
            self._audio.terminate()
