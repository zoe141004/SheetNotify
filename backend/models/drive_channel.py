"""
DriveWatchChannel model — tracks Google Drive push-notification channels.

One channel is created per (user, spreadsheet) so that a single watch covers
every subscription on that spreadsheet (sheet-level or file-level). Drive
channels expire (max 1 day) and must be renewed by re-issuing the watch.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class DriveWatchChannel(Base):
    __tablename__ = "drive_watch_channels"

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

    # The channel id we generate and send to Google (also our lookup key on the
    # incoming notification via the X-Goog-Channel-ID header).
    channel_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # Returned by Google; required to stop the channel.
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Secret we set and validate against X-Goog-Channel-Token on each notification.
    channel_token: Mapped[str] = mapped_column(String(255), nullable=False)
    expiration: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "spreadsheet_id", name="uq_drive_channel_user_spreadsheet"),
    )

    user = relationship("User")
