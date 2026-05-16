"""
Audio capture from microphone for voice questions.
Supports both PyAudio and simulation mode.
"""
import base64
import asyncio
import logging

logger = logging.getLogger(__name__)

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


class AudioCapture:
    def __init__(self, sample_rate=16000, channels=1, chunk_size=1024):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self._recording = False
        self._audio = None
        self._stream = None

        if HAS_PYAUDIO:
            self._audio = pyaudio.PyAudio()

    def start_recording(self) -> bool:
        """Start microphone capture."""
        if HAS_PYAUDIO and self._audio:
            try:
                self._stream = self._audio.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size,
                )
                self._recording = True
                logger.info("Recording started")
                return True
            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
        logger.warning("PyAudio not available — recording disabled")
        return False

    def stop_recording(self) -> bytes:
        """Stop recording and return audio bytes."""
        self._recording = False
        frames = []
        if self._stream:
            try:
                # Read remaining frames
                while self._stream.get_read_available() > 0:
                    data = self._stream.read(self.chunk_size, exception_on_overflow=False)
                    frames.append(data)
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")
        return b"".join(frames)

    def record_to_base64(self, duration_sec: float = 5.0) -> str:
        """Record audio for a given duration and return base64-encoded WAV bytes."""
        # For simulation/fallback: return empty
        if not HAS_PYAUDIO or not self._audio:
            return ""

        try:
            stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=self.channels,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size,
            )

            frames = []
            for _ in range(0, int(self.sample_rate / self.chunk_size * duration_sec)):
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                frames.append(data)

            stream.stop_stream()
            stream.close()

            raw = b"".join(frames)
            return base64.b64encode(raw).decode("utf-8")
        except Exception as e:
            logger.error(f"Recording error: {e}")
            return ""

    def close(self):
        if self._audio:
            self._audio.terminate()
