from dataclasses import dataclass
import json
import os
from datetime import datetime, timezone


@dataclass
class Alert:
    service_name: str
    metric_name: str
    severity: str
    message: str
    value: float
    threshold: float
    created_at: str


DEFAULT_THRESHOLDS = {"response_time_ms": 1000.0, "latency_ms": 1000.0, "error_rate": 5.0, "request_rate": 1000.0}
def configured_thresholds() -> dict[str, float]:
    raw = os.getenv("METRIC_THRESHOLDS_JSON", "")
    if not raw: return DEFAULT_THRESHOLDS
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict): raise ValueError("threshold config must be an object")
        return {str(key): float(value) for key, value in parsed.items() if isinstance(value, (int, float)) and float(value) >= 0}
    except (ValueError, TypeError, json.JSONDecodeError):
        return DEFAULT_THRESHOLDS



def evaluate_metric(
    service_name: str,
    metric_name: str,
    value: float,
) -> Alert | None:

    threshold = configured_thresholds().get(metric_name)

    if threshold is None:
        return None

    if value <= threshold:
        return None

    severity = (
        "CRITICAL"
        if value >= threshold * 2
        else "WARNING"
    )

    return Alert(
        service_name=service_name,
        metric_name=metric_name,
        severity=severity,
        message=(
            f"{service_name}: {metric_name} "
            f"exceeded threshold"
        ),
        value=value,
        threshold=threshold,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
