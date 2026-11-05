# Public contracts

This document is the compatibility ledger for IncidentMind AI. Public
interfaces introduced in a completed phase are never broken; later phases may
extend them only additively.

## Phase 0

### `GET /health`

- Returns HTTP `200`.
- JSON shape: `{"status": "ok", "timestamp": "<ISO-8601 UTC datetime>"}`.
- This endpoint performs no network access and does not require integration
  credentials, so it remains safe for liveness probes.

### Configuration

`config.settings.Settings` loads `HINDSIGHT_API_KEY`, `HINDSIGHT_BASE_URL`,
`GROQ_API_KEY`, and `MODEL_NAME` from the environment or `.env`. Optional
`HINDSIGHT_BANK_ID` selects the memory bank and defaults to `incidentmind`.
It raises a
clear Pydantic validation error when any required value is absent.

## Phase 1 — Hindsight memory

- `Incident` is the validated incident-memory payload, with a stable string ID and explicit outcome enum.
- `MemoryStore.retain_incident(incident)` returns `RetainResult`; service errors are represented without leaking secrets.
- `MemoryStore.recall_similar(query, k)` returns `list[MemoryEvidence]`, including the exact raw Hindsight text and optional source chunk when the official Recall API provides it.
- `MemoryStore.reflect(question)` returns `ReflectResult` with answer text and any available raw evidence.
- `FakeMemory` implements the same async interface for unit tests only; production construction always selects the official Hindsight client.
- `python -m hindsight_memory.demo` runs a retain-then-recall example against configured Hindsight.
- `GET /health` remains unchanged from Phase 0.

## Phase 2 — Incident ingestion and log analysis

- `POST /incidents` accepts an alert with `service` and optional `error`, `cpu_percent`, `failed_requests`, `status`, `logs`, and `occurred_at`; it returns a Phase 1 `Incident` with additive category, signature, and extracted stack frames.
- `GET /incidents/{incident_id}` returns the persisted Phase 1-compatible `Incident`, or HTTP `404` when the ID is unknown.
- Alert validation uses Pydantic; invalid fields return FastAPI's standard HTTP `422` response.
- Incident records are stored in SQLite through SQLAlchemy. `DATABASE_URL` may override the default `sqlite:///./data/incidents.sqlite3`.
- Log signatures normalize UUIDs, IP addresses, long hex identifiers, keyed IDs, and numeric path IDs so equivalent messages can be matched.
- The Phase 1 `MemoryStore` methods and `/health` response remain unchanged; Phase 2 incidents remain valid inputs to `retain_incident`.

## Phase 3 — Grounded analysis and runbooks

- `POST /incidents/{incident_id}/analyze` is additive and returns an `AnalysisResponse` containing validated hypotheses, recommended steps, a runbook reference, recalled evidence, and explicit cold-start/fallback status.
- Each hypothesis is marked `suspected`; only IDs from recalled evidence are retained as citations. Unrecalled IDs are removed and reported in `warnings`.
- A cold start returns the exact notice `No relevant experience found in memory.` with runbook-only recommendations and does not ask the LLM to invent historical context.
- Groq responses are parsed into a Pydantic `AnalysisDraft`; malformed or tool-call-shaped output receives one repair attempt, then deterministic runbook-only fallback.
- Groq calls use a timeout and bounded transient-error retries. Hindsight errors preserve the route with an explicit unavailable-memory response.
- Categories map to Markdown files in `runbooks/`; successful steps are merged only from recalled incidents whose stored outcome is `resolved`.
- Recommendations require engineer review and are never executed by this route. `/health`, `/incidents`, `/incidents/{id}`, and Phase 1 memory interfaces are unchanged.

## Phase 4 — Engineer feedback and learning

- `POST /incidents/{incident_id}/feedback` records a verified cause, steps taken, outcome, notes, and optional idempotency key; exact duplicate submissions do not retain another memory.
- Feedback sets `verified_cause` and `outcome` while preserving `suspected_cause`; the verified incident is retained through the Phase 1 `MemoryStore` when available.
- Failed feedback returns a warning and appears as a warning in later analysis when recalled. Resolved historical steps are surfaced before generic recommendations when evidence supports them.
- `GET /stats/outcomes` returns outcome, category, and verified-cause counts from stored feedback. Resolution labels use count text such as `2 of 3 recorded`; no percentages or success rates are synthesized.
- `POST /incidents/{incident_id}/approve-action` records an engineer's approval for an exact action ID and description. `POST /incidents/{incident_id}/execute-action` rejects unapproved actions and only writes a simulation log; `executed` is always `false`.
- Phase 0–3 routes, schemas, memory interfaces, and contracts remain compatible.

## Phase 5 — Memory innovation

- `POST /innovation/replay` accepts an ordered list of 1–50 stored incident IDs and evaluates that same sequence with memory disabled and with isolated Hindsight memory. It reports per-incident citations, matching verified cause, position to verified fix when measurable, and chart-ready metrics; unverified truth remains `null` rather than being scored.
- Replay analysis masks the current incident's verified cause, outcome, resolution steps, and notes before making recommendations, preventing label leakage. Each replay has a unique Hindsight bank ID returned in the response.
- `POST /incidents/{incident_id}/analyze?innovation_enabled=true` adds structured anti-runbook warnings from recalled engineer feedback. A warning is issued only when a relevant attempted step has recorded failure evidence; it includes the failed/attempted count, incident IDs, and available failure context. Default analysis remains compatible.
- `POST /innovation/insights` accepts a question and optional `refresh`. It calls the Phase 1 Hindsight Reflect interface, stores answers in SQLite for five minutes, and returns the source and cache timestamp. When Reflect is unavailable or unsuccessful, the endpoint returns an explicitly labeled SQLite fallback grounded in engineer feedback.
- `reflect_insight_cache` is created with the application database tables. Cached fallback answers are timestamped and cached as well.
- Phase 0–4 routes and response fields remain compatible; Phase 5 adds routes and opt-in fields only.

## Phase 6 — Dashboard

- `GET /incidents?limit=50&offset=0` is a read-only newest-first feed returning incident payloads with optional feedback outcome and open/verified status. `limit` is bounded from 1 to 200.
- `GET /stats/memory` returns `feedback_records` and `retained_in_hindsight`, counted from persisted engineer feedback and successful Hindsight Retain responses; it is not a live bank inventory.
- The Streamlit dashboard calls only FastAPI through `frontend.api_client.IncidentMindApi`; it does not connect to Hindsight. `INCIDENTMIND_API_URL` may set the backend base URL; default is `http://127.0.0.1:8000`.
- The UI adds Incident Feed and Detail, suspected-cause and evidence panels, engineer feedback, Anti-Runbook warnings, Replay Lab comparisons/chart, outcome summaries, and confirmed-retain counts. API failure and empty states are rendered in the UI.
- Phase 0–5 contracts are unchanged. Phase 6's backend additions are read-only.

## Phase 7 — Stretch features

- `CHAOS_DOJO_ENABLED`, `STALENESS_ENABLED`, and `DEPLOY_RISK_ENABLED` default to `false`. Phase 7 routes return HTTP `404` while their corresponding feature is disabled.
- `POST /innovation/chaos-dojo` accepts a demo service and a bounded fault type. It creates a clearly synthetic incident, runs normal analysis, applies a scripted verified resolution, and retains it through the configured Hindsight MemoryStore. The incident and retained memory carry the `synthetic=true` tag; the dashboard displays these rows separately.
- Synthetic feedback is excluded from `GET /stats/outcomes` totals and groupings. Real incident counts and existing statistics retain their Phase 4 behavior.
- `GET /stats/memory/origins` returns separate feedback and confirmed-retain counts for real and synthetic incidents; the Phase 6 `/stats/memory` response remains unchanged.
- `GET /incidents/{incident_id}/staleness` compares verified incidents for the same service and matching signature/symptoms. Contradictions return both incident IDs, both causes, timestamps, and `possibly outdated` status; neither memory is deleted or hidden. Synthetic incidents are not conflict sources.
- `POST /innovation/deploy-risk` recalls change-related evidence through Hindsight. It separates historical and synthetic evidence and reports no probability or deploy/no-deploy decision. Unavailable memory returns an explicit empty result.
- All Phase 0–6 contracts remain compatible; all Phase 7 capabilities are additive and default off.

## Phase 8 — Hardening and submission

- Alert logs are validated up to 200,000 characters; `Incident.logs_excerpt` remains bounded to 50,000 characters. Unicode input is preserved.
- Groq rate-limit responses (HTTP 429) use bounded retries with backoff; exhausted calls follow the existing deterministic runbook fallback.
- `HINDSIGHT_BANK_ID` is optional and defaults to `incidentmind`, preserving the earlier default. It allows an isolated demo bank without removing existing memory.
- `Dockerfile` builds the API image; `docker-compose.yml` runs API and dashboard with a persistent SQLite volume. Container deployment requires a configured `.env` file and reachable Hindsight/Groq services for integration features.
- `DEMO_SCRIPT.md` documents an eight-step recording flow. Full unit, API, dashboard, and prior-phase contract tests remain part of `pytest -q`.
- The final release tag is `v1.0`; the phase tag `phase-8` points to the same release commit.

