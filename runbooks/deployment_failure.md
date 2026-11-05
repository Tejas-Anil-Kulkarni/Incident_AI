# Deployment failure runbook

Use these checks to guide an engineer. IncidentMind does not execute recovery steps.

## Recommended checks

- Identify the deployment, image, configuration, or migration change that preceded the incident.
- Compare the deployed version and health checks with the previous known-good release.
- Review migration compatibility and readiness probes before considering a rollback.
- Follow the service owner's approved rollback procedure and verify recovery.
