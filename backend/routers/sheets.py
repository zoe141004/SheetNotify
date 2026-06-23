"""
Google Sheets router — list sheets, manage subscriptions, get Apps Script.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from middleware.auth import get_current_user
from models.user import User
from schemas.subscription import (
    SubscriptionCreate,
    SubscriptionResponse,
    SubscriptionUpdate,
    SpreadsheetInfo,
    SheetTab,
)
from services.sheets import (
    create_subscription,
    delete_subscription,
    generate_apps_script,
    get_spreadsheet_tabs,
    get_subscription_by_id,
    get_user_subscriptions,
    list_user_spreadsheets,
)

router = APIRouter()


@router.get("/list", response_model=list[SpreadsheetInfo])
async def list_sheets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all Google Sheets accessible by the user."""
    return await list_user_spreadsheets(current_user, db)


@router.get("/{spreadsheet_id}/tabs", response_model=list[SheetTab])
async def get_tabs(
    spreadsheet_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tabs/sheets in a given spreadsheet."""
    return await get_spreadsheet_tabs(current_user, db, spreadsheet_id)


@router.post("/subscribe", response_model=SubscriptionResponse, status_code=201)
async def subscribe_to_sheet(
    data: SubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new sheet subscription."""
    try:
        subscription = await create_subscription(
            db=db,
            user=current_user,
            spreadsheet_id=data.spreadsheet_id,
            sheet_name=data.sheet_name,
            spreadsheet_name=data.spreadsheet_name,
            spreadsheet_url=data.spreadsheet_url,
            sheet_gid=data.sheet_gid,
            notification_template=data.notification_template,
        )
        return subscription
    except Exception as e:
        if "uq_user_sheet" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You are already subscribed to this sheet",
            )
        raise


@router.get("/subscriptions", response_model=list[SubscriptionResponse])
async def list_subscriptions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all subscriptions for the current user."""
    return await get_user_subscriptions(db, current_user.id)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def get_subscription(
    subscription_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific subscription."""
    sub = await get_subscription_by_id(db, subscription_id, current_user.id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return sub


@router.patch("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
async def update_subscription(
    subscription_id: uuid.UUID,
    data: SubscriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a subscription (toggle active, change template, etc.)."""
    sub = await get_subscription_by_id(db, subscription_id, current_user.id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if data.is_active is not None:
        sub.is_active = data.is_active
    if data.notification_template is not None:
        sub.notification_template = data.notification_template
    if data.script_installed is not None:
        sub.script_installed = data.script_installed

    await db.flush()
    await db.refresh(sub)
    return sub


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def remove_subscription(
    subscription_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a subscription."""
    deleted = await delete_subscription(db, subscription_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subscription not found")


@router.get("/subscriptions/{subscription_id}/script")
async def get_script(
    subscription_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the Google Apps Script code for a subscription."""
    sub = await get_subscription_by_id(db, subscription_id, current_user.id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Subscription not found")

    webhook_url = f"{settings.BACKEND_URL}/api/webhook/{sub.webhook_secret}"
    script = generate_apps_script(
        webhook_url=webhook_url,
        webhook_secret=sub.webhook_secret,
        sheet_name=sub.sheet_name,
    )
    return {"script": script, "webhook_url": webhook_url}
