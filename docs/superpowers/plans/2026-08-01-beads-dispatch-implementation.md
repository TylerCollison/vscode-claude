# Beads Dispatch Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On every git commit in the parent workspace repo, create a dispatched worker (swarm service or local container) for each currently-ready Beads task. The worker's branch is created off the just-committed HEAD and pushed — the dispatcher never commits.

**Architecture:** A Python 3 stdlib daemon (opt-in via `BEADS_DISPATCH=true`). A root daemon installs a `post-commit` hook into the workspace repo and listens on a unix socket. The hook (runs as `abc`) pings the socket; the daemon reads the ready set (`bd list --ready --json`), and for each unseen ready task: `git checkout -b` (off HEAD), `git push`, restore the original branch, then dispatch via `docker service create` (swarm manager) or `docker run -d`.

**Tech Stack:** Python 3 stdlib (subprocess, json, socket, signal, re), `bd` CLI, `docker` CLI, git, existing `git-repo-setup.sh`.

**Design reference:** `docs/superpowers/specs/2026-08-01-beads-dispatch-design.md`

---

## File Structure

**New Files:**
- `beads-dispatch/beads_dispatch.py` — the daemon (socket bridge + dispatch engine)
- `beads-dispatch/README.md` — tool documentation
- `start-beads-dispatch.sh` — startup wrapper (registered as `/106-start-beads-dispatch`)
- `docs/superpowers/specs/2026-08-01-beads-dispatch-design.md` — design spec
- `docs/superpowers/plans/2026-08-01-beads-dispatch-implementation.md` — this plan
- `beads-dispatch/tests/test_beads_dispatch.py` — unit tests

**Existing Files Modified:**
- `Dockerfile` — copy the dispatcher + startup script
- `master-startup.sh` — add `/106-start-beads-dispatch`
- `README.md` — document env vars, usage, troubleshooting

---

## Chunk 1: Dispatcher daemon (`beads-dispatch/beads_dispatch.py`)

### Task 1: Dispatch engine (unchanged core logic)

**Files:**
- Create: `beads-dispatch/beads_dispatch.py`

- [x] **Step 1: Implement `get_ready_issues(workspace)`** — `bd list --ready --json`, return `[{id, title}]` or `None` on error.
- [x] **Step 2: Implement `load_state()` / `save_state()`** — seen-set at `BEADS_DISPATCH_STATE_DIR` (default `/config/.beads-dispatch`).
- [x] **Step 3: Implement `self_container_id()`** — `/etc/hostname` → verify via `docker inspect`; fallback to cgroup parse.
- [x] **Step 4: Implement `inspect_self()`** — extract image, env, restart policy, name.
- [x] **Step 5: Implement `derive_branch_name(issue, prefix)`** — slugified `<prefix>/<id>-<slug>`.
- [x] **Step 6: Implement `derive_git_repo_url(parent_env, workspace)`** — `GIT_REPO_URL` env, else `git remote get-url origin`.
- [x] **Step 7: Implement `is_swarm_manager()`** — `docker info` `LocalNodeState`/`ControlAvailable`.
- [x] **Step 8: Implement `find_free_host_port(base)`** — socket bind probe.
- [x] **Step 9: Implement `compose_worker_env(parent_env, branch, repo_url)`** — copy env, set `GIT_BRANCH_NAME`, ensure `GIT_REPO_URL`, set `BEADS_DISPATCH=false`.
- [x] **Step 10: Implement `worker_name(parent, issue_id)`** — docker/service-safe slug.
- [x] **Step 11: Implement `dispatch_local(...)`** — `docker run -d`, no mounts, publish port, label `beads.task`.
- [x] **Step 12: Implement `dispatch_swarm(...)`** — `docker service create --detach`, no mounts, `--publish published=<p>,target=8443`, `--restart-condition any`, label `beads.task`.

### Task 2: Commit-trigger plumbing (new)

- [x] **Step 13: Implement `git_current_branch(workspace)`** — `git branch --show-current` (or detached HEAD SHA).
- [x] **Step 14: Implement `branch_exists_remote(workspace, branch, repo_url)`** — `git ls-remote <repo_url> refs/heads/<branch>`.
- [x] **Step 15: Implement `push_task_branch(workspace, branch, repo_url)`** — with `GIT_TERMINAL_PROMPT=0`:
  1. remember original branch;
  2. if the branch already exists in origin → return "exists" (skip create/push);
  3. `git checkout -b <branch>` (off HEAD — **no commit**);
  4. `git push -u origin <branch>` (or to `<repo_url>` when it differs from origin);
  5. `git checkout <original>` to restore;
  6. on failure, restore the original branch and return failure.
- [x] **Step 16: Implement `install_post_commit_hook(workspace)`** — back up an existing `post-commit` to `post-commit.beads-dispatch.bak`; write a tiny hook that pings `/run/beads-dispatch.sock` via a one-liner (python3, non-blocking, ignore errors); chmod +x.
- [x] **Step 17: Implement the socket daemon** — create `/run/beads-dispatch.sock` (mode 0666), listen; on each connection, drain the trigger and run `dispatch_all()`.
- [x] **Step 18: Implement `dispatch_all(cfg, self_info, seen)`** — for each ready issue not in `seen`: re-check ready, `push_task_branch` (fail ⇒ log, mark seen, skip), `find_free_host_port`, detect swarm, dispatch; mark seen + persist.
- [x] **Step 19: Implement `main(argv)`** — modes: `--daemon` (install hook, run socket listener); `--once` (run `dispatch_all()` once, useful for testing/manual).

---

## Chunk 2: Startup integration

### Task 3: Startup script

**Files:**
- Create: `start-beads-dispatch.sh`
- Modified: `master-startup.sh`

- [x] **Step 20: Create `start-beads-dispatch.sh`** — `#!/usr/bin/with-contenv bash`; skip unless `BEADS_DISPATCH=true`; verify `bd`/`docker`/`python3` on PATH and the socket is mounted; ensure the state dir exists; launch `/usr/local/bin/beads-dispatch --daemon` **as root**; write PID file; log.
- [x] **Step 21: Add `/106-start-beads-dispatch` to `STARTUP_SCRIPTS`** in `master-startup.sh`.

### Task 4: Dockerfile

**Files:**
- Modified: `Dockerfile`

- [x] **Step 22: Copy + install** — `COPY beads-dispatch/beads_dispatch.py /usr/local/bin/beads-dispatch`, `COPY start-beads-dispatch.sh /106-start-beads-dispatch`, add both to `chmod +x`.

---

## Chunk 3: Documentation & tests

### Task 5: README + tool docs

**Files:**
- Modified: `README.md`
- Create: `beads-dispatch/README.md`

- [x] **Step 23: Document env vars** — `BEADS_DISPATCH`, `BEADS_DISPATCH_BRANCH_PREFIX`, `BEADS_DISPATCH_PORT_BASE`, `BEADS_DISPATCH_WORKER_PORT`, `BEADS_DISPATCH_STATE_DIR` (and note the removed `INTERVAL`/`SEED`).
- [x] **Step 24: Usage + compose example** — enable `BEADS_DISPATCH=true`, prerequisites (docker socket, `GIT_REPO_URL` or origin), commit-driven behavior, swarm-vs-local, what a worker looks like.
- [x] **Step 25: Troubleshooting + Credits** — check the daemon log, state file, worker ports; list beads-dispatch.

### Task 6: Tests

**Files:**
- Create: `beads-dispatch/tests/test_beads_dispatch.py`

- [x] **Step 26: Unit-test pure functions** — branch derivation, worker-name sanitization, env composition (`GIT_BRANCH_NAME` set, `BEADS_DISPATCH=false`, no `GIT_BRANCH`), seen-set diff/seed, port scan.
- [x] **Step 27: Integration smoke test** (scripted, documented in the tool README) — build the image; run a parent with `-v /var/run/docker.sock`, `GIT_REPO_URL`, `BEADS_ENABLED=true`, `BEADS_DISPATCH=true`; create a beads task; commit a change; verify a worker appears (service on swarm manager / container otherwise) with `GIT_BRANCH_NAME` set, branch pushed to origin, on a free port, with **no volume mounts**; verify a second commit does not duplicate the worker; verify a blocked task does not dispatch.

---

## Order of execution

1. Chunk 1 (dispatch engine + commit trigger) → 2. Chunk 2 (startup + Dockerfile) → 3. Chunk 3 (docs + tests)
