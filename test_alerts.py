
from services.metrics.alerts import evaluate_metric


def test_high_latency_generates_warning():
    alert = evaluate_metric(
        "payment", "response_time_ms", 1500.0
    )

    assert alert is not None
    assert alert.severity == "WARNING"
    assert alert.threshold == 1000.0


def test_normal_latency_generates_no_alert():
    alert = evaluate_metric(
        "payment", "response_time_ms", 250.0
    )

    assert alert is None


def test_critical_latency():
    alert = evaluate_metric(
        "payment", "response_time_ms", 2500.0
    )

    assert alert is not None
    assert alert.severity == "CRITICAL"
