import json
import logging
import threading
from collections.abc import Sequence

import pika
from fastapi import FastAPI
from sqlalchemy.engine import Engine

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from shared.messaging import (
    TELEMETRY_EXCHANGE,
    TRACE_ROUTING_KEY,
    declare_telemetry_topology,
    rabbitmq_parameters,
)


logger = logging.getLogger(__name__)

_provider: TracerProvider | None = None
_service_name: str | None = None
_instrumented_engines: set[Engine] = set()


def span_message(span: ReadableSpan) -> dict:
    """Convert a completed span into an ingestion event."""
    context = span.context

    if context is None or not context.is_valid:
        raise ValueError("Span has no valid trace context")

    trace_id = f"{context.trace_id:032x}"
    span_id = f"{context.span_id:016x}"

    parent_span_id = None
    if span.parent is not None and span.parent.is_valid:
        parent_span_id = f"{span.parent.span_id:016x}"

    service_name = str(
        span.resource.attributes.get(
            "service.name",
            "unknown-service",
        )
    )

    attributes = dict(span.attributes or {})
    correlation_id = attributes.get("correlation_id")

    if correlation_id is not None:
        correlation_id = str(correlation_id)[:64]

    # Preserve the SDK's full JSON representation, including
    # attributes, events, links, resource, and status.
    payload = json.loads(span.to_json())

    payload["start_time_unix_nano"] = span.start_time
    payload["end_time_unix_nano"] = span.end_time

    if span.start_time is not None and span.end_time is not None:
        payload["duration_ms"] = (
            span.end_time - span.start_time
        ) / 1_000_000

    return {
        # Stable across retries of the same completed span.
        "event_id": f"span-{trace_id}-{span_id}",
        "event_type": "trace",
        "service_name": service_name[:100],
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "correlation_id": correlation_id,
        "name": (span.name or "unnamed-span")[:255],
        "payload": payload,
    }


class RabbitMQSpanExporter(SpanExporter):
    """Publish completed spans from the batch worker thread."""

    def __init__(self) -> None:
        self._closed = threading.Event()

    def export(
        self,
        spans: Sequence[ReadableSpan],
    ) -> SpanExportResult:
        if self._closed.is_set():
            return SpanExportResult.FAILURE

        if not spans:
            return SpanExportResult.SUCCESS

        try:
            messages = []

            for span in spans:
                message = span_message(span)
                body = json.dumps(
                    message,
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode("utf-8")

                messages.append((message["event_id"], body))

        except (TypeError, ValueError, OverflowError):
            logger.exception("Unable to serialize telemetry batch")
            return SpanExportResult.FAILURE

        next_message = 0

        # Retry once if connection or publishing fails.
        # Already confirmed messages are not sent again.
        for attempt in range(2):
            if self._closed.is_set():
                return SpanExportResult.FAILURE

            connection = None

            try:
                parameters = rabbitmq_parameters()
                parameters.connection_attempts = 1
                parameters.stack_timeout = 10

                # Create, use, and close the connection in this
                # export call. It is never shared across threads.
                connection = pika.BlockingConnection(parameters)
                channel = connection.channel()

                declare_telemetry_topology(channel)
                channel.confirm_delivery()

                while next_message < len(messages):
                    event_id, body = messages[next_message]

                    channel.basic_publish(
                        exchange=TELEMETRY_EXCHANGE,
                        routing_key=TRACE_ROUTING_KEY,
                        body=body,
                        properties=pika.BasicProperties(
                            content_type="application/json",
                            content_encoding="utf-8",
                            delivery_mode=2,
                            message_id=event_id,
                            type="trace",
                        ),
                        mandatory=True,
                    )

                    next_message += 1

                return SpanExportResult.SUCCESS

            except (pika.exceptions.AMQPError, OSError) as exc:
                logger.warning(
                    "Telemetry publish attempt %s failed (%s)",
                    attempt + 1,
                    type(exc).__name__,
                )

            except Exception:
                logger.exception(
                    "Unexpected telemetry exporter failure"
                )
                return SpanExportResult.FAILURE

            finally:
                if connection is not None and connection.is_open:
                    try:
                        connection.close()
                    except (pika.exceptions.AMQPError, OSError):
                        logger.warning(
                            "Unable to close telemetry connection cleanly"
                        )

            if attempt == 0:
                self._closed.wait(1)

        logger.error(
            "Telemetry export failed: %s spans were not confirmed",
            len(messages) - next_message,
        )
        return SpanExportResult.FAILURE

    def shutdown(self) -> None:
        self._closed.set()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        # Buffering is handled by BatchSpanProcessor.
        return True


def configure_tracing(service_name: str) -> TracerProvider:
    """Configure one tracing provider per service process."""
    global _provider, _service_name

    if _provider is not None:
        if _service_name != service_name:
            raise RuntimeError(
                "Run each service in its own process."
            )
        return _provider

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "distributed-observability",
            "service.version": "1.0.0",
        }
    )

    provider = TracerProvider(resource=resource)

    provider.add_span_processor(
        BatchSpanProcessor(
            RabbitMQSpanExporter(),
            schedule_delay_millis=1000,
            max_queue_size=2048,
            max_export_batch_size=64,
        )
    )

    trace.set_tracer_provider(provider)

    _provider = provider
    _service_name = service_name

    return provider


def instrument_service(
    app: FastAPI,
    service_name: str,
    engine: Engine,
) -> TracerProvider:
    """Call after creating the FastAPI app, before it starts."""
    provider = configure_tracing(service_name)

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls=(
            r".*/docs(?:\?.*)?$,"
            r".*/redoc(?:\?.*)?$,"
            r".*/openapi\.json(?:\?.*)?$,"
            r".*/health(?:\?.*)?$,"
            r".*/ready(?:\?.*)?$"
        ),
    )

    httpx_instrumentor = HTTPXClientInstrumentor()

    if not httpx_instrumentor.is_instrumented_by_opentelemetry:
        httpx_instrumentor.instrument(
            tracer_provider=provider,
        )

    if engine not in _instrumented_engines:
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=provider,
        )
        _instrumented_engines.add(engine)

    return provider


def get_current_trace_id() -> str | None:
    """Return the active trace ID as 32 hexadecimal characters."""
    span_context = trace.get_current_span().get_span_context()

    if not span_context.is_valid:
        return None

    return f"{span_context.trace_id:032x}"


def shutdown_tracing() -> None:
    """Export queued spans and stop the tracing provider."""
    if _provider is not None:
        _provider.shutdown()