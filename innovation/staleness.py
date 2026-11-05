"""Explicitly flag older verified memory when newer evidence conflicts."""

import re
import unicodedata
from datetime import datetime

from pydantic import BaseModel, Field

from hindsight_memory.models import Incident


class MemoryConflict(BaseModel):
    service: str
    older_incident_id: str
    older_verified_cause: str
    older_created_at: datetime
    newer_incident_id: str
    newer_verified_cause: str
    newer_created_at: datetime
    status: str = "possibly outdated"


class StalenessResponse(BaseModel):
    conflicts: list[MemoryConflict] = Field(default_factory=list)
    message: str


def find_staleness_conflicts(
    incidents: list[Incident], verified_causes: dict[str, str]
) -> StalenessResponse:
    conflicts: list[MemoryConflict] = []
    ordered = sorted(incidents, key=lambda item: (item.created_at, item.id))
    for index, older in enumerate(ordered):
        older_cause = verified_causes.get(older.id)
        if not older_cause or _is_synthetic(older):
            continue
        for newer in ordered[index + 1:]:
            newer_cause = verified_causes.get(newer.id)
            if not newer_cause or _is_synthetic(newer):
                continue
            if older.service.casefold() != newer.service.casefold():
                continue
            if _normalize(older_cause) == _normalize(newer_cause):
                continue
            if not _same_symptoms(older, newer):
                continue
            conflicts.append(MemoryConflict(
                service=older.service,
                older_incident_id=older.id,
                older_verified_cause=older_cause,
                older_created_at=older.created_at,
                newer_incident_id=newer.id,
                newer_verified_cause=newer_cause,
                newer_created_at=newer.created_at,
            ))
    if conflicts:
        return StalenessResponse(
            conflicts=conflicts,
            message="Older verified memories may be outdated; both versions are shown for engineer review.",
        )
    return StalenessResponse(conflicts=[], message="No conflicting verified incident memories were found.")


def _same_symptoms(left: Incident, right: Incident) -> bool:
    if left.signature and right.signature and left.signature == right.signature:
        return True
    left_terms = _terms(" ".join([left.error, *left.symptoms]))
    right_terms = _terms(" ".join([right.error, *right.symptoms]))
    return bool(left_terms and right_terms and len(left_terms & right_terms) / len(left_terms | right_terms) >= 0.5)


def _is_synthetic(incident: Incident) -> bool:
    return "synthetic=true" in incident.tags


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _terms(value: str) -> set[str]:
    return set(re.findall(r"[\w]+", _normalize(value)))
