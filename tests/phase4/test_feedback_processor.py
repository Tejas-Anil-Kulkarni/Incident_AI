from hindsight_memory.models import Incident
from learning.feedback_processor import FeedbackSubmission, verified_incident


def test_verified_feedback_preserves_and_labels_suspected_cause():
    incident = Incident(
        id="phase4-incident",
        service="payments-api",
        error="connection timeout",
        suspected_cause="Possible database pool saturation",
    )
    feedback = FeedbackSubmission(
        verified_cause="unclosed sessions exhausted the database pool",
        suspected_cause="Possible database pool saturation",
        steps_taken=["Fix session cleanup"],
        outcome="resolved",
        notes="Confirmed by connection-pool metrics",
    )
    updated = verified_incident(incident, feedback)
    assert updated.suspected_cause == "Possible database pool saturation"
    assert updated.verified_cause == "unclosed sessions exhausted the database pool"
    assert updated.outcome == "resolved"
    assert updated.engineer_notes == "Confirmed by connection-pool metrics"
    assert "engineer_verified" in updated.tags
