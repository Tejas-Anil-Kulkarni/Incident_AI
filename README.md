# IncidentMind AI

IncidentMind AI is an incident-response assistant that recommends (but never
executes) recovery actions. Its persistent learning layer will use official
[Hindsight](https://github.com/vectorize-io/hindsight) memory banks to retain
incident outcomes, recall relevant evidence, and reflect on recurring patterns.

## Current status

**Phase 0 complete:** the FastAPI skeleton, structured logs, environment
configuration, health check, and pytest harness are available. Memory,
incident ingestion, and dashboard features are deliberately deferred until
their respective gated phases.

## 10-line implementation plan

1. Establish a tested FastAPI/configuration baseline and record public contracts.
2. Add a thin, typed official Hindsight client wrapper and a test-only fake.
3. Parse alerts/logs into normalized, persisted incident records.
4. Recall Hindsight evidence and produce validated, grounded RCA recommendations.
5. Capture engineer verification and retain real outcomes for future learning.
6. Add Replay Lab to compare recommendations with and without memory.
7. Surface failed fixes through anti-runbook warnings and use Hindsight Reflect insights.
8. Build a Streamlit UI that calls only the FastAPI backend.
9. Add opt-in synthetic chaos, staleness/conflict, and deploy-risk features.
10. Harden, document, containerize, test from a fresh clone, and tag `v1.0`.

## Hindsight verification and intended integration

Before implementation, the official documentation and repository source were
inspected, including the Python client implementation and its operation tests.
The verified Python package is
`hindsight-client`; its client class is `hindsight_client.Hindsight`. The
repository’s implementation is in
`hindsight-clients/python/hindsight_client/hindsight_client.py`, with behavioral
tests in `hindsight-clients/python/tests/`, notably `test_main_operations.py`,
`test_async_sync_parity.py`, and the Retain/Recall/Reflect option tests.

Phase 1 installs that official package and adapts its documented `Hindsight`
client. The current client source exposes `create_bank`, `retain`, `recall`,
and `reflect` as synchronous convenience methods; the application runs these
calls in worker threads so FastAPI's event loop remains responsive. The wrapper
adapts official response models to IncidentMind typed evidence results; it does
not implement vector search, fact extraction, graph retrieval, or reflection.
Hindsight remains the only memory layer.

## Hindsight assumptions to verify in Phase 1

- The installed `hindsight-client` version matches the documented client API.
- Cloud authentication accepts `api_key` as the documented bearer token.
- The configured Hindsight endpoint supports bank creation and the `incidentmind` bank ID.
- `create_bank` is idempotent enough for create-or-retrieve behavior, or the
  official bank-list/get API must be used first.
- Retain response, Recall `results`, and Reflect response/citation fields match
  the installed SDK models used by our typed adapter.
- Service-side timeout/retry semantics do not conflict with the wrapper’s
  bounded retries and fallback behavior.

## Setup and Phase 0 demo

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Fill in the required values before using Hindsight or Groq features.
uvicorn main:app --reload
```

Visit `http://127.0.0.1:8000/health`. Phase 0’s endpoint works even before
credentials are populated. Run tests with:

```powershell
pytest
```

## Phase 1 memory demo

With a Hindsight service reachable at `HINDSIGHT_BASE_URL` and its API key in
`.env`, run `python -m hindsight_memory.demo` to retain an incident and recall
similar evidence. To load the bundled, explicitly synthetic sample incidents,
run `python -m hindsight_memory.seed`. Unit tests use `FakeMemory`; production
code always constructs `HindsightMemory` with the official SDK.

## BAND Desktop (hackathon collaboration requirement)

Band Desktop (formerly Jam) is installed separately from this Python app. The
official Windows x64 installer is linked in Band’s
[installation guide](https://docs.band.ai/band-desktop/install). Run it, sign
in to a Band account, enable the locally installed Codex runtime in the setup
wizard, then verify with `band daemon status` and `band doctor`. It is used for
agent collaboration and auditable development workflow; it is **not** part of
IncidentMind’s runtime, memory system, or production data path.

## Safety and limitations

- Recommendations require explicit engineer approval before any simulated or
  logged action in later phases; IncidentMind never executes recovery actions.
- Secrets belong only in environment variables. `.env` is ignored by Git.
- No Hindsight or Groq credentials are available in this workspace, so Phase 0
  cannot verify a live integration. That verification is a Phase 1 integration
  gate when credentials are supplied.

