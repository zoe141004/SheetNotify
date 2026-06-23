"""
NotificationLog model — records every notification sent/failed/skipped.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sheet_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    spreadsheet_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spreadsheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    row_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_data: Mapped[dict] = mapped_column(JSONB, nullable=False)

    telegram_message: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="sent", server_default=text("'sent'")
    )
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        index=True,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_ip: Mapped[str | None] = mapped_column(INET, nullable=True)

    # Relationships
    user = relationship("User", back_populates="notification_logs")
    subscription = relationship("SheetSubscription", back_populates="notification_logs")
