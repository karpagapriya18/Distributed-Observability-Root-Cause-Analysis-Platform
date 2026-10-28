
from sqlalchemy import select
from sqlalchemy.orm import Session

from services.metrics.models import MetricAggregate, MetricSample


def save_metric(
    db: Session,
    service_name: str,
    metric_name: str,
    value: float,
):
    """Save a metric sample and update its aggregate."""

    sample = MetricSample(
        service_name=service_name,
        metric_name=metric_name,
        value=value,
    )
    db.add(sample)

    aggregate = db.execute(
        select(MetricAggregate).where(
            MetricAggregate.service_name == service_name,
            MetricAggregate.metric_name == metric_name,
        ).with_for_update()
    ).scalar_one_or_none()

    if aggregate is None:
        aggregate = MetricAggregate(
            service_name=service_name,
            metric_name=metric_name,
            sample_count=1,
            average_value=value,
            minimum_value=value,
            maximum_value=value,
        )
        db.add(aggregate)
    else:
        count = aggregate.sample_count
        aggregate.average_value = (
            (aggregate.average_value * count) + value
        ) / (count + 1)
        aggregate.sample_count = count + 1
        aggregate.minimum_value = min(aggregate.minimum_value, value)
        aggregate.maximum_value = max(aggregate.maximum_value, value)

    db.commit()
    return sample
