from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.notification.database import engine
from services.notification import models as notification_models
Base = notification_models.Base
from services.notification.routes import router as notification_router
from shared.telemetry import instrument_service, shutdown_tracing


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    try:
        yield
    finally:
        try:
            engine.dispose()
        finally:
            shutdown_tracing()


app = FastAPI(
    title="Notification Service",
    description="Sample Notification Service for the Observability Platform",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", tags=["Service"])
def service_info():
    return {
        "success": True,
        "data": {
            "service": "notification-service",
            "message": "Notification Service API is running",
        },
    }


@app.get("/health", tags=["Health"])
def health():
    return {
        "success": True,
        "data": {
            "service": "notification-service",
            "status": "alive",
        },
    }


@app.get(
    "/ready",
    tags=["Health"],
    responses={
        503: {"description": "Notification database unavailable"},
    },
)
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "success": True,
            "data": {
                "service": "notification-service",
                "status": "ready",
                "database": "connected",
            },
        }

    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "Notification database is unavailable",
                },
            },
        )


app.include_router(notification_router)

instrument_service(
    app=app,
    service_name="notification-service",
    engine=engine,
)