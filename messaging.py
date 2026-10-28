import os
from pathlib import Path
import pika
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
TELEMETRY_EXCHANGE = "observability.telemetry"
TRACE_ROUTING_KEY = "telemetry.trace.raw"
LOG_ROUTING_KEY = "telemetry.log.raw"
METRIC_ROUTING_KEY = "telemetry.metric.raw"
TRACE_QUEUE = "ingestion.telemetry.traces"
RAW_QUEUE = "ingestion.telemetry.raw"
LOG_QUEUE = "log_processor.logs"
METRIC_QUEUE = "telemetry.metrics"
DEAD_LETTER_EXCHANGE = "observability.telemetry.dlx"
DEAD_LETTER_QUEUE = "ingestion.telemetry.dead"
def rabbitmq_parameters() -> pika.URLParameters:
    url = os.getenv("RABBITMQ_URL")
    if not url:
        user = os.getenv("RABBITMQ_DEFAULT_USER", "observability")
        password = os.getenv("RABBITMQ_DEFAULT_PASS", "")
        host = os.getenv("RABBITMQ_HOST", "127.0.0.1")
        port = os.getenv("RABBITMQ_INTERNAL_PORT", os.getenv("RABBITMQ_PORT", "5672"))
        if not password:
            raise RuntimeError("RABBITMQ_DEFAULT_PASS is missing")
        url = f"amqp://{user}:{password}@{host}:{port}/%2F"
    parameters = pika.URLParameters(url)
    parameters.heartbeat = 30
    parameters.blocked_connection_timeout = 10
    parameters.socket_timeout = 5
    parameters.connection_attempts = 3
    parameters.retry_delay = 1
    return parameters
def declare_telemetry_topology(channel) -> None:
    channel.exchange_declare(exchange=TELEMETRY_EXCHANGE, exchange_type="topic", durable=True)
    channel.exchange_declare(exchange=DEAD_LETTER_EXCHANGE, exchange_type="fanout", durable=True)
    channel.queue_declare(queue=DEAD_LETTER_QUEUE, durable=True)
    channel.queue_bind(queue=DEAD_LETTER_QUEUE, exchange=DEAD_LETTER_EXCHANGE)
    for queue, routing_key in ((RAW_QUEUE, "telemetry.*.raw"), (TRACE_QUEUE, TRACE_ROUTING_KEY), (LOG_QUEUE, LOG_ROUTING_KEY), (METRIC_QUEUE, METRIC_ROUTING_KEY)):
        channel.queue_declare(queue=queue, durable=True, arguments={"x-dead-letter-exchange": DEAD_LETTER_EXCHANGE})
        channel.queue_bind(queue=queue, exchange=TELEMETRY_EXCHANGE, routing_key=routing_key)


def bounded_retry(channel, method, properties, body: bytes, routing_key: str | None, max_retries: int = 3) -> None:
    """Republish transient failures with a bounded retry counter; then dead-letter."""
    headers = dict(getattr(properties, "headers", None) or {})
    retries = int(headers.get("x-retry-count", 0))
    if retries >= max_retries:
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        return
    headers["x-retry-count"] = retries + 1
    try:
        channel.basic_publish(
            exchange=TELEMETRY_EXCHANGE,
            routing_key=routing_key or TRACE_ROUTING_KEY,
            body=body,
            properties=pika.BasicProperties(
                content_type=getattr(properties, "content_type", None) or "application/json",
                delivery_mode=2,
                message_id=getattr(properties, "message_id", None),
                type=getattr(properties, "type", None),
                headers=headers,
            ),
            mandatory=True,
        )
        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception:
        # If republishing fails, leave the original delivery available for redelivery.
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
