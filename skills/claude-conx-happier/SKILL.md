---
name: claude-conx-happier
description: Use when you need to start AI coding sessions (Claude Code, Codex, OpenCode, Gemini), manage authentication with Happier relay servers, configure MCP servers, or manage the Happier daemon/services. Trigger when the user asks to start a coding session, authenticate with Happier, configure MCP, or manage background services.
---

# Happier CLI (ClaudeConX)

The Happier CLI starts AI coding sessions, manages authentication with relay servers, configures MCP servers, and controls background daemons/services.

## When to Use

- **Start AI coding sessions** — Claude Code (default), Codex, OpenCode, or Gemini
- **Authenticate with Happier relay** — login, pairing, status
- **Manage MCP servers** — add, list, bind, test MCP servers
- **Control daemon/services** — start, stop, status, install automatic startup
- **Connect API keys** — store Anthropic, OpenAI, Google, GitHub credentials in Happier cloud
- **Send push notifications** — notify mobile app

## Core Commands

### Start AI Sessions

```bash
# Start default backend (Claude Code)
happier

# Start with specific backend
happier codex        # Start Codex mode
happier opencode     # Start OpenCode mode (ACP)
happier gemini       # Start Gemini mode (ACP)

# Start with options
happier --yolo                    # Bypass permissions (--dangerously-skip-permissions)
happier --chrome                  # Enable Chrome browser access
happier --js-runtime bun          # Use bun instead of node
happier --profile <id-or-name>    # Use a backend profile from settings
happier --resume                  # Resume previous session
```

### Authentication

```bash
# Interactive login (opens browser)
happier auth login

# Headless login (prints URL, no browser)
happier auth login --no-open

# Force re-authentication
happier auth login --force

# Create auth request (headless-friendly, returns JSON)
happier auth request --json

# Approve auth request with local credentials
happier auth approve --public-key <base64> --json

# Wait for approval and write credentials
happier auth wait --public-key <base64> --json

# Remote pairing over SSH
happier auth pair-remote --ssh user@host

# Check auth status
happier auth status

# Logout
happier auth logout
```

### MCP Server Management

```bash
# Start MCP proxy for a session
happier mcp serve --session <session-id>

# List MCP servers
happier mcp servers list

# Add MCP server (stdio transport)
happier mcp servers add --name <name> --transport stdio --command <cmd> --arg <arg>

# Bind MCP server to all machines
happier mcp servers bind --mcp-server <name|id> --all-machines

# Unbind MCP server
happier mcp servers unbind --binding-id <id>

# Detect MCP servers from provider
happier mcp servers detect --provider <provider-id>

# Test MCP server
happier mcp servers test --mcp-server <name|id>
```

### Daemon & Service Management

```bash
# Start daemon (detached)
happier daemon start

# Restart daemon
happier daemon restart

# Stop daemon (sessions stay alive)
happier daemon stop

# Stop daemon and kill sessions
happier daemon stop --kill-sessions

# Show daemon status
happier daemon status

# List active sessions
happier daemon list

# Install automatic startup (systemd/launchd)
happier service install

# Uninstall automatic startup
happier service uninstall

# List installed services
happier service list

# Start/stop/restart installed service
happier service start|stop|restart

# View service logs
happier service logs
```

### Connect API Keys (Happier Cloud)

```bash
# Connect Anthropic Claude (subscription or API key)
happier connect claude
happier connect claude --api-key
happier connect claude --setup-token

# Connect OpenAI Codex
happier connect codex
happier connect codex --api-key

# Connect Google Gemini
happier connect gemini

# Connect GitHub
happier connect github --token

# Show connection status
happier connect status
```

### Other Commands

```bash
# Send push notification to mobile
happier notify "Build complete"

# Install provider CLIs
happier install

# Run diagnostics
happier doctor
```

## Server Selection (Global Flags)

```bash
# Use specific relay by name
happier --server <name-or-id> auth status

# Use specific relay URL (ephemeral)
happier --server-url https://relay.example.com auth login

# Persist relay URL as active profile
happier --server-url https://relay.example.com --persist auth login
```

## Environment Variables (ClaudeConX Container)

| Variable | Description | Required |
|----------|-------------|----------|
| `HAPPIER_MODE` | Role: `server` (relay) or `agent` (client) | Yes for server |
| `HAPPIER_SERVER_URL` | URL of Happier relay server | Yes for agent |
| `HAPPIER_ACCESS_KEY` | Full JSON of `access.key` for auto-auth | No (alternative to pairing) |

## Authentication Flow (Container Startup)

When `HAPPIER_SERVER_URL` is set, the container automatically:
1. **Existing credentials** → Daemon starts immediately
2. **`HAPPIER_ACCESS_KEY` provided** → Key written, daemon starts immediately
3. **Default** → Pairing request submitted, connect URL printed in logs:
   ```
   https://<server>:3005/terminal/connect#key=<base64-key>&server=https%3A%2F%2F<server>%3A3005
   ```
   Open URL in browser to approve. Credentials persist for future restarts.

## Container Integration (ClaudeConX)

- **Daemon auto-starts** when `HAPPIER_SERVER_URL` is configured
- **Machine registration** — container registers as a machine on the relay server
- **Machine name** = container hostname (reflects the work: repo name, task ID, PR number)
- **Beads Dispatch workers** appear as machines named like `beads-worker-<task-id>`
- **MR/PR Dispatch workers** appear as machines named like `mr-pr-<repo>-<number>`
- **Use `happier daemon list`** to see active sessions on this machine

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Verify `HAPPIER_SERVER_URL` is correct and server is running |
| Auth failed | Check `HAPPIER_ACCESS_KEY` is valid JSON; try `happier auth login --force` |
| Daemon won't start | Run `happier daemon status`; check `happier doctor` |
| Codex/OpenCode not found | Run `happier install` or ensure CLI is in PATH |
| MCP server not working | Test with `happier mcp servers test` |
| Service not starting | Check `happier service logs`; run `happier doctor repair` |

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load on keywords like "happier", "codex", "opencode", "gemini", "auth", "mcp"; others require explicit `skill` tool invocation.
- **Tool mapping:** Uses generic action language:
  - "run a shell command" → executes `happier` CLI commands
  - "read a file" → reads `access.key`, config files, logs
  - "write a file" → writes `access.key`, session configs
  - "search files" → searches logs, session transcripts
  - "fetch a URL" → calls Happier REST API endpoints
- **No hardcoded harness list:** Works with ANY harness implementing agentskills.io spec.
- **Harness-specific caveats:**
  - **Claude Code:** `happier` starts a Claude Code session with mobile control
  - **Codex:** `happier codex` starts Codex; `happier` CLI runs in terminal
  - **OpenCode:** `happier opencode` starts OpenCode; `happier` CLI available in terminal
  - **All harnesses:** The `happier` CLI is a standalone binary — harness-agnostic
  - **Machine names:** Always reflect the work (repo name, task ID, PR number)
  - **Cross-session:** Works across different harnesses connected to same Happier server