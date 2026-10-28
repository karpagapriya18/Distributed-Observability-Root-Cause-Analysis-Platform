
from uuid import uuid4

from sqlalchemy.orm import Session

from services.trace_processor.database import engine
from services.trace_processor.models import Trace, TraceSpan


def main():
    trace_id = uuid4().hex

    with Session(engine) as session:
        trace = Trace(
            trace_id=trace_id,
            service_name="order",
            status="PROCESSED",
        )
        session.add(trace)

        spans = [
            TraceSpan(
                trace_id=trace_id,
                span_id="order-span",
                parent_span_id=None,
                service_name="order",
                name="create-order",
                duration_ms=1800,
                status="OK",
            ),
            TraceSpan(
                trace_id=trace_id,
                span_id="payment-span",
                parent_span_id="order-span",
                service_name="payment",
                name="process-payment",
                duration_ms=1500,
                status="OK",
            ),
            TraceSpan(
                trace_id=trace_id,
                span_id="notification-span",
                parent_span_id="payment-span",
                service_name="notification",
                name="send-notification",
                duration_ms=100,
                status="OK",
            ),
        ]

        session.add_all(spans)
        session.commit()

    print("SUCCESS: Dependency test trace created!")
    print("Trace ID:", trace_id)
    print("Connections: order -> payment -> notification")


if __name__ == "__main__":
    main()
