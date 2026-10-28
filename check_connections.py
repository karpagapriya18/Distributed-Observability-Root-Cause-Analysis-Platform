
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


# Load environment variables from project root
PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=True)


DATABASES = {
    "INGESTION": "INGESTION_DATABASE_URL",
    "TRACES": "TRACES_DATABASE_URL",
    "LOGS": "LOGS_DATABASE_URL",
    "METRICS": "METRICS_DATABASE_URL",
    "DIAGNOSTICS": "DIAGNOSTICS_DATABASE_URL",
    "ORDERS": "ORDERS_DATABASE_URL",
    "PAYMENTS": "PAYMENTS_DATABASE_URL",
    "NOTIFICATIONS": "NOTIFICATIONS_DATABASE_URL",
}


def check_connection(name, env_key):
    database_url = os.getenv(env_key)

    if not database_url:
        print(f"FAIL: {name} - {env_key} is missing")
        return False

    engine = None

    try:
        url = make_url(database_url)

        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={
                "connect_timeout": 5,
                "read_timeout": 5,
                "write_timeout": 5,
            },
        )

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        print(f"PASS: {name} -> {url.database}")
        return True

    except SQLAlchemyError as error:
        original_error = getattr(error, "orig", None)

        if original_error and hasattr(original_error, "args"):
            error_code = original_error.args[0]

            if error_code == 1045:
                print(f"FAIL: {name} - MySQL code 1045 (Access denied)")
            elif error_code == 1049:
                print(f"FAIL: {name} - MySQL code 1049 (Unknown database)")
            elif error_code == 2003:
                print(f"FAIL: {name} - MySQL code 2003 (Connection failed)")
            else:
                print(f"FAIL: {name} - Database error code {error_code}")
        else:
            print(f"FAIL: {name} - {type(error).__name__}")

        return False

    except Exception as error:
        print(f"FAIL: {name} - {type(error).__name__}")
        return False

    finally:
        if engine is not None:
            engine.dispose()


def main():
    print("=" * 55)
    print("DISTRIBUTED OBSERVABILITY - DATABASE CHECK")
    print("=" * 55)

    passed = 0

    for name, env_key in DATABASES.items():
        if check_connection(name, env_key):
            passed += 1

    total = len(DATABASES)

    print("-" * 55)
    print(f"Result: {passed}/{total} database connections passed.")

    if passed == total:
        print("SUCCESS: All database connections are working!")
    else:
        print("WARNING: Some database connections need attention.")

    print("=" * 55)


if __name__ == "__main__":
    main()
