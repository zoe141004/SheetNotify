"""
Internal trigger endpoint for Cloud Scheduler (free scale-to-zero polling).

Instead of an always-on instance running the polling loop, Cloud Scheduler
calls POST /api/internal/poll every N minutes. The request wakes the Cloud Run
instance, one poll cycle runs, then the instance can scale back to zero.

Protected by a shared secret header so only our scheduler can trigger it.
"""

import logging

from fastapi import APIRouter, Header, HTTPException
from typing import Optional

from config import settings
from services.poller import run_poll_cycle

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/poll")
async def trigger_poll(x_internal_token: Optional[str] = Header(None)):
    """Run one polling cycle. Called by Cloud Scheduler."""
    if not settings.INTERNAL_POLL_SECRET or x_internal_token != settings.INTERNAL_POLL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    processed = await run_poll_cycle()
    return {"status": "ok", "subscriptions_processed": processed}
