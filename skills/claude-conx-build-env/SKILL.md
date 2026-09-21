---
name: claude-conx-build-env
description: Use when you need a persistent, isolated Docker container for running build commands with bidirectional file synchronization. Trigger when the user asks to compile code, run tests, build artifacts, or execute long-running build processes in a consistent environment.
---

# build-env (ClaudeConX)

Create and manage persistent Docker containers for build commands with bidirectional sync between host and container.

## Overview

`build-env` provides consistent, reproducible build environments by running commands inside dedicated Docker containers. Unlike one-off `docker run` commands, `build-env` containers persist across invocations, maintaining state (installed packages, compiled artifacts, cache) while synchronizing source files bidirectionally with the host.

## Installation

**In ClaudeConX container:** Pre-installed at `/usr/local/bin/build-env`

**On host:** Install via pip:
```bash
pip install build-env
```

## Required Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BUILD_CONTAINER` | Docker image to use for the build container | `python:3.11-slim` |
| `DEFAULT_WORKSPACE` | Host workspace path to sync | `/workspace` |

## Usage

### Run a Single Command

```bash
build-env -- run npm test
```

### Run Multiple Commands (Container Persists)

```bash
build-env -- npm install
build-env -- npm run build
build-env -- npm test
```

The container stays running between commands, preserving `node_modules`, build cache, etc.

### Shutdown the Container

```bash
build-env --exit
```

### Specify a Custom Image

```bash
BUILD_CONTAINER=golang:1.21 build-env -- go build ./...
```

### Set Custom Workspace

```bash
DEFAULT_WORKSPACE=/my/project build-env -- make
```

## Features

### Persistent Containers
Containers survive across command invocations. State (installed packages, compiled objects, caches) is preserved.

### Environment Isolation
Each workspace gets its own container. No cross-project contamination.

### Bidirectional Sync
Files are synchronized in both directions:
- Host → Container: Source code, config files
- Container → Host: Build artifacts, generated files, lockfiles

### Synchronization Algorithm
1. **Compare** modification timestamps between host and container
2. **Delete orphans** in container that no longer exist on host (opt-in with `--delete-orphans`)
3. **Copy missing** files from host to container
4. **Resolve conflicts** by keeping the newer version (based on mtime)

## Docker Image Recommendations

| Language | Recommended Image |
|----------|-------------------|
| Python | `python:3.11-slim` |
| Node.js | `node:20-slim` |
| Go | `golang:1.21` |
| Rust | `rust:1.73-slim` |
| Java | `eclipse-temurin:21-jdk` |
| .NET | `mcr.microsoft.com/dotnet/sdk:8.0` |
| Custom | Any image with your toolchain |

## Security

- **Image validation:** Only trusted, official images recommended
- **Container isolation:** No privileged access, no host network by default
- **User mapping:** Runs as container's default user (not root)
- **Volume mounts:** Only workspace directory is mounted

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Container won't start | Check `BUILD_CONTAINER` image exists locally or on Docker Hub |
| Sync conflicts | Run `build-env --exit` and restart; check file timestamps |
| Permission errors | Ensure `PUID`/`PGID` match host user; check workspace permissions |
| Out of disk | Run `docker system prune` or increase container disk limit |
| Stale container state | Use `build-env --exit` to force fresh container on next run |

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load on keywords like "build-env", "persistent build", "Docker build"; others require explicit `skill` tool invocation.
- **Tool mapping:** Uses generic action language:
  - "run a shell command" → executes `build-env` CLI
  - "read a file" → reads sync status, logs, config
  - "write a file" → creates `.build-env` config files
- **No hardcoded harness list:** Works with ANY harness implementing agentskills.io spec.
- **Harness-specific caveats:**
  - This is a **host-level tool** that manages separate Docker containers
  - The harness does not run inside the build container; it orchestrates from outside
  - Works identically across all harnesses since it's a CLI command
  - Requires Docker daemon access (available in ClaudeConX via Docker-in-Docker)