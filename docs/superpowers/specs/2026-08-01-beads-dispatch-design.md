# Beads Dispatch — Design Spec

> **Status:** Proposed
> **Date:** 2026-08-01
> **Revision:** 4 (dispatcher no longer creates/pushes branch; worker auto-creates branch off default branch)

## Problem

When a Beads task is moved into the **ready** state (open, no active blockers), we want to
automatically spin up a **replica of the currently running container** — a sibling container or
swarm service from the same image whose `GIT_BRANCH_NAME` points at a git branch named after the
task. This gives each claimable task an isolated development environment pre-checked-out on its
own branch.

There is no such automation today: Beads tasks live in a Dolt-backed graph database and nothing
reacts to state changes.

## Why trigger on a git commit

A worker is a fresh clone of `GIT_REPO_URL`; it can only ever see **committed** state that exists
in `origin`. Polling for ready tasks doesn't guarantee the task's context is committed or pushed,
so a worker spawned from a poll could check out an empty branch. Triggering on a **commit**
guarantees:

1. A commit just happened → the working tree is in a defined, committed state.
2. The branch is created **off the current HEAD** → it contains every commit up to and including
   the triggering commit, so the worker pulls the task's actual work.
3. The dispatcher never commits anything — no "committing problem", no risk of moving the user's
   uncommitted WIP or polluting the repo.

On commit, the dispatcher checks `bd list --ready --json` and creates a worker for **each**
currently-ready task (idempotent via a persisted seen-set).

## Goal

- On every git commit in the parent workspace repo, check for ready tasks and create one
  **dispatched worker** for each:
  - same image and environment (API keys, providers, config),
  - **no volume mounts** — runs on the container's ephemeral filesystem (config and workspace
    are regenerated/checked-out on boot; nothing persists),
  - `GIT_BRANCH_NAME=<task branch>`, created off the current HEAD and **pushed** to origin,
  - `BEADS_DISPATCH=false` so a worker never dispatches its own workers,
  - code-server (8443) published on a free host port,
  - started as a **swarm service** when running on a swarm manager node, otherwise as a regular
    local Docker container.
- Be idempotent: one worker per task, never re-dispatched on later commits.
- Be opt-in and safe: off by default, no recursion.

## Non-goals

- Not a replacement for `cconx` or `build-env` — this is a narrow, task-driven dispatcher.
- Not git-branch management beyond checkout (branch creation/checkout is handled by the existing
  `git-repo-setup.sh` startup script).
- **No lifecycle teardown in v1** — a dispatched worker stays up until removed manually.
- **No beads-export/import in v1** — the worker's beads DB starts fresh (task *tracking* stays in
  the parent; the worker is a code sandbox on the task branch). Can be added later if wanted.

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

### Trigger mechanism (verified against the built image)

- Git hooks run as the **committer**. In this container the IDE/Claude Code commit as `abc`, but
  `abc` is **not** in the sudo group and `sudo -n` fails (verified) — so the hook cannot elevate
  to root, and root is required to talk to the docker socket (`root:989`, verified).
- **Bridge:** a root daemon listens on a unix socket (`/run/beads-dispatch.sock`, mode 0666); the
  post-commit hook (as `abc`) connects and sends a byte. Verified: abc→socket→root round-trip works.
  This is **event-driven** (no polling).
- `bd init` does **not** install a `post-commit` git hook by default (verified: `.git/hooks/`
  empty), so the dispatcher's hook won't conflict; any pre-existing hook is backed up.
- **`core.hooksPath`:** `bd init` sets `core.hooksPath` to `<workspace>/.beads/hooks` (verified),
  so git only runs hooks from there — the dispatcher's `post-commit` hook must be installed into
  the **effective hooks dir** (from `core.hooksPath`), not `.git/hooks`. Beads installs no
  `post-commit` there, so there is no conflict.
- **`safe.directory`:** the dispatcher runs git as **root** but the workspace repo is owned by the
  `abc` user, so git 2.35+ refuses with "dubious ownership". The daemon adds the workspace to
  root's `safe.directory` at startup (verified fix).

### Container self-inspection & dispatch (verified against the built image)

- The Docker CLI works inside the container when `/var/run/docker.sock` is mounted. `docker info`,
  `docker inspect`, `docker run`, `docker service create` all operate on the **host** daemon.
- `/etc/hostname` returns the container's short ID, so a container inspects itself via
  `docker inspect $(cat /etc/hostname)`.
- `docker inspect` exposes everything needed: `.Config.Image`, `.Config.Env`,
  `.HostConfig.RestartPolicy`, `.Name`.
- **Swarm detection** (verified on a 2-node swarm, this host is Leader):
  `docker info --format '{{.Swarm.LocalNodeState}}'` == `active` AND
  `docker info --format '{{.Swarm.ControlAvailable}}'` == `true` ⇒ manager ⇒ dispatch as a
  **swarm service**; otherwise a **local container**.
- **Branch creation**: the dispatcher derives the branch name and passes it via `GIT_BRANCH_NAME`. The worker's `git-repo-setup.sh` clones the repo and automatically creates the branch off the default branch (typically `main`) if it doesn't exist, or checks it out if it does.

## Architecture

```
Parent container:
  /etc/cont-init.d/90-master-startup
    └─ /106-start-beads-dispatch (root, opt-in BEADS_DISPATCH=true)
         └─ beads-dispatch --daemon (root)
              ├─ install .git/hooks/post-commit in the workspace repo (back up existing)
              ├─ listen on /run/beads-dispatch.sock (0666)
              └─ on trigger → dispatch_all()

  git commit (by abc, anywhere in the repo)
    └─ .git/hooks/post-commit (runs as abc)
         └─ ping /run/beads-dispatch.sock   (event-driven, non-blocking)
              └─ daemon (root):
                   ├─ bd list --ready --json
                   ├─ diff vs seen-set (/config/.beads-dispatch/state.json)
                   └─ for each NEW ready task:
                        ├─ branch = task/<id>-<slug>; pass via GIT_BRANCH_NAME
                        ├─ detect swarm manager?
                        │    ├─ yes → docker service create
                        │    └─ no  → docker run -d
                        └─ mark seen + persist

Worker (first boot, ephemeral filesystem):
  git-repo-setup.sh  → clone GIT_REPO_URL, create/checkout GIT_BRANCH_NAME
                       (auto-creates branch off default branch if missing)
  configure-beads.sh → bd init (fresh DB)
```

## Design decisions

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Trigger | A git **post-commit** hook pings a root daemon via a unix socket; the daemon dispatches | Event-driven, no polling; guarantees the branch is created off a committed state |
| D2 | "Which tasks" | On each trigger, `bd list --ready --json`; dispatch every ready issue not yet seen | "Ready to be worked" = the current ready set; the committed state is captured by the branch-from-HEAD |
| D3 | Idempotency | Persisted `seen` set in `/config/.beads-dispatch/state.json` | One worker per task across many commits/restarts |
| D4 | Privilege bridge | Root daemon owns the socket; the hook (abc) only pings it | `abc` cannot elevate (no sudo) and cannot reach the docker socket |
| D5 | Branch source | Dispatcher passes `GIT_BRANCH_NAME` to worker; worker (via `git-repo-setup.sh`) creates branch off default branch if missing | Simplifies dispatcher, leverages existing worker init; worker always starts from a clean base |
| D6 | Push | No branch push by dispatcher | Worker pulls from `origin`; dispatcher no longer responsible for pushing branches |
| D7 | Replica storage | **No volume mounts** | Ephemeral worker; config and workspace regenerated on boot |
| D8 | Recursion | Workers get `BEADS_DISPATCH=false` (and no hook is installed in their repo) | Prevents unbounded spawning |
| D9 | Branch name | `<BEADS_DISPATCH_BRANCH_PREFIX>/<issue-id>-<slug>` (default `task/probe-n5h-task-a`) | Readable, unique, git-safe |
| D10 | Git env var | Set `GIT_BRANCH_NAME` only | The var `git-repo-setup.sh` reads |
| D11 | Git repo source | Inherit `GIT_REPO_URL`; else `git -C <workspace> remote get-url origin` | The worker always knows what to clone/push to |
| D12 | Dispatch mode | Swarm manager → `docker service create`; else `docker run -d` | Use the swarm when available |
| D13 | Ports | Publish code-server 8443 on the first free host port ≥ `BEADS_DISPATCH_PORT_BASE` (default 8000) | Avoids host conflicts |
| D14 | Restart | Local: inherit parent policy; swarm: `--restart-condition any` | Same durability as parent |
| D15 | Language/deps | Python 3 stdlib daemon (subprocess, json, socket, signal); no new pip deps | Shells out to `bd` + `docker` |
| D16 | Runtime user | Root (daemon + dispatch) | Docker socket is `root:989`; `bd` works as root |
| D17 | Race guard | Re-check the ready set (and branch state) immediately before each dispatch | Avoids dispatching an issue that was just re-blocked, and avoids recreating an already-pushed branch |
| D18 | Hook safety | Back up any existing `post-commit` hook to `post-commit.beads-dispatch.bak`; hook is a tiny non-blocking ping | Non-destructive; commits stay fast |

## Environment variables (new)

| Variable | Default | Function |
|----------|---------|----------|
| `BEADS_DISPATCH` | *(unset)* | `true` enables the dispatcher (installs the hook + starts the daemon) on container startup |
| `BEADS_DISPATCH_BRANCH_PREFIX` | `task` | Git branch prefix: `<prefix>/<issue-id>-<slug>` |
| `BEADS_DISPATCH_PORT_BASE` | `8000` | Lowest host port considered for the worker's 8443 mapping (first free used) |
| `BEADS_DISPATCH_WORKER_PORT` | `8443` | Internal port published on the worker (code-server) |
| `BEADS_DISPATCH_STATE_DIR` | `/config/.beads-dispatch` | Where the seen-set state file lives |

*(`BEADS_DISPATCH_INTERVAL` and `BEADS_DISPATCH_SEED` are removed — dispatch is commit-driven.)*

## Failure modes & guards

- **No docker socket** → daemon logs a warning and exits.
- **No git repo in the workspace** → hook install is skipped (logged); dispatch only works when a
  repo exists.
- **No beads db yet** → the ready check fails gracefully; nothing dispatched until `bd init` runs.
- **Push fails (no credentials)** → clear, actionable error; the task is marked seen (no spam) so
  the parent can be fixed and the branch created manually if needed.
- **Remote branch already exists** → skip create/push; still dispatch the worker (it checks out the
  existing branch).
- **`bd` / docker command errors** → logged; other ready tasks still process.
- **Worker name collision** (container/service exists) → skip.
- **Runaway spawning** → seen-set dedup + `BEADS_DISPATCH=false` in workers.

## Security notes

- The docker socket gives the daemon full host-docker control (same privilege the README already
  documents for Docker-in-Docker). The feature is opt-in (`BEADS_DISPATCH=true`).
- The unix socket only carries a "commit happened" signal; any container user can trigger a
  dispatch, but dispatch is idempotent (seen-set), so spurious triggers are harmless.
- Worker name/image come from `docker inspect`; branch names are slugified and validated.
- Secrets (API keys) are intentionally inherited by workers — they are full peers of the parent.
- Workers mount no volumes and no docker socket.
