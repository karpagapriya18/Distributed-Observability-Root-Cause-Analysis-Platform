
import json
import os
from uuid import uuid4

import pika
from dotenv import load_dotenv

load_dotenv()

credentials = pika.PlainCredentials(
    os.getenv("RABBITMQ_DEFAULT_USER"),
    os.getenv("RABBITMQ_DEFAULT_PASS"),
)

connection = pika.BlockingConnection(
    pika.ConnectionParameters(
        host="127.0.0.1",
        port=25672,
        credentials=credentials,
    )
)

channel = connection.channel()

event = {
    "event_id": str(uuid4()),
    "service_name": "payment",
    "trace_id": "a" * 32,
    "severity": "ERROR",
    "message": "Test payment failure",
    "attributes": {"test": True},
}

channel.basic_publish(
    exchange="telemetry",
    routing_key="logs.test",
    body=json.dumps(event).encode("utf-8"),
)

print("TEST LOG EVENT PUBLISHED:", event["event_id"])

connection.close()
