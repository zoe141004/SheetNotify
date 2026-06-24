"""
Sheet subscription Pydantic schemas.
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class SubscriptionCreate(BaseModel):
    spreadsheet_id: str
    spreadsheet_name: Optional[str] = None
    spreadsheet_url: Optional[str] = None
    sheet_name: Optional[str] = None
    sheet_gid: Optional[str] = None
    notification_template: Optional[str] = None
    polling_enabled: bool = True
    polling_interval_minutes: int = 1
    track_all_sheets: bool = False
    monitored_sheet_names: Optional[list[str]] = None


class SubscriptionUpdate(BaseModel):
    is_active: Optional[bool] = None
    notification_template: Optional[str] = None
    script_installed: Optional[bool] = None
    polling_enabled: Optional[bool] = None
    polling_interval_minutes: Optional[int] = None
    track_all_sheets: Optional[bool] = None
    monitored_sheet_names: Optional[list[str]] = None


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    spreadsheet_id: str
    spreadsheet_name: Optional[str] = None
    spreadsheet_url: Optional[str] = None
    sheet_name: str
    sheet_gid: Optional[str] = None
    webhook_secret: str
    is_active: bool
    script_installed: bool
    last_known_row: int
    polling_enabled: bool
    polling_interval_minutes: int
    track_all_sheets: bool
    monitored_sheet_names: Optional[list[str]] = None
    last_polled_at: Optional[datetime] = None
    last_poll_error: Optional[str] = None
    poll_failure_count: int
    notification_template: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SpreadsheetInfo(BaseModel):
    id: str
    name: str
    url: str


class SheetTab(BaseModel):
    title: str
    sheet_id: int
    index: int
