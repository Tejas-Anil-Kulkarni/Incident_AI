# Database failure runbook

Use these checks to guide an engineer. IncidentMind does not execute recovery steps.

## Recommended checks

- Check database health, connection-pool saturation, and current connection counts.
- Review recent database errors and the top application stack frames.
- Confirm session and transaction cleanup paths before restarting workers.
- If saturation is verified, consider a controlled worker restart and monitor recovery.
