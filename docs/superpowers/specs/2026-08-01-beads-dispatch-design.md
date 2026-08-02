# Beads Dispatch — Design Spec

> **Status:** Proposed
> **Date:** 2026-08-01
> **Revision:** 2 (per review: rename to BEADS_DISPATCH, GIT_BRANCH_NAME only, no volume mounts on replicas, swarm-vs-local startup)

## Problem

When a Beads task is moved into the **ready** state (open, no active blockers), we want to
automatically spin up a **replica of the currently running container** — a sibling container or
swarm service from the same image whose `GIT_BRANCH_NAME` points at a git branch named after the
task. This gives each claimable task an isolated development environment pre-checked-out on its
own branch.

There is no such automation today: Beads tasks live in a Dolt-backed graph database and nothing
reacts to state changes.

## Goal

- Detect when a task transitions into the ready set (status `open`, no active blockers) in
  near-real-time.
- For each such task, create one **dispatched worker** for the task:
  - same image and environment (API keys, providers, config),
  - **no volume mounts** — runs on the container's ephemeral filesystem (config and workspace
    are regenerated/checked-out on boot; nothing persists),
  - `GIT_BRANCH_NAME=<task branch>` (branch named from the task),
  - `BEADS_DISPATCH=false` so a worker never dispatches its own workers,
  - code-server (8443) published on a free host port,
  - started as a **swarm service** when running on a swarm manager node, otherwise as a regular
    local Docker container.
- Be idempotent: one worker per task, never re-dispatched on restart or repeated polls.
- Be opt-in and safe: off by default, no recursion.

## Non-goals

- Not a replacement for `cconx` or `build-env` — this is a narrow, task-driven dispatcher.
- Not git-branch management beyond checkout (branch creation/checkout is handled by the existing
  `git-repo-setup.sh` startup script).
- **No lifecycle teardown in v1** — a dispatched worker stays up until removed manually. Tearing
  down the worker/service when the task leaves the ready set is a future enhancement.

## Background / verified facts

### Beads "ready" semantics (verified against bd 1.1.2)

- "Ready work" = issues with status `open` (category `active`) that have **no active blockers**.
- Query: `bd list --ready --json` returns a JSON array, one object per ready issue:
  ```json
  [{"id": "probe-n5h", "title": "Task A", "status": "open", "priority": 2, ...}]
  ```
- Blocked issues are excluded (verified: `bd dep add C --depends-on A; bd update C -s blocked`
  removes C from the ready set).
- This matches the **Ready** column of the bead-me-up-scotty web UI
  (`lib/board-columns.ts`: Ready = `status === "open" && !blocked`).

### Change detection

- `bd` has **no push/event/stream/daemon** mechanism (verified: no such subcommand exists;
  beads is CLI-shell-out by design; the reference UI "scotty" polls the CLI).
- **Therefore the trigger is a poll loop** over `bd list --ready --json` with a diff against a
  persisted "seen" set. New issue IDs in the ready set = "moved to ready".

### Container self-inspection & dispatch (verified against the built image)

- The Docker CLI works inside the container when `/var/run/docker.sock` is mounted (it is, per the
  README standard config). `docker info`, `docker inspect`, `docker run`, `docker service create`
  all operate on the **host** daemon from inside.
- `/etc/hostname` returns the container's short ID on the default bridge network, so a container
  can inspect itself via `docker inspect $(cat /etc/hostname)`.
- `docker inspect` exposes everything needed: `.Config.Image`, `.Config.Env`, `.HostConfig.RestartPolicy`, `.Name`.
- **Swarm detection** (verified on a 2-node swarm, this host is Leader):
  - `docker info --format '{{.Swarm.LocalNodeState}}'` → `active` when the node is in a swarm.
  - `docker info --format '{{.Swarm.ControlAvailable}}'` → `true` when the node is a manager.
  - Manager node ⇒ dispatch as a **swarm service**; otherwise ⇒ a regular **local container**.
- `git-repo-setup.sh` (startup script `93-`) clones `GIT_REPO_URL` into `DEFAULT_WORKSPACE`
  (`/workspace`) and checks out / creates `GIT_BRANCH_NAME`. On an ephemeral filesystem (no
  workspace volume) `/workspace` is always empty at first boot, so the clone always succeeds.

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  Running container (parent)                                    │
│                                                               │
│  /etc/cont-init.d/90-master-startup                           │
│    └─ /106-start-beads-dispatch (opt-in: BEADS_DISPATCH)      │
│         └─ beads-dispatch watcher (python3 stdlib daemon)     │
│              ├─ poll: bd list --ready --json  (every N sec)   │
│              ├─ diff vs state file (seen set)                 │
│              ├─ for each NEW ready issue:                     │
│              │   ├─ derive branch name from issue             │
│              │   ├─ detect swarm manager?                    │
│              │   ├─   yes → docker service create             │
│              │   └─   no  → docker run -d                     │
│              └─ persist seen set → /config/.beads-dispatch    │
└───────────────────────────────────────────────────────────────┘
                           │ docker socket (host daemon)
                           ▼
   Swarm manager?  ┌─ YES ── docker service create (swarm task, no mounts)
                   └─ NO  ── docker run -d (local container, no mounts)
```

## Design decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Trigger | Poll `bd list --ready --json`, diff vs persisted seen set | Only available mechanism (no push in bd) |
| D2 | "Moved to ready" | New issue ID appears in the ready set | Covers both new-open and status-changed issues; matches Ready column semantics |
| D3 | Idempotency | Persisted `seen` set in `/config/.beads-dispatch/state.json` | Survives watcher/container restarts; one worker per task |
| D4 | First run | Seed `seen` with the current ready set (do not dispatch for pre-existing ready tasks) | Avoids a burst of workers on container start; override with `BEADS_DISPATCH_SEED=all` |
| D5 | Replica storage | **No volume mounts** (no `/config`, no `/workspace`, no docker socket) | Explicitly requested; ephemeral worker — config and workspace are regenerated/checked out on boot |
| D6 | Recursion | Workers get `BEADS_DISPATCH=false` | Prevents unbounded container/service spawning |
| D7 | Branch name | `<BEADS_DISPATCH_BRANCH_PREFIX>/<issue-id>-<slug>` (default `task/probe-n5h-task-a`) | Readable, unique (issue id is unique), git-safe after slugging |
| D8 | Git env var | Set `GIT_BRANCH_NAME` only (the var `git-repo-setup.sh` reads) | Correct env var name |
| D9 | Git repo source | Inherit `GIT_REPO_URL`; if unset, derive from `git -C <workspace> remote get-url origin` | The worker always knows what to clone |
| D10 | Dispatch mode | Swarm manager node → `docker service create`; otherwise → `docker run -d` | Run workers on the swarm when available; fall back to local containers |
| D11 | Ports | Publish code-server 8443 to the first free host port ≥ `BEADS_DISPATCH_PORT_BASE` (default 8000); bind nothing else | Avoids host port conflicts; other services (scotty, happier, litellm) run internally |
| D12 | Restart | Local: inherit parent restart policy (default `unless-stopped`); swarm: `--restart-condition any` | Same durability as parent |
| D13 | Language/deps | Python 3 stdlib daemon (subprocess + json), no new pip deps | Uses system python3; shells out to `bd` and `docker` CLI |
| D14 | Runtime user | Runs as **root** | The watcher shells out to `docker` via the mounted host socket; the socket is `root:989` (verified), so `abc` gets "permission denied". `bd` also works as root |
| D15 | Race guard | Re-query the ready set immediately before each dispatch; skip if the issue is no longer ready | Dolt auto-commit is off by default, so the ready snapshot can race with a concurrent block/update — prevents dispatching an issue that was just re-blocked (observed in testing) |

## Environment variables (new)

| Variable | Default | Function |
|----------|---------|----------|
| `BEADS_DISPATCH` | *(unset)* | `true` enables the dispatcher on container startup |
| `BEADS_DISPATCH_INTERVAL` | `30` | Poll interval (seconds) for the ready set |
| `BEADS_DISPATCH_BRANCH_PREFIX` | `task` | Git branch prefix: `<prefix>/<issue-id>-<slug>` |
| `BEADS_DISPATCH_SEED` | `skip` | `skip` = do not dispatch for pre-existing ready issues on first start; `all` = dispatch for all current ready issues |
| `BEADS_DISPATCH_PORT_BASE` | `8000` | Lowest host port considered for the worker's 8443 mapping (first free used) |
| `BEADS_DISPATCH_STATE_DIR` | `/config/.beads-dispatch` | Where the seen-set state file lives |

## Failure modes & guards

- **No docker socket** → watcher logs a warning and exits (parent wasn't started with the socket).
- **No beads db yet** → watcher waits; it only acts once `bd list --ready --json` succeeds.
- **`bd` / docker command errors** → logged, poll continues.
- **Branch name collision** → `git-repo-setup.sh` checks out the existing branch instead of creating a new one (idempotent).
- **Worker name collision** (container or service already exists) → watcher checks first; skips if present.
- **Runaway spawning** → dedup via seen set + recursion disabled in workers.
- **Swarm `docker service create` failure** → logged with the error; optionally fall back to a local container (configurable at implementation time).

## Security notes

- The docker socket gives the watcher full host-docker control (same privilege the README already
  documents for Docker-in-Docker). The feature is opt-in (`BEADS_DISPATCH=true`).
- Worker name/image come from `docker inspect` (not user input); branch names are slugified and
  validated before use as env/container/service names.
- Secrets (API keys) are intentionally inherited by workers — they are full peers of the parent.
- Workers mount no volumes and no docker socket, so a compromised worker has no host-docker or
  persistent-state access.
