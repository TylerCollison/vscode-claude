---
name: claude-conx-shutdown
description: Gracefully shuts down the container with Happier machine revocation and s6-overlay cleanup. Use when the user asks to shut down, stop, or power off the container, or when a task requires clean container termination.
license: Proprietary
compatibility: Requires s6-overlay init system, optional Happier server connectivity for machine revocation
metadata:
  author: claude-conx
  version: "1.0"
  command: /workspace/shutdown.sh
---

# Shutdown Skill

## When to Use This Skill

Use this skill when:
- The user asks to "shut down", "stop", "power off", or "terminate" the container
- A task completes and requires clean container shutdown
- You need to gracefully stop the container with proper cleanup
- The user mentions "shutdown command" or references `/workspace/shutdown.sh`

Do NOT use this skill for:
- Restarting services within the container (use service management instead)
- Suspending or pausing the container
- Force-killing processes without graceful shutdown

## Command

**Location:** `/workspace/shutdown.sh`

**Usage:**
```bash
/workspace/shutdown.sh
```

The script is executable and self-contained. Run it directly to initiate the shutdown sequence.

## Shutdown Sequence

The shutdown script performs the following steps in order:

### 1. Happier Machine Revocation (if HAPPIER_MODE is set)

If `HAPPIER_MODE` environment variable is set, the script:
- Determines the Happier server URL based on mode:
  - `HAPPIER_MODE=server` → `HAPPIER_SERVER_URL` (default: `https://localhost:3005`)
  - Other modes → `HAPPIER_SERVER_URL` (default: `http://happier-server:3006`)
- Locates the access key at `/config/.happier/servers/<server_id>/access.key`
- Reads the machine ID from `/config/.happier/settings.json`
- Sends a `POST /v1/machines/<machine_id>/revoke` request to the Happier server
- This marks the machine as `active=false` and sets `revokedAt` timestamp

**Note:** The Happier daemon is intentionally left running so other sessions/tools on the machine keep working.

### 2. Graceful Container Shutdown via s6-overlay

- Sends `SIGTERM` to PID 1 (the s6-overlay init process)
- Waits 2 seconds for graceful shutdown
- If container is still running, sends `SIGKILL` to PID 1 as a last resort

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HAPPIER_MODE` | No | If set, triggers Happier machine revocation. Values: `server`, `client`, or any truthy value |
| `HAPPIER_SERVER_URL` | No | Override the Happier server URL. Defaults depend on `HAPPIER_MODE` |

## Prerequisites

- Container must be running with s6-overlay as PID 1 (standard for this environment)
- For Happier cleanup: `HAPPIER_MODE` must be set and Happier server must be accessible
- Access key must exist at `/config/.happier/servers/<server_id>/access.key`
- Machine ID must be registered in `/config/.happier/settings.json`

## Troubleshooting

### Container Doesn't Stop

If the container doesn't stop after running the shutdown script:

1. **Check s6-overlay processes:**
   ```bash
   ps aux | grep s6
   ```
   Look for the s6-svscan process (PID 1) and any supervised services.

2. **Check if SIGTERM was received:**
   ```bash
   # The script logs to stdout; check container logs
   docker logs <container_name>
   ```

3. **Force kill if needed:**
   The script attempts `SIGKILL` after 2 seconds, but if that fails:
   ```bash
   kill -KILL 1
   ```

### Happier Revocation Fails

Common issues and resolutions:

| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 200/204 | Success | Machine revoked successfully |
| 404 | Not found | Machine already removed from server |
| 401 | Unauthorized | Access token expired; re-authenticate with Happier |
| Other | Server error | Check server logs; verify network connectivity |

If no access key is found:
- Verify `HAPPIER_SERVER_URL` is correct
- Check that `/config/.happier/servers/` contains the server directory
- Run Happier authentication flow to generate access key

If no machine ID is found:
- Check `/config/.happier/settings.json` for `machineIdByServerId` or `machineIdByServerIdByAccountId`
- The machine may not have been registered yet

### Permission Denied

If the script fails with permission errors:
- Ensure the script is executable: `chmod +x /workspace/shutdown.sh`
- The script runs as root in the container, so file permissions should not be an issue

## Cross-Harness Notes

This skill works with any harness that:
- Runs the container with s6-overlay as the init system (PID 1)
- Provides the `/workspace/shutdown.sh` script
- Sets `HAPPIER_MODE` and `HAPPIER_SERVER_URL` environment variables when Happier integration is desired

The shutdown mechanism is harness-agnostic because it:
1. Uses standard POSIX signals (SIGTERM, SIGKILL)
2. Targets PID 1 (the init process) which is universal
3. Uses standard HTTP API for Happier revocation
4. Does not depend on any harness-specific APIs

## Examples

### Basic Shutdown
```bash
/workspace/shutdown.sh
```

### Shutdown with Happier Cleanup (Server Mode)
```bash
HAPPIER_MODE=server HAPPIER_SERVER_URL=https://my-happier-server:3005 /workspace/shutdown.sh
```

### Shutdown with Happier Cleanup (Client Mode)
```bash
HAPPIER_MODE=client HAPPIER_SERVER_URL=http://happier-server:3006 /workspace/shutdown.sh
```

## Expected Output

Successful shutdown produces logs like:
```
[SHUTDOWN] HAPPIER_MODE is set (server), cleaning up Happier machine...
[SHUTDOWN] Server URL: https://my-happier-server:3005
[SHUTDOWN] Found access key at /config/.happier/servers/env_xxx/access.key
[SHUTDOWN] Found machine ID: abc123
[SHUTDOWN] Revoking machine abc123 from Happier server...
[SHUTDOWN] Successfully revoked machine abc123 from Happier server
[SHUTDOWN] Shutting down container...
[SHUTDOWN] Shutdown complete
```

Without Happier mode:
```
[SHUTDOWN] HAPPIER_MODE not set, skipping Happier cleanup
[SHUTDOWN] Shutting down container...
[SHUTDOWN] Shutdown complete
```

## References

- [shutdown.sh script](../shutdown.sh) — The actual shutdown script (relative to workspace root)
- Happier API documentation — For machine revocation endpoint details
- s6-overlay documentation — For understanding the init system shutdown behavior