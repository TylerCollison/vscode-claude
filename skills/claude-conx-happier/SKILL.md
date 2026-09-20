---
name: claude-conx-happier
description: Use when you need to orchestrate AI agents across sessions, delegate work to subagents, run planning or review workflows, or manage cross-harness agent communication via the Happier CLI. Trigger when the user asks to start a delegated agent, run a code review, create a plan, or connect to a Happier relay server.
---

# Happier CLI (ClaudeConX)

The Happier CLI provides agent management, session delegation, planning, review, and cross-harness orchestration from the command line.

## When to Use

- **Delegate work** to a background agent that runs independently
- **Plan** complex multi-step implementations before executing
- **Review** code changes for correctness, security, and quality
- **Voice agents** for hands-free interaction
- **Cross-session messaging** between agents/harnesses
- **Manage machines** and sessions on a Happier relay server

## Core Commands

### Agent Delegation

```bash
# Start a delegated agent for a task
happier agent start --backend-target agent:claude --instructions "Fix the login bug" --permission-mode workspace_write

# Start a planning agent
happier plan start --backend-target agent:claude --instructions "Design the new API" --permission-mode read_only

# Start a code review
happier review start --engine-ids coderabbit --instructions "Review for security issues" --permission-mode read_only

# Start a voice agent
happier voice-agent start --backend-target agent:claude --instructions "Help me debug" --permission-mode read_only
```

### Session Management

```bash
# List running sessions
happier session list

# Send a message to a session
happier session send <session-id> "Check the test results"

# Wait for a run to complete
happier run wait <run-id> --timeout 300

# Stop a run
happier run stop <run-id>
```

### Machine Management

```bash
# List available machines (containers/agents)
happier machine list

# Search for machines by name
happier machine search "vscode-claude"

# Start a new session on a machine
happier session start --machine <machine-id> --backend-target agent:claude
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `HAPPIER_MODE` | Role: `server` (relay) or `agent` (client) | Yes for server |
| `HAPPIER_SERVER_URL` | URL of Happier relay server | Yes for agent |
| `HAPPIER_ACCESS_KEY` | Full JSON of `access.key` for auto-auth | No (alternative to pairing) |

## Authentication Flow

1. **Existing credentials** → Daemon starts immediately
2. **`HAPPIER_ACCESS_KEY` provided** → Key written, daemon starts immediately
3. **Default** → Pairing request submitted, connect URL printed in logs:
   ```
   https://<server>:3005/terminal/connect#key=<base64-key>&server=https%3A%2F%2F<server>%3A3005
   ```
   Open URL in browser to approve. Credentials persist for future restarts.

## Delegation Patterns

| Pattern | When to Use | Command |
|---------|-------------|---------|
| **Delegate** | Independent task, fire-and-forget | `happier agent start` |
| **Plan** | Need design before implementation | `happier plan start` |
| **Review** | Verify correctness/security of changes | `happier review start` |
| **Voice** | Hands-free, conversational workflow | `happier voice-agent start` |
| **Subagents** | Parallel multi-agent workflow | `happier subagents delegate` |

## Integration with Beads Dispatch & MR/PR Dispatch

- **Every dispatched worker container** appears as a machine on the Happier server
- **Machine name** = container hostname (reflects the work being done)
- **Beads Dispatch workers** → machines named like `beads-worker-<task-id>`
- **MR/PR Dispatch workers** → machines named like `mr-pr-<repo>-<number>`
- Use `happier machine list` to see all active workers
- Use `happier session send` to communicate with running workers

## Container Startup (ClaudeConX)

When `HAPPIER_SERVER_URL` is set, the container automatically:
1. Authenticates with the relay server (using `HAPPIER_ACCESS_KEY` or pairing)
2. Starts the Happier daemon
3. Registers as a machine on the server
4. Becomes available for delegation

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Verify `HAPPIER_SERVER_URL` is correct and server is running |
| Auth failed | Check `HAPPIER_ACCESS_KEY` is valid JSON; try re-pairing |
| Daemon won't start | Check logs: `journalctl -u happier` or container logs |
| Machine not showing | Ensure `HAPPIER_MODE=agent` and server URL accessible |
| Timeout on run wait | Increase `--timeout`; check if run is stuck |

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load on keywords like "happier", "delegate", "subagent", "orchestrate"; others require explicit `skill` tool invocation.
- **Tool mapping:** Uses generic action language:
  - "run a shell command" → executes `happier` CLI commands
  - "read a file" → reads `access.key`, config files, logs
  - "write a file" → writes `access.key`, session configs
  - "search files" → searches logs, session transcripts
  - "fetch a URL" → calls Happier REST API endpoints
- **No hardcoded harness list:** Works with ANY harness implementing agentskills.io spec.
- **Harness-specific caveats:**
  - **Claude Code:** Integrates with `/skill` tool and Agent tool for delegation
  - **Codex:** Uses native `agent` tool for delegation; `happier` CLI runs in terminal
  - **OpenCode:** Similar to Codex; `happier` CLI available in terminal
  - **All harnesses:** The `happier` CLI is a standalone binary — harness-agnostic
  - **Machine names:** Always reflect the work (repo name, task ID, PR number)
  - **Cross-session:** Works across different harnesses connected to same Happier server