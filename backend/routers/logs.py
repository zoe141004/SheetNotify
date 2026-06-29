"""
Logs router — notification history and stats.
"""

import uuid
from math import ceil
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import get_current_user
from models.user import User
from models.notification import NotificationLog
from schemas.notification import NotificationStats, PaginatedLogs

router = APIRouter()


@router.get("", response_model=PaginatedLogs)
async def get_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    subscription_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated notification logs for the current user."""
    # Base query
    query = select(NotificationLog).where(NotificationLog.user_id == current_user.id)
    count_query = select(func.count(NotificationLog.id)).where(
        NotificationLog.user_id == current_user.id
    )

    # Filters
    if status:
        query = query.where(NotificationLog.status == status)
        count_query = count_query.where(NotificationLog.status == status)
    if subscription_id:
        query = query.where(NotificationLog.subscription_id == subscription_id)
        count_query = count_query.where(NotificationLog.subscription_id == subscription_id)

    # Count total
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = (
        query.order_by(NotificationLog.received_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    items = list(result.scalars().all())

    return PaginatedLogs(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=ceil(total / per_page) if total > 0 else 0,
    )


@router.get("/stats", response_model=NotificationStats)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get notification statistics for the current user."""
    base = select(func.count(NotificationLog.id)).where(
        NotificationLog.user_id == current_user.id
    )

    total_r = await db.execute(base)
    total = total_r.scalar() or 0

    sent_r = await db.execute(base.where(NotificationLog.status == "sent"))
    sent = sent_r.scalar() or 0

    failed_r = await db.execute(base.where(NotificationLog.status == "failed"))
    failed = failed_r.scalar() or 0

    skipped_r = await db.execute(base.where(NotificationLog.status == "skipped"))
    skipped = skipped_r.scalar() or 0

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_r = await db.execute(
        base.where(NotificationLog.received_at >= today_start)
    )
    today = today_r.scalar() or 0

    return NotificationStats(
        total=total,
        sent=sent,
        failed=failed,
        skipped=skipped,
        today=today,
    )
