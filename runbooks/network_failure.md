# Network failure runbook

Use these checks to guide an engineer. IncidentMind does not execute recovery steps.

## Recommended checks

- Check DNS resolution, service discovery, and network reachability from affected hosts.
- Review connection resets, TLS handshake failures, and recent network policy changes.
- Compare affected paths with a known healthy region or service instance.
- Escalate to the network owner before changing routing or firewall rules.
