# IncidentMind AI — 60-second recording script

Use a dedicated, empty Hindsight bank for the recording. This avoids deleting
or changing existing memory. Copy `.env.example` to `.env`, configure the
Hindsight and Groq credentials, then set `HINDSIGHT_BANK_ID=incidentmind-demo`
and `DATABASE_URL=sqlite:///./data/incidentmind-demo.sqlite3` before starting
the app. The master build prompt was the only demo guide found
in the provided project; these eight beats follow its requested empty-memory,
verified-feedback, retrieval, replay, and safety story.

## 1. Start with an empty memory (0–6 sec)

**Say:** “IncidentMind starts with no relevant memory. Recommendations are
runbook-based until an engineer verifies a real outcome.”

**Show:** Run the API and dashboard in separate terminals; open the empty
dedicated bank's Incident Feed.

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
.\.venv\Scripts\python.exe -m streamlit run frontend/dashboard.py
```

## 2. Submit the first incident (6–13 sec)

**Say:** “A payment API is degraded because its database pool is exhausted.”

**Show/run:**

```powershell
$base = 'http://127.0.0.1:8000'
$first = Invoke-RestMethod -Method Post -Uri "$base/incidents" -ContentType 'application/json' -Body '{"service":"payments-api","error":"database connection pool exhausted","status":"degraded","logs":"Timeout waiting for a database connection from the pool"}'
Invoke-RestMethod -Method Post -Uri "$base/incidents/$($first.id)/analyze" | ConvertTo-Json -Depth 8
```

## 3. Resolve and verify it (13–21 sec)

**Say:** “The engineer confirms sessions were leaking and records the fix.”

**Show/run:**

```powershell
$firstFeedback = @{ verified_cause = 'unclosed sessions exhausted the connection pool'; steps_taken = @('Close sessions in the request finally block'); outcome = 'resolved'; notes = 'Verified by the on-call engineer' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/incidents/$($first.id)/feedback" -ContentType 'application/json' -Body $firstFeedback | ConvertTo-Json
```

## 4. Show retained memory (21–27 sec)

**Say:** “That verified incident is retained in Hindsight; the dashboard counts
confirmed retains separately from synthetic examples.”

**Show:** Open Learning & Memory and the Incident Detail feedback panel.

## 5. Demonstrate evidence-based analysis (27–36 sec)

**Say:** “A similar timeout arrives. The agent can now cite the previous
incident and surface its verified fix as historical evidence.”

**Show/run:**

```powershell
$second = Invoke-RestMethod -Method Post -Uri "$base/incidents" -ContentType 'application/json' -Body '{"service":"payments-api","error":"payment requests timing out waiting for database pool connections","status":"degraded","logs":"sqlalchemy pool timeout while acquiring connection"}'
Invoke-RestMethod -Method Post -Uri "$base/incidents/$($second.id)/analyze?innovation_enabled=true" | ConvertTo-Json -Depth 10
```

Expand Memory Evidence in the dashboard and point to the prior incident ID.

## 6. Record a failed attempt and surface the warning (36–44 sec)

**Say:** “Failed fixes stay in memory too, so engineers can see what failed
before repeating it.”

**Show/run:**

```powershell
$third = Invoke-RestMethod -Method Post -Uri "$base/incidents" -ContentType 'application/json' -Body '{"service":"payments-api","error":"database pool acquisition timeout","status":"degraded","logs":"pool exhausted waiting for connection"}'
$failedFeedback = @{ verified_cause = 'connection pool saturation'; steps_taken = @('Increase connection timeout'); outcome = 'failed'; notes = 'Longer timeout increased request latency without restoring pool capacity' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/incidents/$($third.id)/feedback" -ContentType 'application/json' -Body $failedFeedback | ConvertTo-Json
$fourth = Invoke-RestMethod -Method Post -Uri "$base/incidents" -ContentType 'application/json' -Body '{"service":"payments-api","error":"database pool acquisition timeout persists","status":"degraded","logs":"pool exhausted acquiring connection"}'
Invoke-RestMethod -Method Post -Uri "$base/incidents/$($fourth.id)/analyze?innovation_enabled=true" | ConvertTo-Json -Depth 10
```

The Anti-Runbook warning reports only stored failure cases.

## 7. Compare the learning curve (44–53 sec)

**Say:** “Replay Lab runs the same ordered incidents with memory off and on.
These are observed results, not a promised improvement score.”

**Show/run:** Give the second incident its engineer verification, then replay
the first two in the same order:

```powershell
$secondFeedback = @{ verified_cause = 'unclosed sessions exhausted the connection pool'; steps_taken = @('Close sessions in the request finally block'); outcome = 'resolved'; notes = 'Confirmed after cleanup' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/incidents/$($second.id)/feedback" -ContentType 'application/json' -Body $secondFeedback | Out-Null
$replay = @{ incident_ids = @($first.id, $second.id) } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/innovation/replay" -ContentType 'application/json' -Body $replay | ConvertTo-Json -Depth 12
```

Show citations, steps to verified fix, and the chart in the Replay Lab tab.

## 8. Close on safety and honest counts (53–60 sec)

**Say:** “Causes stay suspected until an engineer verifies them. Actions are
never executed, and synthetic scenarios are visibly separate from production
history.”

**Show:** The suspected/verified labels, separate synthetic feed, recorded
outcome counts, and approval-gated simulation contract. Do not execute an
operational recovery action during the recording.

```powershell
Invoke-RestMethod -Method Get -Uri "$base/stats/outcomes" | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Get -Uri "$base/stats/memory/origins" | ConvertTo-Json
```

## Recording notes

- Use only an authorized test service and synthetic-looking incident details.
- A fresh `HINDSIGHT_BANK_ID` provides an empty demo bank without deleting data.
- Live Reflect, Recall, Retain, Groq analysis, and Replay require configured
  external services. If they are unavailable, show the labeled fallback instead
  of implying that a memory result was retrieved.
- Do not call the API output a success rate or treat a recommendation as an
  executed recovery.
