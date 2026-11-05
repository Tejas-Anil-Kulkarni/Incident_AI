import pytest
from pydantic import ValidationError

from incident_processing.incident_classifier import classify_incident
from incident_processing.incident_detector import AlertPayload, detect_incident
from incident_processing.log_analyzer import analyze_logs, normalize_log_line


@pytest.mark.parametrize(
    ("logs", "expected"),
    [
        ("sqlalchemy.exc.TimeoutError: database connection pool exhausted", "Database"),
        ("HTTP 502 gateway error: upstream endpoint failed", "API"),
        ("High CPU 99%, worker saturation and queue backlog", "Overload"),
        ("DNS name resolution failed; connection reset by peer", "Network"),
        ("Deployment release failed during migration; rollback started", "Deployment"),
        ("P95 latency increased; slow response taking 4200ms", "Performance"),
    ],
)
def test_classifies_all_six_incident_categories(logs, expected):
    assert classify_incident(text=logs).category == expected


def test_normalization_matches_logs_with_different_identifiers_and_addresses():
    first = "GET /users/123?user_id=111 from 10.1.2.3 trace_id=abcdef0123456789"
    second = "GET /users/456?user_id=222 from 10.9.8.7 trace_id=0123456789abcdef"
    assert normalize_log_line(first) == normalize_log_line(second)
    assert analyze_logs(first).signature == analyze_logs(second).signature


def test_log_analysis_extracts_frames_repeats_and_timestamps():
    logs = """2026-11-05T12:30:00Z ERROR database timeout
File \"app/db.py\", line 42, in connect
ERROR database timeout
ERROR database timeout"""
    parsed = analyze_logs(logs)
    assert parsed.signature.startswith("2026-11-05T12:30:00Z")
    assert parsed.top_stack_frames == ['File "app/db.py", line 42, in connect']
    assert parsed.repeated_patterns == ["ERROR database timeout"]
    assert parsed.timestamps[0].year == 2026


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"status": "down"}, "critical"),
        ({"cpu_percent": 90}, "high"),
        ({"failed_requests": 1}, "medium"),
        ({"status": "healthy"}, "low"),
    ],
)
def test_severity_is_determined_from_alert_signals(kwargs, expected):
    assert classify_incident(text="API error", **kwargs).severity == expected


def test_malformed_alert_is_rejected():
    with pytest.raises(ValidationError):
        AlertPayload.model_validate({"service": "", "cpu_percent": 150})


def test_malformed_log_text_does_not_crash_detection():
    incident = detect_incident({"service": "test-service", "logs": "\x00☃\n\n???"})
    assert incident.service == "test-service"
    assert incident.logs_excerpt == "\x00☃\n\n???"
