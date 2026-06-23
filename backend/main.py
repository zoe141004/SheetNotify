"""
SheetNotify — FastAPI Backend Application
Main entry point for the API server.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
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
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
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
