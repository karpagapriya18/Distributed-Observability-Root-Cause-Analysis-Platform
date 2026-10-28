import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

database_url = os.getenv("NOTIFICATIONS_DATABASE_URL")

if not database_url:
    raise RuntimeError(
        "NOTIFICATIONS_DATABASE_URL is missing from configuration"
    )

engine = create_engine(
    database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=5,
    connect_args={
        "connect_timeout": 5,
        "read_timeout": 5,
        "write_timeout": 5,
    },
)