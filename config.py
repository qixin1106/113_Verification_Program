from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """系统配置类"""
    SECRET_KEY: str = "your-secret-key-change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DB_URL: str = "sqlite://db.sqlite3"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()