
import json
import os
import uuid
from pathlib import Path

import pika
from dotenv import load_dotenv

# Load environment variables from the project root
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

QUEUE_NAME = "telemetry.metrics"


def main():
    username = os.getenv("RABBITMQ_DEFAULT_USER")
    password = os.getenv("RABBITMQ_DEFAULT_PASS")
    host = os.getenv("RABBITMQ_HOST", "127.0.0.1")
    port = int(os.getenv("RABBITMQ_PORT", "25672"))

    if not username or not password:
        raise RuntimeError(
            "RabbitMQ credentials are missing from .env"
        )

    credentials = pika.PlainCredentials(
        username,
        password,
    )

    parameters = pika.ConnectionParameters(
        host=host,
        port=port,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=30,
    )

    event = {
        "event_id": str(uuid.uuid4()),
        "service_name": "payment",
        "metric_name": "response_time_ms",
        "value": 1500.0,
    }

    connection = pika.BlockingConnection(parameters)

    try:
        channel = connection.channel()

        # Ensure the queue exists
        channel.queue_declare(
            queue=QUEUE_NAME,
            durable=True,
        )

        # Publish the metric event
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=json.dumps(event).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
            mandatory=True,
        )

        print("SUCCESS: Test metric event published!")
        print("Event ID:", event["event_id"])
        print("Queue:", QUEUE_NAME)
        print("Service:", event["service_name"])
        print("Metric:", event["metric_name"])
        print("Value:", event["value"])

    finally:
        if connection.is_open:
            connection.close()


if __name__ == "__main__":
    main()
