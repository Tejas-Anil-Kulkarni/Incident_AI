# Phase 6 dashboard manual checklist

Run the API in one terminal and the dashboard in another:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
.\.venv\Scripts\python.exe -m streamlit run frontend/dashboard.py
```

Screenshots to capture during the demo:

1. Incident feed showing service, severity, category, outcome status, and timestamp.
2. Incident detail with suspected cause badge/wording, runbook recommendations, and expanded Hindsight evidence showing relevance.
3. Engineer feedback form before submit and the retained-in-Hindsight confirmation after submit.
4. Replay Lab with both memory-disabled and memory-enabled step metrics and chart-ready result JSON.
5. Learning & memory counters with locally recorded feedback and confirmed Retain counts.

Check the empty feed, API unavailable message, an incident with no recalled evidence, a failed-fix Anti-Runbook warning, and a replay containing at least two feedback-labeled incidents. Confirm no dashboard interaction executes a recovery action.
