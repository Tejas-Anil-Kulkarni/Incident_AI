"""Deterministic category and severity assignment for incidents."""

import re
from typing import Literal

from pydantic import BaseModel

Category = Literal["Database", "API", "Overload", "Network", "Deployment", "Performance"]
Severity = Literal["critical", "high", "medium", "low", "unknown"]


class Classification(BaseModel):
    category: Category
    severity: Severity


RULES: tuple[tuple[Category, tuple[str, ...]], ...] = (
    ("Database", (r"\bdatabase\b", r"\bpostgres(?:ql)?\b", r"\bmysql\b", r"sqlalchemy", r"connection pool", r"deadlock", r"query timeout")),
    ("Deployment", (r"\bdeploy(?:ment|ed)?\b", r"\brelease\b", r"rollback", r"migration failed", r"new version", r"image pull")),
    ("Network", (r"\bdns\b", r"name resolution", r"connection reset", r"connection refused", r"network unreachable", r"tls handshake")),
    ("Overload", (r"cpu (?:usage )?(?:over )?\d{2,3}%", r"\bhigh cpu\b", r"queue (?:backlog|saturated)", r"out of memory", r"oomkilled", r"worker saturation")),
    ("Performance", (r"latency", r"slow response", r"slow request", r"p\d{2,3}", r"throughput", r"taking \d+(?:\.\d+)? ?(?:ms|s)")),
    ("API", (r"\bhttp(?:/\d(?:\.\d)?)?\b", r"\b[45]\d\d\b", r"upstream", r"endpoint", r"request failed", r"gateway")),
)


def classify_incident(
    *, text: str, cpu_percent: float | None = None, failed_requests: int = 0, status: str | None = None
) -> Classification:
    haystack = text.lower()
    category: Category = "API"
    for candidate, patterns in RULES:
        if any(re.search(pattern, haystack, re.I) for pattern in patterns):
            category = candidate
            break
    status_text = (status or "").lower()
    if cpu_percent is not None and cpu_percent >= 98 or status_text in {"down", "critical", "unavailable"}:
        severity: Severity = "critical"
    elif cpu_percent is not None and cpu_percent >= 85 or failed_requests >= 20 or status_text in {"unhealthy", "degraded", "error"}:
        severity = "high"
    elif cpu_percent is not None and cpu_percent >= 70 or failed_requests > 0 or status_text in {"warning", "partial"}:
        severity = "medium"
    elif status_text in {"ok", "healthy", "resolved"}:
        severity = "low"
    else:
        severity = "unknown"
    return Classification(category=category, severity=severity)
