"""Honest count summaries derived only from recorded engineer feedback."""

from collections import Counter, defaultdict
from typing import Literal

from pydantic import BaseModel, Field

Outcome = Literal["resolved", "failed", "partial"]


class FeedbackEntry(BaseModel):
    incident_id: str
    category: str | None = None
    verified_cause: str
    outcome: Outcome
    synthetic: bool = False


class CategoryOutcomeStats(BaseModel):
    category: str
    recorded: int
    resolved: int
    failed: int
    partial: int


class ResolutionOutcomeStats(BaseModel):
    verified_cause: str
    recorded: int
    resolved: int
    failed: int
    partial: int
    display: str


class OutcomeStatsResponse(BaseModel):
    total_recorded: int
    outcomes: dict[str, int]
    by_category: list[CategoryOutcomeStats] = Field(default_factory=list)
    by_resolution: list[ResolutionOutcomeStats] = Field(default_factory=list)


def compute_outcome_stats(entries: list[FeedbackEntry]) -> OutcomeStatsResponse:
    entries = [entry for entry in entries if not entry.synthetic]
    outcomes: Counter[str] = Counter(entry.outcome for entry in entries)
    categories: dict[str, Counter[str]] = defaultdict(Counter)
    resolutions: dict[str, Counter[str]] = defaultdict(Counter)
    for entry in entries:
        categories[entry.category or "Unknown"][entry.outcome] += 1
        cause = entry.verified_cause.strip()
        if cause:
            resolutions[cause][entry.outcome] += 1
    return OutcomeStatsResponse(
        total_recorded=len(entries),
        outcomes={outcome: outcomes.get(outcome, 0) for outcome in ("resolved", "failed", "partial")},
        by_category=[
            CategoryOutcomeStats(
                category=category,
                recorded=sum(counts.values()),
                resolved=counts.get("resolved", 0),
                failed=counts.get("failed", 0),
                partial=counts.get("partial", 0),
            )
            for category, counts in sorted(categories.items())
        ],
        by_resolution=[
            ResolutionOutcomeStats(
                verified_cause=cause,
                recorded=sum(counts.values()),
                resolved=counts.get("resolved", 0),
                failed=counts.get("failed", 0),
                partial=counts.get("partial", 0),
                display=f"{counts.get('resolved', 0)} of {sum(counts.values())} recorded",
            )
            for cause, counts in sorted(resolutions.items())
        ],
    )
