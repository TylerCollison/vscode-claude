---
name: scotty-beads-ui
description: Use when configuring or enabling Scotty (Beads web UI) in the container — covers environment variables, startup requirements, stealth mode, and troubleshooting.
---

# Scotty (Beads Web UI) Configuration Skill

## Overview
Scotty is a standalone Next.js web UI for the Beads issue tracker (bead-me-up-scotty). It provides a five-column kanban board (Backlog · Ready · In Progress · Blocked · Done) with drag-and-drop, epics with progress bars, dependency graph, comments, and create/edit. It shells out to the `bd` CLI as the single source of truth.

## When to Use
- Enabling the Beads web UI in a container
- Configuring Scotty environment variables
- Troubleshooting Scotty startup issues
- Setting up Scotty with Beads stealth mode

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_SCOTTY` | *(not set)* | **Required.** Set to `true` to start Scotty on container startup |
| `SCOTTY_PORT` | `3000` | Port the Scotty web UI listens on |
| `BEADS_ENABLED` | *(not set)* | Set to `true` to auto-initialize Beads (`bd init`) — required for Scotty to have a database |
| `BEADS_DIR` | *(not set)* | Enables stealth mode: stores Beads database at this path (outside workspace) |
| `DEFAULT_WORKSPACE` | `/workspace` | Workspace directory containing the `.beads` database |

## Prerequisites

1. **Beads must be initialized** — Scotty shells out to `bd`, so a Beads database must exist. Either:
   - Set `BEADS_ENABLED=true` (auto-runs `bd init` on startup), OR
   - Run `bd init` manually in the workspace before enabling Scotty

2. **The `bd` CLI must be on PATH** — Installed at `/usr/local/bin/bd` in the container. Without it, Scotty runs in demo mode.

3. **Port availability** — Default port 3000 must be free (or configure `SCOTTY_PORT`).

## Quick Start

```yaml
environment:
  - ENABLE_SCOTTY=true
  - SCOTTY_PORT=3000        # Optional
  - BEADS_ENABLED=true      # Required for database
```

Then access at `http://localhost:3000` (or configured port).

## Stealth Mode (BEADS_DIR)

When `BEADS_DIR` is set, Beads runs in stealth mode — the database lives at `$BEADS_DIR` (e.g., `/config/.beads` for persistence) instead of `.beads/` in the workspace. Scotty handles this automatically:

1. On startup, `start-scotty.sh` creates a symlink: `$DEFAULT_WORKSPACE/.beads` → `$BEADS_DIR`
2. Scotty's project check looks for `.beads` in the workspace path
3. The `bd` CLI still resolves the database via the exported `BEADS_DIR` environment variable
4. Git excludes keep the symlink and database out of the repo

```yaml
environment:
  - ENABLE_SCOTTY=true
  - BEADS_ENABLED=true
  - BEADS_DIR=/config/.beads
volumes:
  - /path/to/beads-data:/config/.beads
```

## Startup Script Behavior (`start-scotty.sh`)

The script at `/workspace/start-scotty.sh` (run by container init):

1. **Checks `ENABLE_SCOTTY`** — exits 0 if not `true`
2. **Verifies Scotty exists** — expects `/opt/bead-me-up-scotty/server.js`
3. **Warns if `bd` missing** — runs in demo mode without it
4. **Prevents duplicate starts** — checks PID file at `/var/run/scotty.pid`
5. **Fixes permissions** — chowns Beads data dir to `abc:abc` for the UI user
6. **Handles stealth mode** — creates workspace `.beads` symlink if `BEADS_DIR` set
7. **Ensures config dir** — creates `/config/.config` for Scotty's project registry
8. **Starts server as `abc` user** — via `setpriv` with `HOME=/config`, `BEADS_REPO=$DEFAULT_WORKSPACE`
9. **Waits for port** — polls up to 30s for TCP listen on `SCOTTY_PORT`
10. **Logs success** — outputs ready URL

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Scotty not enabled" | `ENABLE_SCOTTY` not `true` | Set `ENABLE_SCOTTY=true` |
| "Scotty not found at /opt/bead-me-up-scotty" | Image built without Scotty | Rebuild image with Scotty included |
| "bd not found — demo mode" | `bd` CLI not installed | Ensure image has `bd` at `/usr/local/bin/bd` |
| "Scotty failed to start after 30s" | Port conflict or server crash | Check `/tmp/scotty.log`; verify port free |
| Empty project list | No Beads database | Run `bd init` or set `BEADS_ENABLED=true` |
| Stealth mode not working | Symlink missing or perms | Verify `BEADS_DIR` set; check `/config/.beads` mount |

## Architecture Notes

- **Runs as `abc` user** — Non-root for security; needs read/write to Beads DB and config dir
- **Single-threaded Node.js** — One process handles all requests; not for high concurrency
- **Shells out to `bd`** — Every UI action invokes the CLI; latency depends on `bd` performance
- **Project registry** — Stored in `/config/.config/bead-me-up-scotty/` per workspace
- **No authentication** — Relies on container network isolation; add reverse proxy auth for exposure

## Common Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Forgetting `BEADS_ENABLED=true` | No database → empty UI | Enable Beads or run `bd init` first |
| Using `BEADS_DIR` without volume mount | Data lost on restart | Mount volume at `BEADS_DIR` path |
| Port 3000 already in use | Startup timeout | Change `SCOTTY_PORT` or free port 3000 |
| Running as root instead of `abc` | Permission errors on DB | Script handles this via `setpriv` — don't override |

## Related Skills
- `beads-setup` — For Beads initialization and configuration (if created)
- `beads-dispatch` — For auto-provisioning workers (if created)

## Example: Full docker-compose

```yaml
services:
  claude-dev:
    image: tylercollison2089/vscode-claude
    environment:
      - ENABLE_SCOTTY=true
      - SCOTTY_PORT=3000
      - BEADS_ENABLED=true
      - BEADS_DIR=/config/.beads
      - DEFAULT_WORKSPACE=/workspace
    volumes:
      - ./workspace:/workspace
      - ./beads-data:/config/.beads
    ports:
      - "8443:8443"   # VS Code
      - "3000:3000"   # Scotty
```

## Verification Checklist

After enabling Scotty, verify:
- [ ] Container logs show "Scotty (Beads UI) is ready at http://localhost:3000"
- [ ] `curl http://localhost:3000` returns HTML (not connection refused)
- [ ] UI shows the workspace as a project
- [ ] Creating an issue in UI appears in `bd list`
- [ ] `bd list` issues appear in UI after refresh