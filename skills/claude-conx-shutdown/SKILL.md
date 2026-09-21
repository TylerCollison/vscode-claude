---
name: claude-conx-shutdown
description: Use when you need to gracefully shut down the ClaudeConX container with proper cleanup of Happier machine registration, running processes, and resources. Trigger when the user asks to stop the container, shut down gracefully, or run the shutdown command.
---

# shutdown (ClaudeConX)

Gracefully shut down the container with proper Happier cleanup, process termination, and resource release.

## When to Use

- Container shutdown requested by user or orchestration system
- Before container restart or replacement
- When cleaning up Happier machine registration
- Graceful termination of all managed processes

## Command

```bash
shutdown
```

**Location:** `/workspace/shutdown.sh` (also available as `/usr/local/bin/shutdown` in container)

## Cleanup Sequence

The shutdown script executes in this order:

1. **Happier Machine Revocation** (if `HAPPIER_MODE` is set)
   - Connects to Happier server at `HAPPIER_SERVER_URL`
   - Revokes this machine's registration
   - Removes machine from server's machine list
   - Waits for confirmation (timeout: 10s)

2. **SIGTERM to PID 1** (s6-overlay init)
   - Sends SIGTERM to the init process
   - s6-overlay propagates to all supervised services
   - Services get 30s grace period for clean shutdown

3. **Force Kill** (if needed)
   - After 30s, sends SIGKILL to remaining processes
   - Ensures container exits

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `HAPPIER_MODE` | Set to `agent` or `server` to enable Happier cleanup | No (optional) |
| `HAPPIER_SERVER_URL` | URL of Happier relay server | Yes if `HAPPIER_MODE` set |
| `HAPPIER_ACCESS_KEY` | Auth key for server communication | Yes if `HAPPIER_MODE` set |

## Usage

### Basic Shutdown

```bash
shutdown
```

### With Happier Cleanup

```bash
HAPPIER_MODE=agent HAPPIER_SERVER_URL=https://happier.example.com HAPPIER_ACCESS_KEY='{"key":"..."}' shutdown
```

### In Container Orchestration

```dockerfile
# Dockerfile HEALTHCHECK or stop signal
STOPSIGNAL SIGTERM
# shutdown handles the rest via s6-overlay
```

## Prerequisites

- For Happier cleanup: `HAPPIER_MODE` must be set (`agent` or `server`)
- `HAPPIER_SERVER_URL` must be accessible
- Valid credentials (via `HAPPIER_ACCESS_KEY` or existing pairing)

## Output

**Success:**
```
[shutdown] Starting graceful shutdown...
[shutdown] Revoking Happier machine registration...
[shutdown] Machine revoked successfully
[shutdown] Sending SIGTERM to PID 1 (s6-overlay)...
[shutdown] Waiting for services to stop...
[shutdown] All services stopped. Exiting.
```

**Happier Not Configured:**
```
[shutdown] Starting graceful shutdown...
[shutdown] HAPPIER_MODE not set, skipping Happier cleanup
[shutdown] Sending SIGTERM to PID 1 (s6-overlay)...
...
```

**Happier Revocation Failed:**
```
[shutdown] Starting graceful shutdown...
[shutdown] Revoking Happier machine registration...
[shutdown] WARNING: Failed to revoke machine (timeout or connection error)
[shutdown] Continuing with process termination...
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Container doesn't stop | s6-overlay service stuck | Check `s6-svstat /run/service/*`; force kill after timeout |
| Happier revocation fails | Network/server down | Script continues anyway; machine auto-expires on server |
| Permission denied | Not running as root | Run with appropriate privileges (container runs as root) |
| Socket errors | Happier daemon not running | Revocation uses HTTP API, not socket; check server URL |

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load on keywords like "shutdown", "graceful shutdown", "container stop"; others require explicit `skill` tool invocation.
- **Tool mapping:** Uses generic action language:
  - "run a shell command" → executes `shutdown` script
  - "read a file" → reads Happier config, logs
  - "fetch a URL" → calls Happier REST API for machine revocation
- **No hardcoded harness list:** Works with ANY harness implementing agentskills.io spec.
- **Harness-specific caveats:**
  - This is a **container-level command** — shuts down the entire container
  - Only works inside the ClaudeConX container (uses s6-overlay)
  - Happier cleanup is optional — container shuts down even if it fails
  - The `shutdown` command is the recommended way to stop the container (vs `docker stop`)
  - Works identically across all harnesses running inside the container