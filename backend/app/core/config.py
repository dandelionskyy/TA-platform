from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "TA Platform"
    DEBUG: bool = False
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://ta_admin:ta_platform@localhost:5432/ta_platform"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # JWT
    JWT_SECRET: str = "change-me-to-a-random-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 30
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

    # File storage
    UPLOAD_DIR: str = "./uploads"
    KNOWLEDGE_BASE_DIR: str = "./app/knowledge_base"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
