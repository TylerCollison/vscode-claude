# Beads Dispatch

Automatically dispatches a worker (swarm service or local container) when a Beads task moves
to the **ready** state. Each worker is created from the running container's own image, with
`GIT_BRANCH_NAME` set to a branch named after the task, and **no volume mounts** (ephemeral
filesystem — the existing `git-repo-setup.sh` clones the repo and checks out the branch on boot).

## How it works

1. Polls `bd list --ready --json` every `BEADS_DISPATCH_INTERVAL` seconds (default `30`).
2. Diffs the ready set against a persisted seen-set in
   `BEADS_DISPATCH_STATE_DIR` (default `/config/.beads-dispatch/state.json`).
3. For each **newly-ready** issue, dispatches a worker:
   - **swarm manager node** → `docker service create` (a swarm service)
   - **otherwise** → `docker run -d` (a local container)
4. Marks the issue as seen so it is never dispatched twice.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_DISPATCH` | *(unset)* | `true` enables the dispatcher on container startup |
| `BEADS_DISPATCH_INTERVAL` | `30` | Poll interval (seconds) |
| `BEADS_DISPATCH_BRANCH_PREFIX` | `task` | Git branch prefix: `<prefix>/<issue-id>-<slug>` |
| `BEADS_DISPATCH_SEED` | `skip` | `skip` = don't dispatch for already-ready issues on first start; `all` = dispatch for all current ready issues |
| `BEADS_DISPATCH_PORT_BASE` | `8000` | Lowest host port considered for the worker's code-server (8443) mapping |
| `BEADS_DISPATCH_WORKER_PORT` | `8443` | Internal port published on the worker (code-server) |
| `BEADS_DISPATCH_STATE_DIR` | `/config/.beads-dispatch` | Where the seen-set state file lives |

## Prerequisites

- The container must be started with `/var/run/docker.sock` mounted (standard config).
- `GIT_REPO_URL` set in the environment, **or** the workspace must be a git repo with an `origin`
  remote (the origin URL is then inherited by workers).
- Beads must be initialized (`BEADS_ENABLED=true` or a manual `bd init`).

## Branch naming

Branch name = `<BEADS_DISPATCH_BRANCH_PREFIX>/<issue-id>-<slugified-title>`, e.g.
`task/probe-n5h-task-a`. If the title produces no slug, it falls back to
`task/probe-n5h`.

## Worker behavior

- Same image and full environment as the parent, with `GIT_BRANCH_NAME` set, `GIT_REPO_URL`
  ensured, and `BEADS_DISPATCH=false` (so workers never dispatch their own workers).
- **No volume mounts** — `/config` and `/workspace` live on the ephemeral container filesystem;
  nothing persists.
- Code-server (8443) is published on the first free host port ≥ `BEADS_DISPATCH_PORT_BASE`.
- Restart policy is inherited from the parent (local) / `any` (swarm service).

## Development

```bash
# Unit tests (no docker daemon needed)
python3 beads-dispatch/tests/test_beads_dispatch.py

# One-shot poll+dispatch (testing)
BEADS_DISPATCH=true /usr/local/bin/beads-dispatch --once

# Watch the log
tail -f /tmp/beads-dispatch.log
```
