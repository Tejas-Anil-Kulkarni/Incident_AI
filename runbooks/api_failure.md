# API failure runbook

Use these checks to guide an engineer. IncidentMind does not execute recovery steps.

## Recommended checks

- Check endpoint error rates, upstream health, and recent deployment changes.
- Compare response latency and status codes across affected routes.
- Verify dependency timeouts and retry behavior before changing limits.
- If a recent release is implicated, review the rollback plan with the service owner.
