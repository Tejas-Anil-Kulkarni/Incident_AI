# Performance degradation runbook

Use these checks to guide an engineer. IncidentMind does not execute recovery steps.

## Recommended checks

- Compare latency percentiles, throughput, and saturation with the normal operating range.
- Inspect traces and slow operations to identify where time is spent.
- Check dependency latency and resource contention before changing timeouts.
- Validate performance after each approved change and retain the measured outcome.
