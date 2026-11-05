"""Incident serialization for Hindsight Retain."""

import json

from hindsight_memory.models import Incident


def incident_content(incident: Incident) -> str:
    """Produce a human-readable, evidence-preserving document for Hindsight."""

    data = incident.model_dump(mode="json", exclude_none=True)
    return "IncidentMind incident record:\n" + json.dumps(data, ensure_ascii=False, sort_keys=True)
