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

