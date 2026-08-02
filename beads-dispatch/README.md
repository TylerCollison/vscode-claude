# Beads Dispatch

Automatically dispatches a worker (swarm service or local container) whenever you **commit** in
the workspace repo and a Beads task is **ready** (open, no active blockers). Each worker is
created from the running container's own image, with `GIT_BRANCH_NAME` set to a branch named
after the task and **no volume mounts** (ephemeral filesystem — the existing `git-repo-setup.sh`
clones the repo and checks out the branch on boot).

## How it works

1. On container start, a **root daemon** (`beads-dispatch --daemon`) installs a `post-commit`
   hook in the workspace repo and listens on `/run/beads-dispatch.sock`.
2. Every `git commit` runs the hook (as the committer). The hook **pings the socket** — nothing
   else; commits stay fast and are never broken.
3. The daemon checks `bd list --ready --json` and, for each ready task **not yet dispatched**,
   creates a worker:
   - **branch** = `task/<issue-id>-<slug>`, created **off the current HEAD** (the state you just
     committed — no commit is made by the tool) and **pushed** to origin,
   - the original branch is checked back out (the parent's working state is untouched),
   - **swarm manager node** → `docker service create` (a swarm service),
   - **otherwise** → `docker run -d` (a local container).
4. The task is recorded in the seen-set so a later commit never re-dispatches it.

Triggering on a commit guarantees the worker's branch contains committed work (not an empty
branch from origin/main), and the dispatcher never has to commit anything itself.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_DISPATCH` | *(unset)* | `true` enables the dispatcher on container startup |
| `BEADS_DISPATCH_BRANCH_PREFIX` | `task` | Git branch prefix: `<prefix>/<issue-id>-<slug>` |
| `BEADS_DISPATCH_PORT_BASE` | `8000` | Lowest host port considered for the worker's code-server (8443) mapping |
| `BEADS_DISPATCH_WORKER_PORT` | `8443` | Internal port published on the worker (code-server) |
| `BEADS_DISPATCH_STATE_DIR` | `/config/.beads-dispatch` | Where the seen-set state file lives |

## Prerequisites

- The container must be started with `/var/run/docker.sock` mounted (standard config).
- A git repo in the workspace (`GIT_REPO_URL` set, or a mounted/checked-out repo), and the parent
  must be able to **push** to its origin (credential helper / token configured).
- Beads must be initialized (`BEADS_ENABLED=true` or a manual `bd init`).

## Worker behavior

- Same image and full environment as the parent, with `GIT_BRANCH_NAME` set, `GIT_REPO_URL`
  ensured, and `BEADS_DISPATCH=false` (workers never dispatch their own workers; no hook is
  installed in their repos).
- **No volume mounts** — `/config` and `/workspace` live on the ephemeral container filesystem.
- Code-server (8443) is published on the first free host port ≥ `BEADS_DISPATCH_PORT_BASE`.
- Restart policy is inherited from the parent (local) / `any` (swarm service).

## Development

```bash
# Unit tests (no docker daemon needed)
python3 beads-dispatch/tests/test_beads_dispatch.py

# One-shot install + dispatch (manual testing)
BEADS_DISPATCH=true /usr/local/bin/beads-dispatch --once

# Watch the daemon log
tail -f /tmp/beads-dispatch.log
```

## Troubleshooting

- **No worker appears after a commit** → check `/tmp/beads-dispatch.log` for "Commit trigger
  received", push errors, or `bd` not ready.
- **"could not push branch"** → the parent needs credentials for its git origin (token /
  credential helper); configure and commit again.
- **`beads.task` label** → `docker service ls --filter label=beads.task` (swarm) or
  `docker ps --filter label=beads.task` (local) lists dispatched workers.
