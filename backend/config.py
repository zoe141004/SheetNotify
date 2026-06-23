"""
Application configuration using Pydantic Settings.
All values are read from environment variables or .env file.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sheetsnotify"

    # ── JWT ──
    SECRET_KEY: str = "change-me-to-a-256-bit-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7

    # ── Google OAuth ──
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"

    # ── Telegram ──
    TELEGRAM_BOT_TOKEN: str = "8715974789:AAHAy38XKg-q8RSpSak9yFLTCS0hZ8H-vj8"
    TELEGRAM_WEBHOOK_SECRET: str = "random-webhook-verify-token"
    TELEGRAM_BOT_USERNAME: str = "sheet1fybot"

    # ── App Config ──
    FRONTEND_URL: str = "http://localhost:5173"
    ENVIRONMENT: str = "development"
    BACKEND_URL: str = "http://localhost:8000"

    # ── Google API Scopes ──
    GOOGLE_SCOPES: list[str] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()
