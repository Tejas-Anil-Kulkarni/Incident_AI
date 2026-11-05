"""Noise normalization and lightweight structure extraction for service logs."""

import re
from collections import Counter
from datetime import datetime

from pydantic import BaseModel, Field

UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}\b")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HEX_ID_RE = re.compile(r"\b[0-9a-fA-F]{16,}\b")
KEYED_ID_RE = re.compile(r"\b(request[_-]?id|trace[_-]?id|user[_-]?id|order[_-]?id|id)\s*[:=]\s*[\w-]+", re.I)
PATH_ID_RE = re.compile(r"(?<=/)\d{3,}(?=/|\b)")
TIMESTAMP_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b")
STACK_FRAME_RE = re.compile(r"^\s*(?:File \"[^\"]+\", line \d+.*|at\s+[\w.$<>]+.*)\s*$")


class LogAnalysis(BaseModel):
    signature: str
    top_stack_frames: list[str] = Field(default_factory=list)
    repeated_patterns: list[str] = Field(default_factory=list)
    timestamps: list[datetime] = Field(default_factory=list)


def normalize_log_line(line: str) -> str:
    """Replace volatile identifiers while preserving technical error wording."""

    normalized = UUID_RE.sub("<UUID>", line)
    normalized = IP_RE.sub("<IP>", normalized)
    normalized = HEX_ID_RE.sub("<ID>", normalized)
    normalized = KEYED_ID_RE.sub(lambda match: f"{match.group(1).lower()}=<ID>", normalized)
    normalized = PATH_ID_RE.sub("<ID>", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def analyze_logs(logs: str | None) -> LogAnalysis:
    """Extract a stable signature, stack frames, repeated lines and timestamps."""

    if not logs:
        return LogAnalysis(signature="")
    lines = [line for line in logs.splitlines() if line.strip()]
    normalized = [normalize_log_line(line) for line in lines]
    counts = Counter(normalized)
    signature = next((line[:500] for line in normalized if line), "")
    frames: list[str] = []
    for line in lines:
        if STACK_FRAME_RE.match(line) and line.strip() not in frames:
            frames.append(line.strip()[:500])
        if len(frames) == 3:
            break
    repeats = [line[:500] for line, count in counts.most_common() if count > 1][:10]
    timestamps: list[datetime] = []
    for match in TIMESTAMP_RE.findall(logs):
        try:
            value = match.replace("Z", "+00:00")
            timestamps.append(datetime.fromisoformat(value))
        except ValueError:
            continue
    return LogAnalysis(signature=signature, top_stack_frames=frames, repeated_patterns=repeats, timestamps=timestamps)
