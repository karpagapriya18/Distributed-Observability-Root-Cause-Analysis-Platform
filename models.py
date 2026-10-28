from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class NotificationAttempt(Base):
    __tablename__ = "notification_attempts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
    )

    # References are IDs only; other services own those records.
    order_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    payment_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="pending",
        index=True,
    )

    scenario: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="normal",
    )

    correlation_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    trace_id: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    )