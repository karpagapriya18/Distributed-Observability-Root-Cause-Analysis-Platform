
import json
import uuid
from datetime import datetime, timedelta, timezone

import pika

from shared.messaging import (
    TRACE_QUEUE,
    declare_telemetry_topology,
    rabbitmq_parameters,
)


def main():
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]

    start = datetime.now(timezone.utc)
    end = start + timedelta(milliseconds=1500)

    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "trace",
        "service_name": "payment",
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": None,
        "correlation_id": str(uuid.uuid4()),
        "name": "payment-processing",
        "payload": {
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "status": "OK",
        },
    }

    connection = pika.BlockingConnection(
        rabbitmq_parameters()
    )

    try:
        channel = connection.channel()
        declare_telemetry_topology(channel)

        channel.basic_publish(
            exchange="",
            routing_key=TRACE_QUEUE,
            body=json.dumps(event).encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
        )

        print("SUCCESS: Trace event published!")
        print("Trace ID:", trace_id)
        print("Queue:", TRACE_QUEUE)

    finally:
        connection.close()


if __name__ == "__main__":
    main()
