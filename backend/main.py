"""
SheetNotify — FastAPI Backend Application
Main entry point for the API server.
"""

from contextlib import asynccontextmanager
import logging
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from config import settings
from database import engine, Base
from services.schema_sync import ensure_polling_schema
from services.poller import run_polling_loop
from services.drive_watch import run_drive_maintenance_loop

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await ensure_polling_schema(engine)

    # NOTE: Telegram webhook is registered ONCE via POST /api/telegram/setup-webhook
    # (or manually), not on every cold start — keeps scale-to-zero cold starts fast
    # and free of an external Telegram call. Re-run setup only if BACKEND_URL changes.

    background_tasks: list[asyncio.Task] = []
    if settings.ENABLE_POLLING:
        background_tasks.append(
            asyncio.create_task(run_polling_loop(settings.POLLING_CYCLE_SECONDS))
        )
    if settings.ENABLE_DRIVE_WEBHOOK:
        background_tasks.append(asyncio.create_task(run_drive_maintenance_loop()))

    yield

    for task in background_tasks:
        task.cancel()
    for task in background_tasks:
        try:
            await task
        except asyncio.CancelledError:
            pass
    await engine.dispose()


app = FastAPI(
    title="SheetNotify API",
    description="Real-time Google Sheets → Telegram notification platform",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/google1dc6bc0faf4c2840.html", response_class=PlainTextResponse)
async def google_verification():
    # Nội dung trả về chính là dòng chữ bên trong file Google yêu cầu
    return "google-site-verification: google1dc6bc0faf4c2840.html"

# ── CORS Middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins to prevent Vercel CORS issues
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include Routers ──
from routers import auth, sheets, telegram, webhook, logs, internal  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(sheets.router, prefix="/api/sheets", tags=["Google Sheets"])
app.include_router(telegram.router, prefix="/api/telegram", tags=["Telegram"])
app.include_router(webhook.router, prefix="/api/webhook", tags=["Webhook"])
app.include_router(internal.router, prefix="/api/internal", tags=["Internal"])
app.include_router(logs.router, prefix="/api/logs", tags=["Logs"])


@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "SheetNotify API", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}
