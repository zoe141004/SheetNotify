"""
Lightweight database schema synchronization for backward-compatible deploys.
"""

from sqlalchemy.ext.asyncio import AsyncEngine


async def ensure_polling_schema(engine: AsyncEngine) -> None:
    """Add missing polling and diff columns if they do not exist yet."""
    statements = [
        """
        ALTER TABLE sheet_subscriptions
        ADD COLUMN IF NOT EXISTS polling_enabled BOOLEAN DEFAULT TRUE
        """,
        """
        ALTER TABLE sheet_subscriptions
        ADD COLUMN IF NOT EXISTS polling_interval_minutes INTEGER DEFAULT 1
        """,
        """
        ALTER TABLE sheet_subscriptions
        ADD COLUMN IF NOT EXISTS track_all_sheets BOOLEAN DEFAULT FALSE
        """,
        """
        ALTER TABLE sheet_subscriptions
        ADD COLUMN IF NOT EXISTS monitored_sheet_names JSONB
        """,
        """
        ALTER TABLE sheet_subscriptions
        ADD COLUMN IF NOT EXISTS last_state_snapshot JSONB
        """,
        """
        ALTER TABLE sheet_subscriptions
        ADD COLUMN IF NOT EXISTS last_polled_at TIMESTAMP WITH TIME ZONE
        """,
        """
        ALTER TABLE sheet_subscriptions
        ADD COLUMN IF NOT EXISTS last_poll_error TEXT
        """,
        """
        ALTER TABLE sheet_subscriptions
        ADD COLUMN IF NOT EXISTS poll_failure_count INTEGER DEFAULT 0
        """,
        """
        ALTER TABLE notification_logs
        ADD COLUMN IF NOT EXISTS before_data JSONB
        """,
        """
        ALTER TABLE notification_logs
        ADD COLUMN IF NOT EXISTS after_data JSONB
        """,
        """
        ALTER TABLE notification_logs
        ADD COLUMN IF NOT EXISTS changed_columns JSONB
        """,
        """
        ALTER TABLE notification_logs
        ADD COLUMN IF NOT EXISTS cell_reference VARCHAR(50)
        """,
        """
        ALTER TABLE notification_logs
        ADD COLUMN IF NOT EXISTS change_type VARCHAR(20)
        """,
        """
        ALTER TABLE notification_logs
        ADD COLUMN IF NOT EXISTS detection_method VARCHAR(20)
        """,
    ]

    async with engine.begin() as conn:
        for statement in statements:
            await conn.exec_driver_sql(statement)