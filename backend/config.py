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
    # NEVER hard-code real credentials here. Set them via environment variables.
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = "random-webhook-verify-token"
    TELEGRAM_BOT_USERNAME: str = "sheet1fybot"

    # ── App Config ──
    FRONTEND_URL: str = "http://localhost:5173"
    ENVIRONMENT: str = "development"
    BACKEND_URL: str = "http://localhost:8000"

    # Background polling worker (default change-detection trigger).
    ENABLE_POLLING: bool = True
    POLLING_CYCLE_SECONDS: int = 60
    # Pause a subscription's polling after this many consecutive failures
    # (e.g. revoked Google access) so we stop hammering a broken sheet.
    MAX_POLL_FAILURES: int = 10

    # Google Drive push notifications (near real-time trigger).
    # Requires BACKEND_URL to be a PUBLIC, domain-verified HTTPS URL
    # (a *.run.app URL cannot be verified — use a custom domain).
    ENABLE_DRIVE_WEBHOOK: bool = False
    DRIVE_WEBHOOK_TTL_SECONDS: int = 86400  # max allowed by Drive for files.watch
    DRIVE_CHANNEL_RENEW_BEFORE_SECONDS: int = 21600  # renew when <6h remaining
    DRIVE_MAINTENANCE_CYCLE_SECONDS: int = 1800  # check renewals every 30 min

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


# ── Startup safety checks (warn loudly on insecure production config) ──
if settings.ENVIRONMENT.lower() != "development":
    import logging as _logging

    _logger = _logging.getLogger("config")
    if settings.SECRET_KEY == "change-me-to-a-256-bit-secret-key":
        _logger.critical(
            "SECRET_KEY is using the insecure default value in a non-development "
            "environment. Set a strong SECRET_KEY env var immediately."
        )
    if not settings.TELEGRAM_BOT_TOKEN:
        _logger.warning("TELEGRAM_BOT_TOKEN is empty — Telegram notifications will fail.")
