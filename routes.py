import math
import os
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from services.notification.database import engine
from services.notification.models import NotificationAttempt
from services.notification.schemas import (
    NotificationCreate,
    NotificationRead,
)
from shared.telemetry import get_current_trace_id


router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["Notifications"],
)


def error_response(code, message, status_code):
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
            },
        },
    )


def notification_response(notification, payload, replayed=False):
    if (
        notification.order_id != str(payload.order_id)
        or notification.payment_id != str(payload.payment_id)
        or notification.scenario != payload.scenario
    ):
        return error_response(
            "IDEMPOTENCY_CONFLICT",
            "This key was already used for a different request",
            409,
        )

    data = NotificationRead.model_validate(
        notification
    ).model_dump(mode="json")

    return JSONResponse(
        status_code=200 if replayed else 201,
        headers={
            "X-Correlation-ID": notification.correlation_id,
        },
        content={
            "success": True,
            "data": data,
            "meta": {
                "replayed": replayed,
                "simulated": True,
            },
        },
    )


@router.post(
    "",
    status_code=201,
    responses={
        200: {"description": "Previously recorded notification"},
        409: {"description": "Idempotency key conflict"},
        422: {"description": "Invalid request or unsupported scenario"},
        503: {"description": "Database or configuration unavailable"},
    },
)
def create_notification(
    payload: NotificationCreate,
    idempotency_key: Annotated[
        str,
        Header(
            min_length=1,
            max_length=64,
            pattern=r"^[A-Za-z0-9._-]+$",
        ),
    ],
    x_correlation_id: Annotated[
        str | None,
        Header(
            min_length=1,
            max_length=64,
            pattern=r"^[A-Za-z0-9._-]+$",
        ),
    ] = None,
):
    supported = {
        "normal",
        "slow_payment",
        "notification_timeout",
    }

    if payload.scenario not in supported:
        return error_response(
            "SCENARIO_NOT_IMPLEMENTED",
            "Supported scenarios: normal, slow_payment, notification_timeout",
            422,
        )

    statement = select(NotificationAttempt).where(
        NotificationAttempt.idempotency_key == idempotency_key
    )

    try:
        with Session(engine) as session:
            existing = session.scalar(statement)

            if existing is not None:
                return notification_response(
                    existing,
                    payload,
                    replayed=True,
                )

        if payload.scenario == "notification_timeout":
            try:
                delay = float(
                    os.getenv("NOTIFICATION_DELAY_SECONDS", "8")
                )

                if not math.isfinite(delay) or not 0 <= delay <= 30:
                    raise ValueError("Invalid delay")

            except ValueError:
                return error_response(
                    "NOTIFICATION_CONFIGURATION_ERROR",
                    "Notification delay must be between 0 and 30 seconds",
                    503,
                )

            # The caller may time out while this operation continues.
            time.sleep(delay)

        notification = NotificationAttempt(
            id=str(uuid4()),
            order_id=str(payload.order_id),
            payment_id=str(payload.payment_id),
            idempotency_key=idempotency_key,
            status="simulated_sent",
            scenario=payload.scenario,
            correlation_id=x_correlation_id or str(uuid4()),
            trace_id=get_current_trace_id(),
            error_message=None,
        )

        with Session(engine, expire_on_commit=False) as session:
            with session.begin():
                session.add(notification)
                session.flush()
                session.refresh(notification)

            return notification_response(notification, payload)

    except IntegrityError:
        # Handle concurrent requests using the same key.
        try:
            with Session(engine) as session:
                existing = session.scalar(statement)

                if existing is not None:
                    return notification_response(
                        existing,
                        payload,
                        replayed=True,
                    )

        except SQLAlchemyError:
            pass

        return error_response(
            "NOTIFICATION_WRITE_FAILED",
            "Unable to save the notification attempt",
            503,
        )

    except SQLAlchemyError:
        return error_response(
            "DATABASE_UNAVAILABLE",
            "Notification database is unavailable",
            503,
        )