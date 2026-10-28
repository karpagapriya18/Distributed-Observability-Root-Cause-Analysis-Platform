
import json
import logging
import math
import os
import time
from pathlib import Path

import pika
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.metrics.database import engine
from services.metrics.models import (
    MetricAggregate,
    MetricSample,
    MetricAlert,
)
from services.metrics.alerts import evaluate_metric
from shared.messaging import METRIC_QUEUE, declare_telemetry_topology, rabbitmq_parameters, bounded_retry


# Load environment variables
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("metrics_consumer")

QUEUE_NAME = METRIC_QUEUE


def save_metric(event: dict) -> None:
    """Save metric, update aggregate, and generate alert."""

    if not isinstance(event, dict):
        raise ValueError("Metric event must be a JSON object")

    service_name = event.get("service_name")
    metric_name = event.get("metric_name")
    raw_value = event.get("value")

    if not service_name or not metric_name or raw_value is None:
        raise ValueError("Missing required metric fields")

    service_name = str(service_name)
    metric_name = str(metric_name)

    try:
        value = float(raw_value)
    except (ValueError, TypeError) as exc:
        raise ValueError("Metric value must be numeric") from exc

    if not math.isfinite(value):
        raise ValueError("Metric value must be finite")

    # Evaluate the metric before saving.
    alert = evaluate_metric(
        service_name,
        metric_name,
        value,
    )

    # Save metric, aggregate, and alert together.
    with Session(engine) as session:
        with session.begin():

            sample = MetricSample(
                event_id=str(event.get("event_id") or event.get("id") or f"{service_name}:{metric_name}:{event.get('timestamp', 'missing')}:{value}"),
                service_name=service_name,
                metric_name=metric_name,
                value=value,
            )
            session.add(sample)

            aggregate = session.scalar(
                select(MetricAggregate)
                .where(
                    MetricAggregate.service_name == service_name,
                    MetricAggregate.metric_name == metric_name,
                )
                .with_for_update()
            )

            if aggregate is None:
                aggregate = MetricAggregate(
                    service_name=service_name,
                    metric_name=metric_name,
                    sample_count=1,
                    average_value=value,
                    minimum_value=value,
                    maximum_value=value,
                )
                session.add(aggregate)

            else:
                old_count = aggregate.sample_count
                new_count = old_count + 1

                aggregate.average_value = (
                    aggregate.average_value * old_count + value
                ) / new_count

                aggregate.sample_count = new_count

                aggregate.minimum_value = min(
                    aggregate.minimum_value,
                    value,
                )

                aggregate.maximum_value = max(
                    aggregate.maximum_value,
                    value,
                )

            # Automatically save threshold alerts.
            if alert is not None:
                active_alert = session.scalar(
                    select(MetricAlert).where(
                        MetricAlert.service_name == service_name,
                        MetricAlert.metric_name == metric_name,
                        MetricAlert.status == "ACTIVE",
                    ).with_for_update()
                )
                if active_alert is None:
                    session.add(MetricAlert(
                        service_name=alert.service_name,
                        metric_name=alert.metric_name,
                        severity=alert.severity,
                        message=alert.message,
                        value=alert.value,
                        threshold=alert.threshold,
                        status="ACTIVE",
                        occurrence_count=1,
                    ))
                else:
                    active_alert.value = alert.value
                    active_alert.severity = alert.severity
                    active_alert.occurrence_count += 1
                    active_alert.last_seen_at = __import__("datetime").datetime.utcnow()

    logger.info(
        "Saved metric: %s / %s = %s",
        service_name,
        metric_name,
        value,
    )

    if alert is not None:
        logger.warning(
            "METRIC ALERT SAVED: %s / %s = %s (%s)",
            service_name,
            metric_name,
            value,
            alert.severity,
        )


def on_message(channel, method, properties, body):
    """Process RabbitMQ metric events."""

    try:
        event = json.loads(body.decode("utf-8"))

        save_metric(event)

        channel.basic_ack(
            delivery_tag=method.delivery_tag
        )

        logger.info("Metric event processed successfully")

    except IntegrityError:
        logger.info("Duplicate metric event ignored")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    except (ValueError, TypeError, KeyError) as exc:
        logger.error("Invalid metric event: %s", exc)

        channel.basic_reject(
            delivery_tag=method.delivery_tag,
            requeue=False,
        )

    except Exception:
        logger.exception("Failed to process metric event")

        bounded_retry(channel, method, properties, body, getattr(method, "routing_key", "telemetry.metric.raw"))


def main():
    """Connect to RabbitMQ and consume metric events."""

    parameters = rabbitmq_parameters()

    while True:
        connection = None

        try:
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()

            declare_telemetry_topology(channel)

            channel.basic_qos(prefetch_count=1)

            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=on_message,
                auto_ack=False,
            )

            logger.info(
                "Metrics consumer waiting for events on %s...",
                QUEUE_NAME,
            )

            channel.start_consuming()

        except KeyboardInterrupt:
            logger.info("Metrics consumer stopped")
            break

        except Exception:
            logger.exception(
                "Consumer stopped; retrying in 5 seconds"
            )
            time.sleep(5)

        finally:
            if connection is not None and connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
