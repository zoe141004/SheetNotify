"""
SheetNotify — FastAPI Backend Application
Main entry point for the API server.
"""

from contextlib import asynccontextmanager
import logging
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base
from services.schema_sync import ensure_polling_schema
from services.poller import run_polling_loop
from services.telegram import set_telegram_webhook
from services.runtime_urls import resolve_backend_url

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await ensure_polling_schema(engine)

    if settings.ENVIRONMENT.lower() != "development":
        try:
            backend_url = resolve_backend_url()
            webhook_url = f"{backend_url}/api/telegram/webhook"
            await set_telegram_webhook(webhook_url)
        except Exception:
            logger.exception("Failed to auto-configure Telegram webhook")

    polling_task = None
    if settings.ENVIRONMENT.lower() != "development":
        polling_task = asyncio.create_task(run_polling_loop(60))

    yield

    if polling_task is not None:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    await engine.dispose()


app = FastAPI(
    title="SheetNotify API",
    description="Real-time Google Sheets → Telegram notification platform",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS Middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins to prevent Vercel CORS issues
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include Routers ──
from routers import auth, sheets, telegram, webhook, logs  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(sheets.router, prefix="/api/sheets", tags=["Google Sheets"])
app.include_router(telegram.router, prefix="/api/telegram", tags=["Telegram"])
app.include_router(webhook.router, prefix="/api/webhook", tags=["Webhook"])
app.include_router(logs.router, prefix="/api/logs", tags=["Logs"])


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "SheetNotify API", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}
