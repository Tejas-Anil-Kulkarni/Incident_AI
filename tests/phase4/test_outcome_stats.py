from learning.outcome_stats import FeedbackEntry, compute_outcome_stats


def test_stats_show_actual_counts_without_percentages():
    entries = [
        FeedbackEntry(incident_id="1", category="Database", verified_cause="session leak", outcome="resolved"),
        FeedbackEntry(incident_id="2", category="Database", verified_cause="session leak", outcome="resolved"),
        FeedbackEntry(incident_id="3", category="Database", verified_cause="session leak", outcome="failed"),
    ]
    result = compute_outcome_stats(entries)
    resolution = result.by_resolution[0]
    assert result.total_recorded == 3
    assert result.outcomes == {"resolved": 2, "failed": 1, "partial": 0}
    assert resolution.display == "2 of 3 recorded"
    assert not hasattr(resolution, "success_rate")


def test_empty_stats_have_zero_counts():
    result = compute_outcome_stats([])
    assert result.total_recorded == 0
    assert result.by_category == []
    assert result.by_resolution == []
