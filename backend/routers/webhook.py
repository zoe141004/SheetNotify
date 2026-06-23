"""
Webhook router — receives data from Google Apps Script.
"""

from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from database import get_db
from services.notification import process_webhook_data

router = APIRouter()


@router.post("/{webhook_secret}")
async def receive_webhook(
    webhook_secret: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive webhook data from Google Apps Script.
    The webhook_secret path parameter authenticates the request.
    """
    payload = await request.json()

    # Get source IP
    source_ip = request.client.host if request.client else None

    result = await process_webhook_data(
        db=db,
        webhook_secret=webhook_secret,
        payload=payload,
        source_ip=source_ip,
    )

    return result
