from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "TA Platform"
    DEBUG: bool = True
    PORT: int = 8000

    # Database — SQLite by default for zero-dependency demo
    DATABASE_URL: str = "sqlite+aiosqlite:///./ta_platform.db"

    # Redis — optional, disabled by default for demo
    USE_REDIS: bool = False
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    JWT_SECRET: str = "demo-secret-change-in-production-please-use-a-strong-random-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 480  # 8 hours for demo convenience
    JWT_REFRESH_EXPIRE_DAYS: int = 7

    # DeepSeek API — ★ the only thing you need to configure ★
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_BASE: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL_NAME: str = "deepseek-chat"

    # SMS (Alibaba Cloud) — leave empty for demo mode (code printed in console)
    ALIBABA_SMS_ACCESS_KEY: str = ""
    ALIBABA_SMS_SECRET: str = ""
    ALIBABA_SMS_SIGN_NAME: str = ""
    ALIBABA_SMS_TEMPLATE_CODE: str = ""

    # File storage
    UPLOAD_DIR: str = "./uploads"
    KNOWLEDGE_BASE_DIR: str = "./app/knowledge_base"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
