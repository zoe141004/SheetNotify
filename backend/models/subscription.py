"""
SheetSubscription model — tracks which sheets a user is monitoring.
"""
import secrets
from sqlalchemy import Column, String
import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, Integer, ForeignKey, UniqueConstraint, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class SheetSubscription(Base):
    __tablename__ = "sheet_subscriptions"

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

    spreadsheet_id: Mapped[str] = mapped_column(String(255), nullable=False)
    spreadsheet_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spreadsheet_url: Mapped[str | None] = mapped_column(String, nullable=True)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sheet_gid: Mapped[str | None] = mapped_column(String(50), nullable=True)

    webhook_secret = Column(
        String(255), 
        nullable=False, 
        default=lambda: secrets.token_hex(32),
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("TRUE"))
    script_installed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("FALSE")
    )
    last_known_row: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
    polling_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("TRUE")
    )
    polling_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1")
    )
    track_all_sheets: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("FALSE")
    )
    monitored_sheet_names: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    last_state_snapshot: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_poll_error: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    poll_failure_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )

    notification_template: Mapped[str | None] = mapped_column(String, nullable=True, default=None)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Unique constraint
    __table_args__ = (
        UniqueConstraint("user_id", "spreadsheet_id", "sheet_name", name="uq_user_sheet"),
    )

    # Relationships
    user = relationship("User", back_populates="subscriptions")
    notification_logs = relationship(
        "NotificationLog", back_populates="subscription", passive_deletes=True
    )
