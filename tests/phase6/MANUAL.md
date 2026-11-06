# Phase 6 dashboard manual checklist

Run FastAPI and Vite in separate terminals for development:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
pnpm --dir frontend install
pnpm --dir frontend dev
```

Open `http://127.0.0.1:5173`. Vite proxies API calls to FastAPI. For a
production-style check, run `pnpm --dir frontend build` and then open
`http://127.0.0.1:8000`; FastAPI serves `frontend/dist` when it exists.

Screenshots to capture during the demo:

1. Incident register showing service, severity, category, outcome status, and date.
2. Incident detail with suspected cause badge/wording, runbook recommendations, and expanded Hindsight evidence showing relevance.
3. Engineer feedback form before submit and the retained-in-Hindsight confirmation after submit.
4. Replay Lab with both memory-disabled and memory-enabled step metrics and chart-ready result JSON.
5. Learning & memory counters with real/synthetic records, outcomes, and a Reflect insight.

Check the empty feed, API unavailable message, an incident with no recalled evidence, a failed-fix Anti-Runbook warning, and a replay containing at least two feedback-labeled incidents. Confirm no dashboard interaction executes a recovery action.
