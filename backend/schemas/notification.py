"""
Notification log Pydantic schemas.
"""

import uuid
from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel


class NotificationLogResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    subscription_id: Optional[uuid.UUID] = None
    spreadsheet_id: Optional[str] = None
    spreadsheet_name: Optional[str] = None
    sheet_name: Optional[str] = None
    row_number: Optional[int] = None
    row_data: dict[str, Any]
    telegram_message: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    received_at: datetime
    sent_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NotificationStats(BaseModel):
    total: int
    sent: int
    failed: int
    skipped: int
    today: int


class PaginatedLogs(BaseModel):
    items: list[NotificationLogResponse]
    total: int
    page: int
    per_page: int
    pages: int
