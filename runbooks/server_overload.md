# Server overload runbook

Use these checks to guide an engineer. IncidentMind does not execute recovery steps.

## Recommended checks

- Check CPU, memory, queue depth, and worker utilization on affected hosts.
- Identify recent traffic or workload changes and inspect autoscaling events.
- Consider reducing optional workload or scaling capacity after validating impact.
- Monitor error rates and resource headroom after any approved change.
