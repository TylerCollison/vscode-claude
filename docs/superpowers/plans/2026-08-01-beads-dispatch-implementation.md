# Beads Dispatch Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a Beads task moves to the **ready** state, automatically create a dispatched worker (swarm service or local container) from the same image, with `GIT_BRANCH_NAME` set to a branch named after the task, and **no volume mounts**.

**Architecture:** A Python 3 stdlib watcher daemon (opt-in) polls `bd list --ready --json`, diffs against a persisted seen-set, detects whether the node is a swarm manager, and dispatches via `docker service create` (swarm) or `docker run -d` (local).

**Tech Stack:** Python 3 stdlib (subprocess, json, time, os, re, socket, signal), `bd` CLI, `docker` CLI, existing `git-repo-setup.sh` (branch checkout).

**Design reference:** `docs/superpowers/specs/2026-08-01-beads-dispatch-design.md`

---

## File Structure

**New Files:**
- `beads-dispatch/beads_dispatch.py` — the watcher + dispatcher daemon (stdlib only)
- `beads-dispatch/README.md` — tool documentation
- `start-beads-dispatch.sh` — startup wrapper (registered as `/106-start-beads-dispatch`)
- `docs/superpowers/specs/2026-08-01-beads-dispatch-design.md` — design spec (written)
- `docs/superpowers/plans/2026-08-01-beads-dispatch-implementation.md` — this plan

**Existing Files Modified:**
- `Dockerfile` — copy `beads-dispatch.py` to `/usr/local/bin/beads-dispatch`, copy + chmod the startup script
- `master-startup.sh` — add `/106-start-beads-dispatch` to `STARTUP_SCRIPTS`
- `README.md` — document env vars, usage, compose example, troubleshooting

---

## Chunk 1: Dispatcher core (`beads-dispatch/beads_dispatch.py`)

### Task 1: Ready-set polling + seen-set diff

**Files:**
- Create: `beads-dispatch/beads_dispatch.py`

- [x] **Step 1: Implement `get_ready_issues()`** — run `bd list --ready --json` via `subprocess.run`, parse JSON, return `[{id, title, status}]`; return `None` on error (db not ready). Use the workspace cwd (default `/workspace`) and pass through `BEADS_DIR`.
- [x] **Step 2: Implement `load_state()` / `save_state()`** — read/write `state.json` (`{"seen": [ids]}`) at `BEADS_DISPATCH_STATE_DIR` (default `/config/.beads-dispatch`).
- [x] **Step 3: Implement the diff loop** — every `interval` seconds: fetch ready set; for each id not in `seen`, dispatch a worker; add to `seen`; persist. On **first run**, seed `seen` with the current ready set unless `BEADS_DISPATCH_SEED=all`.
- [x] **Step 4: Implement graceful shutdown** — handle SIGTERM/SIGINT, flush state, exit cleanly.

### Task 2: Worker dispatch

- [x] **Step 5: Implement `self_container_id()`** — read `/etc/hostname`; verify via `docker inspect <id>`; fallback to `docker ps --filter name=<hostname>`; error out if unresolvable.
- [x] **Step 6: Implement `inspect_self()`** — `docker inspect <id>` and extract image, env list, restart policy, name.
- [x] **Step 7: Implement `derive_branch_name(issue)`** — slugify title (lowercase, non-alnum → `-`, collapse, trim), return `<BEADS_DISPATCH_BRANCH_PREFIX>/<issue_id>-<slug>` (fallback to just `<prefix>/<issue_id>` if slug empty).
- [x] **Step 8: Implement `derive_git_repo_url(env, workspace)`** — return inherited `GIT_REPO_URL`, else `git -C <workspace> remote get-url origin` (via subprocess), else `None` (log warning, skip dispatch).
- [x] **Step 9: Implement `is_swarm_manager()`** — `docker info --format '{{.Swarm.LocalNodeState}}'` == `active` **and** `docker info --format '{{.Swarm.ControlAvailable}}'` == `true`.
- [x] **Step 10: Implement `compose_worker_env(parent_env, issue, branch)`** — copy parent env; set `GIT_BRANCH_NAME=<branch>`; set `GIT_REPO_URL` (inherit or derived); set `BEADS_DISPATCH=false`; drop nothing else (API keys etc. are inherited).
- [x] **Step 11: Implement `find_free_host_port(base)`** — probe candidate host ports by attempting a bind on 0.0.0.0 (python `socket`), return first free.
- [x] **Step 12: Implement `dispatch_local(worker_name, image, env, port)`** — assemble and run `docker run -d --name <worker_name> -e <k>=<v> ... -p <port>:8443 <image>`; **no volume mounts**; inherit restart policy; skip if a container with that name already exists.
- [x] **Step 13: Implement `dispatch_swarm(worker_name, image, env, port)`** — assemble and run `docker service create --name <worker_name> --detach -e <k>=<v> ... --publish published=<port>,target=8443 --restart-condition any <image>`; **no mounts**; skip if a service with that name already exists.
- [x] **Step 14: Implement `dispatch_worker(issue)`** — validate worker name (`<parent_name>-<issue_id>`, docker-safe), choose local vs swarm via `is_swarm_manager()`, dispatch, log the worker name/branch/URL.
- [x] **Step 15: Implement `main()`** — parse env/config, `--once` flag for one-shot mode (useful for testing), loop, logging to stdout.

---

## Chunk 2: Startup integration

### Task 3: Startup script

**Files:**
- Create: `start-beads-dispatch.sh`
- Modified: `master-startup.sh`

- [x] **Step 16: Create `start-beads-dispatch.sh`** — `#!/usr/bin/with-contenv bash`; skip unless `BEADS_DISPATCH=true`; verify `bd` and `docker` are on PATH and the socket exists; ensure state dir exists; launch `/usr/local/bin/beads-dispatch` **as root** (the docker socket requires root — gid 989) with `DEFAULT_WORKSPACE` passed through; write PID file. (The Step 3 loop re-checks readiness before dispatching to avoid racing a concurrent block.)
- [x] **Step 17: Add `/106-start-beads-dispatch` to `STARTUP_SCRIPTS`** in `master-startup.sh`.

### Task 4: Dockerfile

**Files:**
- Modified: `Dockerfile`

- [x] **Step 18: Copy + install the dispatcher** — `COPY beads-dispatch/beads_dispatch.py /usr/local/bin/beads-dispatch`, `COPY start-beads-dispatch.sh /106-start-beads-dispatch`, add `/106-start-beads-dispatch` to the `chmod +x` block. (No new runtime deps; stdlib-only, shells out to existing `bd` + `docker` binaries.)

---

## Chunk 3: Documentation & tests

### Task 5: README + tool docs

**Files:**
- Modified: `README.md`
- Create: `beads-dispatch/README.md`

- [x] **Step 19: Document env vars** in the README Beads section: `BEADS_DISPATCH`, `BEADS_DISPATCH_INTERVAL`, `BEADS_DISPATCH_BRANCH_PREFIX`, `BEADS_DISPATCH_SEED`, `BEADS_DISPATCH_PORT_BASE`.
- [x] **Step 20: Add usage + compose example** — show enabling the dispatcher, prerequisites (docker socket mount, `GIT_REPO_URL` or repo origin), swarm-vs-local behavior, and what a worker looks like (name, branch, URL).
- [x] **Step 21: Add troubleshooting** — check dispatcher log, state file, worker ports; and Credits.

### Task 6: Tests

**Files:**
- Create: `beads-dispatch/tests/test_beads_dispatch.py`

- [x] **Step 22: Unit-test pure functions** — branch-name derivation (slugs, empty-title fallback), seen-set diff/seed logic, worker env composition (`GIT_BRANCH_NAME` set, `BEADS_DISPATCH=false`, no `GIT_BRANCH`), worker-name sanitization.
- [x] **Step 23: Integration smoke test** (manual/scripted, documented in the tool README) — build the image, run a container with `-v /var/run/docker.sock`, `GIT_REPO_URL`, `BEADS_ENABLED=true`, `BEADS_DISPATCH=true`; create a beads issue; verify a worker appears (service on a swarm manager / container otherwise) with `GIT_BRANCH_NAME` set, on a free port, with **no volume mounts**; verify no duplicate worker on re-poll; verify a blocked issue does not dispatch.

---

## Order of execution

1. Chunk 1 (dispatcher core) → 2. Chunk 2 (startup + Dockerfile) → 3. Chunk 3 (docs + tests)
