"""Integration tests against a real PostgreSQL database.

These exercise the parts that need Postgres-specific features (advisory locks,
JSONB, gen_random_uuid): the shared change engine and an authenticated API
route. External calls (Google Sheets, Telegram) are monkeypatched.

Skipped unless RUN_DB_TESTS=1 and DATABASE_URL points to a test Postgres.
Each test runs entirely inside one asyncio.run() (one event loop) and disposes
the engine at the end so the asyncpg pool never spans event loops.
"""

import asyncio
import os
import random
import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DB_TESTS"),
    reason="requires Postgres (set RUN_DB_TESTS=1 and DATABASE_URL)",
)


async def _setup_schema():
    import models  # noqa: F401  (register all tables)
    from database import Base, engine
    from services.schema_sync import ensure_polling_schema

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_polling_schema(engine)


def _snapshot(rows):
    from services.sheets import SheetSnapshot

    return SheetSnapshot(
        spreadsheet_id="ss",
        spreadsheet_name="Demo Sheet",
        sheet_name="Sheet1",
        sheet_gid="0",
        headers=["Name", "Status"],
        rows=rows,
        fetched_at=datetime.now(timezone.utc),
    )


def test_polling_flow_baseline_then_change(monkeypatch):
    """Baseline poll sends nothing; a later change sends one message + logs it."""
    from models.subscription import SheetSubscription
    from models.user import User

    state = {"rows": [{"_row_number": 2, "Name": "Alice", "Status": "present"}]}
    sent: list[tuple] = []

    async def fake_snapshot(*args, **kwargs):
        return _snapshot(state["rows"])

    async def fake_send(chat_id, text, parse_mode="HTML"):
        sent.append((chat_id, text))
        return True

    monkeypatch.setattr("services.change_processor.get_sheet_snapshot", fake_snapshot)
    monkeypatch.setattr("services.change_processor.send_telegram_message", fake_send)

    async def _run():
        await _setup_schema()
        from sqlalchemy import select

        from database import async_session, engine
        from models.notification import NotificationLog
        from services.change_processor import process_subscription_changes

        try:
            async with async_session() as session:
                user = User(
                    google_id=str(uuid.uuid4()),
                    email=f"{uuid.uuid4()}@example.com",
                    telegram_chat_id=random.randint(1, 2_000_000_000),
                    google_access_token="tok",
                    google_token_expiry=datetime.now(timezone.utc).replace(year=2099),
                )
                session.add(user)
                await session.flush()
                sub = SheetSubscription(
                    user_id=user.id,
                    spreadsheet_id=f"ss-{uuid.uuid4()}",
                    sheet_name="Sheet1",
                    polling_enabled=True,
                )
                session.add(sub)
                await session.commit()
                sub_id = sub.id

            async with async_session() as session:
                r1 = await process_subscription_changes(
                    session, sub_id, detection_method="polling",
                    respect_interval=False, require_polling_enabled=True,
                )

            # Add a new row, then poll again.
            state["rows"] = state["rows"] + [
                {"_row_number": 3, "Name": "Bob", "Status": "absent"}
            ]
            async with async_session() as session:
                r2 = await process_subscription_changes(
                    session, sub_id, detection_method="polling",
                    respect_interval=False, require_polling_enabled=True,
                )

            async with async_session() as session:
                logs = (
                    await session.execute(
                        select(NotificationLog).where(
                            NotificationLog.subscription_id == sub_id
                        )
                    )
                ).scalars().all()
            return r1, r2, logs
        finally:
            await engine.dispose()

    r1, r2, logs = asyncio.run(_run())

    assert r1["status"] == "baseline"
    assert r2["status"] == "ok" and r2["changes"] == 1
    assert len(logs) == 1
    assert logs[0].change_type == "insert"
    assert len(sent) == 1  # exactly one consolidated Telegram message


def test_authenticated_subscriptions_endpoint(monkeypatch):
    """A valid JWT returns the user's subscriptions through the real DB."""
    import httpx

    import main
    from models.subscription import SheetSubscription
    from models.user import User
    from services.auth import create_access_token

    async def _run():
        await _setup_schema()
        from database import async_session, engine

        try:
            async with async_session() as session:
                user = User(
                    google_id=str(uuid.uuid4()),
                    email=f"{uuid.uuid4()}@example.com",
                    telegram_chat_id=random.randint(1, 2_000_000_000),
                )
                session.add(user)
                await session.flush()
                session.add(
                    SheetSubscription(
                        user_id=user.id,
                        spreadsheet_id=f"ss-{uuid.uuid4()}",
                        sheet_name="Sheet1",
                    )
                )
                await session.commit()
                user_id = user.id

            token, _ = create_access_token(user_id)
            transport = httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(
                    "/api/sheets/subscriptions",
                    headers={"Authorization": f"Bearer {token}"},
                )
            return resp.status_code, resp.json()
        finally:
            await engine.dispose()

    status_code, body = asyncio.run(_run())
    assert status_code == 200
    assert isinstance(body, list) and len(body) == 1
    assert body[0]["sheet_name"] == "Sheet1"
