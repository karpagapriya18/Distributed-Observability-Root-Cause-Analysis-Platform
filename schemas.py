from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


Scenario = Literal[
    "normal",
    "slow_payment",
    "payment_failure",
    "notification_timeout",
    "invalid_downstream_response",
    "intermittent_unavailability",
]


class NotificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: UUID
    payment_id: UUID
    scenario: Scenario = "normal"


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    payment_id: str
    status: str
    scenario: Scenario
    correlation_id: str
    trace_id: str | None
    error_message: str | None
    created_at: datetime