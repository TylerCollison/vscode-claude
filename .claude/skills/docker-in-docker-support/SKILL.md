---
name: docker-in-docker-support
description: Use when you need to run Docker commands inside the container (build images, manage containers, use docker-compose) by mounting the host Docker socket
---

# Docker-in-Docker Support

## Overview
This container includes Docker CLI, Docker Compose v2, and Buildx pre-installed. By mounting the host's Docker socket (`/var/run/docker.sock`), you can run Docker commands from inside the container that execute on the host Docker daemon.

## When to Use
- Building Docker images from within the container (`docker build`, `docker buildx build`)
- Running containers for testing (`docker run`, `docker compose up`)
- Managing host containers (`docker ps`, `docker logs`, `docker stop`)
- Using Docker Compose for multi-container setups
- Running BuildKit builds for faster layered builds

**When NOT to use:**
- If you don't need Docker inside the container (saves resources)
- If security policies prohibit mounting the Docker socket

## Quick Reference

| Action | Command / Config |
|--------|------------------|
| Enable in docker run | `-v /var/run/docker.sock:/var/run/docker.sock` |
| Enable in docker-compose | `volumes: - /var/run/docker.sock:/var/run/docker.sock` |
| Test Docker access | `docker ps` or `docker version` |
| Build an image | `docker build -t myapp .` |
| Use BuildKit builder | `USE_BUILDKIT_BUILDER=true` (see BuildKit Builder skill) |
| Run docker-compose | `docker compose up -d` |

## Implementation

### Dockerfile Setup (Already Done)
The container image includes:
- `docker.io` — Docker CLI and daemon client
- `docker-compose-v2` — Docker Compose v2 plugin
- `docker-buildx` — Buildx for multi-platform builds
- `VOLUME /var/run/docker.sock` — Declares the socket mount point

### Runtime Configuration
Mount the host Docker socket when starting the container:

```bash
docker run -d \
  --name=claude-dev \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ...other options...
  tylercollison2089/vscode-claude
```

Or in docker-compose.yml:
```yaml
services:
  claude-dev:
    image: tylercollison2089/vscode-claude
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
```

### BuildKit Accelerated Builds (Optional)
For significantly faster Docker builds, enable the persistent BuildKit builder:

```bash
docker run -d \
  -e USE_BUILDKIT_BUILDER=true \
  -v /var/run/docker.sock:/var/run/docker.sock \
  ...
```

This creates a `docker-container` driver builder that avoids the expensive layer-export step. See the **BuildKit Builder** skill for details.

### Verifying It Works
Inside the container:
```bash
# Test basic connectivity
docker ps

# Test building
docker build -t test-image .

# Test compose
docker compose version
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Forgetting to mount the socket | Add `-v /var/run/docker.sock:/var/run/docker.sock` |
| Socket permission denied | Ensure container runs with appropriate permissions (PUID/PGID) or socket has correct ACLs |
| Docker commands hang | Check if host Docker daemon is running: `systemctl status docker` |
| "Cannot connect to Docker daemon" | Socket not mounted or Docker not running on host |
| BuildKit builder not persisting | Ensure `USE_BUILDKIT_BUILDER=true` is set on ALL containers sharing the builder |

## Security Note
Mounting `/var/run/docker.sock` gives the container **full control over the host's Docker daemon**. This is equivalent to root access on the host. Only use in trusted environments.

## Related Skills
- **BuildKit Builder** — Persistent BuildKit builder for faster builds (`configure-buildx.sh`)
- **Build Environment** — Persistent build containers (`build-env` tool)