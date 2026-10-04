import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache

# Find project root (where .env lives) relative to this file
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(_PROJECT_ROOT, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "TA Platform"
    DEBUG: bool = False
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./ta_platform.db"

    # Redis is enabled in production and gracefully disabled for local demo.
    USE_REDIS: bool = False
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    JWT_SECRET: str = "demo-secret-change-in-production-please-use-a-strong-random-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 480
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # DeepSeek API
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL_NAME: str = "deepseek-chat"

    # SMS (Alibaba Cloud)
    ALIBABA_SMS_ACCESS_KEY: str = ""
    ALIBABA_SMS_SECRET: str = ""
    ALIBABA_SMS_SIGN_NAME: str = ""
    ALIBABA_SMS_TEMPLATE_CODE: str = ""
    ALIBABA_NLS_APP_KEY: str = ""
    ALIBABA_NLS_ACCESS_KEY_ID: str = ""
    ALIBABA_NLS_ACCESS_KEY_SECRET: str = ""
    ALIBABA_TTS_VOICE: str = "siyue"
    ALIBABA_ASR_ENDPOINT: str = ""
    ALIBABA_TTS_ENDPOINT: str = ""

    # Runtime safety
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost"
    ROBOT_AUTH_KEYS: str = "TA-Robot-01:robot-secret-key-change-me"
    ROBOT_HEARTBEAT_TIMEOUT_SECONDS: int = 15
    MAX_UPLOAD_SIZE_MB: int = 10
    MAX_CONTEXT_MESSAGES: int = 12
    MAX_CONTEXT_CHARS: int = 24000
    SEED_DEMO_DATA: bool = False

    # BRIDGE uses institution-controlled model endpoints. Blank URLs disable
    # generation/indexing rather than silently sending student text elsewhere.
    BRIDGE_LLM_URL: str = ""
    BRIDGE_LLM_MODEL: str = ""
    BRIDGE_EMBEDDINGS_URL: str = ""
    BRIDGE_EMBEDDINGS_MODEL: str = "bge-m3"
    BRIDGE_ALLOW_LEXICAL_PROTOTYPE: bool = False
    BRIDGE_MIN_SIMILARITY: float = 0.65
    BRIDGE_UPLOAD_MAX_MB: int = 50
    BRIDGE_SESSION_DAYS: int = 30

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "debug"}
        return value

    # File storage
    UPLOAD_DIR: str = "./uploads"
    KNOWLEDGE_BASE_DIR: str = "./app/knowledge_base"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
