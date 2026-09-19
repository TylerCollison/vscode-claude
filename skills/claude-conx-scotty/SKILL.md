---
name: claude-conx-scotty
description: Use when configuring, enabling, checking, or troubleshooting Scotty (Bead UI / bead-me-up-scotty), the web interface for the Beads issue tracker in the ClaudeConX container. Triggers include "Scotty", "Bead UI", "Beads web UI", "Beads web interface", "bead-me-up-scotty", "kanban board for Beads", "ENABLE_SCOTTY", "SCOTTY_PORT", or questions about viewing Beads issues in a browser.
---

# Scotty (Bead UI) — Web Interface for Beads

## Overview

Scotty ("Bead Me Up, Scotty", upstream: [bead-me-up-scotty](https://github.com/brendan-appstart/bead-me-up-scotty)) is the web UI for the Beads issue tracker: a **five-column kanban board** for Beads issues. It is built into the ClaudeConX container image as a standalone Next.js server at `/opt/bead-me-up-scotty` and is opt-in — it only starts when `ENABLE_SCOTTY=true`.

## Board Columns

| Column | Meaning |
|--------|---------|
| **Backlog** | Open issues not yet ready to work on |
| **Ready** | Beads' ready set — open issues with no active blockers (matches `bd ready`) |
| **In Progress** | Issues currently being worked |
| **Blocked** | Issues with active blockers |
| **Done** | Closed issues |

Columns support **drag-and-drop** (e.g. drag a card from Ready to In Progress). Note that drag-and-drop maps to Beads state changes through the same `bd` CLI the agents use — the board is a view over the shared database, not a separate store.

## Features

- Five-column kanban board (Backlog · Ready · In Progress · Blocked · Done) with drag-and-drop
- **Epics** with progress bars
- **Dependency graph** visualization (Beads' first-class dependencies)
- **Comments** on issues
- **Create/edit** issues directly from the UI

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_SCOTTY` | *(not set)* | Set to `true` to start the Beads web UI (Scotty) on container startup |
| `SCOTTY_PORT` | `3000` | Port the Scotty web UI listens on |

Related (Beads side): `BEADS_DIR` (stealth mode — see below) and `BEADS_ENABLED` / `bd init` (prerequisite — see below).

## Accessing the UI

Open **http://localhost:3000** in your browser (configurable via `SCOTTY_PORT`). The server listens on `0.0.0.0` inside the container, so publish the port in docker-compose (`"3000:3000"`) or reach it via the container network.

## Workspace Registration & Stealth Mode

- **Automatic registration:** The workspace (which contains the `.beads` database) is registered automatically as a project. Scotty's project registry lives under `/config/.config` (the app runs as the `abc` user with `HOME=/config`).
- **Stealth mode integration:** When `BEADS_DIR` is set, the database lives outside the workspace and the workspace has no `.beads` directory. Scotty only registers projects whose path contains a `.beads` directory, so `start-scotty.sh` links `/workspace/.beads` → `$BEADS_DIR` (the symlink is only for Scotty's project check) and passes `BEADS_DIR` through to `bd`, so the database is found there. The stealth git excludes keep the symlink out of the repo.

## Prerequisites

The UI reads the database via the `bd` CLI, so a Beads database must exist: set `BEADS_ENABLED=true` (handled by `configure-beads.sh` on startup) or run `bd init` yourself. If `bd` is not on PATH, the app silently falls back to **demo mode**.

## Relationship to the bd CLI

The UI shells out to the `bd` CLI (`/usr/local/bin/bd`) — **`bd` remains the single source of truth**. Anything agents do with `bd` (create, update, close, comment, …) is reflected in the UI, and changes made in the UI go through `bd` to the same database. Agents can always fall back to `bd` commands; the UI is a convenience view, not a separate store.

## Usage Example (docker-compose)

```yaml
environment:
  # Scotty — Beads web UI (optional)
  - ENABLE_SCOTTY=true
  - SCOTTY_PORT=3000 # Optional
ports:
  - "3000:3000" # Scotty (Beads UI) — only if ENABLE_SCOTTY=true
```

Then open `http://localhost:3000` in your browser. If you also set `BEADS_DIR` (stealth mode), Scotty links the workspace's `.beads` to `BEADS_DIR` and passes the variable through to `bd`, so the database is found there.

## Troubleshooting

- **Verify it's running:**
  ```bash
  docker exec claude-dev ps aux | grep server.js
  docker exec claude-dev curl -I http://localhost:3000
  ```
- **Check the startup log:** `docker exec claude-dev cat /tmp/scotty.log`
- **Not starting:** Ensure `ENABLE_SCOTTY=true` is set and the port (`SCOTTY_PORT`, default `3000`) isn't already in use
- **ERROR: "Scotty not found at /opt/bead-me-up-scotty"** — the image was built without it; rebuild the image
- **UI shows demo data** — `bd` wasn't on PATH when the server started; ensure `bd` is installed (`which bd`) and restart Scotty
- **Workspace/project not listed** — the workspace path must contain a `.beads` directory (in stealth mode `start-scotty.sh` creates the symlink; check `ls -la /workspace/.beads`)
- **Database not found / empty board** — Beads may not be initialized; run `bd init` (or set `BEADS_ENABLED=true` and restart)
- **Duplicate-server protection** — a PID file at `/var/run/scotty.pid` prevents double starts across container init re-runs; remove it (and kill the process) to force a restart

## Cross-Harness Notes

Works with **any harness in the container** (Claude Code, Happier, threads, plain CLI, …): Scotty is just a web server — no harness-specific integration is required. Agents in any harness can:

- Check status with `curl` against `http://localhost:$SCOTTY_PORT` (or read `/tmp/scotty.log`)
- Read and mutate issues via the `bd` CLI, which the UI reflects (bd is the source of truth)
- Help users enable it by setting `ENABLE_SCOTTY=true` (+ `SCOTTY_PORT`) and restarting the container
