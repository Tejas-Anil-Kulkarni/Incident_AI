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
`GROQ_API_KEY`, and `MODEL_NAME` from the environment or `.env`. It raises a
clear Pydantic validation error when any required value is absent.

## Phase 1 — Hindsight memory

- `Incident` is the validated incident-memory payload, with a stable string ID and explicit outcome enum.
- `MemoryStore.retain_incident(incident)` returns `RetainResult`; service errors are represented without leaking secrets.
- `MemoryStore.recall_similar(query, k)` returns `list[MemoryEvidence]`, including the exact raw Hindsight text.
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

