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
    sheet_name: str
    sheet_gid: Optional[str] = None
    notification_template: Optional[str] = None


class SubscriptionUpdate(BaseModel):
    is_active: Optional[bool] = None
    notification_template: Optional[str] = None
    script_installed: Optional[bool] = None


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
