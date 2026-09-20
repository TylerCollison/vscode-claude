---
name: claude-conx-dispatch-beads
description: Use when you need to manually trigger the Beads Dispatch daemon to check for ready tasks and spawn worker containers without committing code. Trigger when the user asks to dispatch ready tasks, trigger Beads Dispatch manually, or run the dispatch-beads command.
---

# dispatch-beads (ClaudeConX)

Manually trigger the Beads Dispatch daemon to check for ready tasks and spawn worker containers without requiring a git commit.

## When to Use

- After running `bd update` or `bd create` to make tasks ready
- When you want to dispatch workers without committing
- During development/testing of Beads Dispatch workflows
- When the post-commit hook hasn't fired but tasks are ready

## Command

```bash
dispatch-beads
```

**Location:** `/workspace/dispatch-beads` (symlinked to `/usr/local/bin/dispatch-beads` in container)

## How It Works

1. Reads `BEADS_DISPATCH_SOCKET_PATH` environment variable (default: `/run/beads-dispatch/trigger.sock`)
2. Connects to the Unix domain socket
3. Sends a "manual" trigger message to the Beads Dispatch daemon
4. Daemon wakes up, checks for ready tasks, spawns workers
5. Returns success/failure with log location

## Prerequisites

- **Beads Dispatch daemon must be running** with `BEADS_DISPATCH=true`
- **Unix socket** must exist at `BEADS_DISPATCH_SOCKET_PATH`
- **Database** must be initialized (`bd init`)

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BEADS_DISPATCH_SOCKET_PATH` | Path to Unix socket for trigger | `/run/beads-dispatch/trigger.sock` |

## Output

**Success:**
```
Trigger sent to Beads Dispatch daemon
Check logs at: /var/log/beads-dispatch.log
```

**Failure (daemon not running):**
```
Error: Could not connect to socket /run/beads-dispatch/trigger.sock
Is the Beads Dispatch daemon running? (BEADS_DISPATCH=true)
```

**Failure (socket not found):**
```
Error: Socket file not found at /run/beads-dispatch/trigger.sock
```

## Relationship to Post-Commit Hook

Both `dispatch-beads` and the git post-commit hook send a "manual" trigger to the same daemon socket. The daemon doesn't distinguish between them — it simply wakes up and processes ready tasks.

| Trigger Source | Trigger Type | Use Case |
|----------------|--------------|----------|
| `git commit` | "manual" (via post-commit hook) | Automatic dispatch on commit |
| `dispatch-beads` | "manual" (direct) | Manual dispatch without commit |
| Scheduled cron | "scheduled" | Periodic check (if configured) |

## Common Use Case

```bash
# 1. Create or update tasks
bd create "New feature" --description="..." --type=task
bd update workspace-abc --claim

# 2. Manually dispatch (instead of committing)
dispatch-beads

# 3. Check worker status
bd list --status=in_progress
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `Connection refused` | Daemon not running | Start with `BEADS_DISPATCH=true start-beads-dispatch.sh` |
| `Socket not found` | Wrong path or daemon not started | Check `BEADS_DISPATCH_SOCKET_PATH`; verify daemon created socket |
| `Permission denied` | Socket permissions | Ensure daemon runs with same user; check socket permissions |
| Workers not spawning | No ready tasks | Run `bd ready` to verify; check task dependencies |

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load on keywords like "dispatch-beads", "beads dispatch", "trigger dispatch"; others require explicit `skill` tool invocation.
- **Tool mapping:** Uses generic action language:
  - "run a shell command" → executes `dispatch-beads` command
  - "read a file" → reads daemon logs, socket status
  - "fetch a URL" → not applicable (local Unix socket)
- **No hardcoded harness list:** Works with ANY harness implementing agentskills.io spec.
- **Harness-specific caveats:**
  - This is a **container-internal command** — only works inside the ClaudeConX container
  - Requires the Beads Dispatch daemon to be running in the same container
  - The Unix socket mechanism is Linux-specific
  - Works identically across all harnesses running inside the container