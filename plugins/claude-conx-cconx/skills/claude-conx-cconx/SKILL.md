---
name: claude-conx-cconx
description: Use when you need to manage ClaudeConX Docker instances — start, stop, delete, check status, configure DNS, or manage environment variables. Trigger when the user asks to create a new ClaudeConX instance, manage existing instances, or configure container networking.
---

# cconx (ClaudeConX Docker Management)

Command-line interface for managing ClaudeConX Docker instances with lifecycle management, DNS, and environment configuration.

## Overview

`cconx` is the primary management tool for ClaudeConX containers. It handles instance creation, configuration, networking, and lifecycle operations.

## Installation

**In ClaudeConX container:** Pre-installed at `/usr/local/bin/cconx`

**On host:** Included in the ClaudeConX repository at `/workspace/cconx`

## Core Commands

### Instance Lifecycle

```bash
# Create and start a new instance
cconx create --name my-instance --workspace /path/to/code

# Start an existing instance
cconx start my-instance

# Stop an instance
cconx stop my-instance

# Delete an instance (removes container, keeps volumes)
cconx delete my-instance

# Force delete (removes container and volumes)
cconx delete --force my-instance
```

### Status & Information

```bash
# List all instances
cconx list

# Show detailed status
cconx status my-instance

# Show logs
cconx logs my-instance --follow

# Show resource usage
cconx stats my-instance
```

### Configuration

```bash
# Set environment variable
cconx env set my-instance KEY=value

# Append to existing variable (e.g., add API key)
cconx env append my-instance GOOGLE_API_KEY=new-key

# Remove environment variable
cconx env unset my-instance KEY

# Show all environment variables
cconx env show my-instance
```

### Networking & DNS

```bash
# Configure custom domain
cconx dns set my-instance dev.example.com

# Remove custom domain
cconx dns unset my-instance

# Show DNS configuration
cconx dns show my-instance
```

### Workspace Management

```bash
# Change workspace path
cconx workspace set my-instance /new/path

# Show current workspace
cconx workspace show my-instance
```

## Environment Variable Management

`cconx` uses append/override logic for environment variables:

- **Override (default):** `cconx env set` replaces the value
- **Append:** `cconx env append` adds to comma-separated lists (e.g., API keys)

This is critical for `CLAUDE_MARKETPLACES`, `CLAUDE_PLUGINS`, `SKILLS_MARKETPLACES`, `SKILLS` where you want to add to existing values.

## Configuration Files

Instance configuration is stored in:
- `/config/cconx/instances/<name>.json` — Instance metadata
- Docker labels on container — Runtime config

## Common Workflows

### New Project Setup

```bash
cconx create --name my-project --workspace ~/code/my-project
cconx env append my-project GOOGLE_API_KEY=your-key
cconx env append my-project NIM_API_KEY=your-key
cconx start my-project
```

### Switching Workspaces

```bash
cconx stop current-project
cconx workspace set current-project ~/code/other-project
cconx start current-project
```

### Adding API Keys to Running Instance

```bash
cconx env append running-instance NEW_API_KEY=key
cconx restart running-instance
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Instance won't start | Check `cconx logs <name>`; verify workspace exists; check port conflicts |
| DNS not resolving | Verify `cconx dns show`; check `/etc/hosts` or DNS provider |
| Env vars not applying | Restart instance after `cconx env` changes; check `cconx env show` |
| Permission denied | Ensure Docker socket access; run with appropriate privileges |
| Volume conflicts | Use `cconx delete --force` to clean up; check `docker volume ls` |

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load on keywords like "cconx", "ClaudeConX", "instance management", "Docker management"; others require explicit `skill` tool invocation.
- **Tool mapping:** Uses generic action language:
  - "run a shell command" → executes `cconx` CLI commands
  - "read a file" → reads instance config JSON, logs
  - "write a file" → updates instance config, environment files
  - "fetch a URL" → not directly used (local Docker API)
- **No hardcoded harness list:** Works with ANY harness implementing agentskills.io spec.
- **Harness-specific caveats:**
  - This is a **host-level tool** that manages Docker containers
  - The harness does not run inside the managed instances; it orchestrates from outside
  - Works identically across all harnesses since it's a CLI command
  - Requires Docker daemon access (available in ClaudeConX via Docker-in-Docker)
  - On host, requires Docker and appropriate permissions