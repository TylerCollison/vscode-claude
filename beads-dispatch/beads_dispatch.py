#!/usr/bin/env python3
"""Beads Dispatch — dispatch a worker container/service when a task is ready and a commit happens.

Trigger model
-------------
Dispatch is triggered by a git **post-commit** hook, not a poll loop. Every commit in the
workspace repo causes the dispatcher to re-check `bd list --ready --json` and create a worker
for each currently-ready task that hasn't been dispatched yet.

Privilege bridge
----------------
Git hooks run as the committer (the `abc` user), but docker (via the mounted host socket) needs
root. So a root daemon listens on `/run/beads-dispatch.sock`; the post-commit hook (as `abc`)
just pings the socket. The daemon does the dispatch work as root. This is event-driven — no
polling.

Branch creation
---------------
For each ready task the daemon:
  1. `git checkout -b <task-branch>` off the **current HEAD** (the state that was just committed),
  2. `git push` the branch to origin,
  3. `git checkout <original-branch>` to restore the parent's working state.

The dispatcher never commits anything — the triggering commit IS the state the worker pulls.

Dispatch mode
-------------
  * swarm manager node  -> `docker service create` (a swarm service)
  * otherwise           -> `docker run -d` (a local container)

Workers mount **no volumes** (ephemeral) and get `BEADS_DISPATCH=false` (no recursion).

Stdlib only (no pip deps): shells out to the `bd`, `docker`, and `git` CLIs.
"""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

SOCKET_PATH = "/run/beads-dispatch.sock"


# --------------------------------------------------------------------------- helpers

def log(msg):
    print("%s - %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg), flush=True)


def run(cmd, **kwargs):
    """Run a command, return (returncode, stdout, stderr)."""
    proc = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def env(name, default=None):
    return os.environ.get(name, default)


# --------------------------------------------------------------------------- config

class Config:
    def __init__(self):
        self.workspace = env("DEFAULT_WORKSPACE", "/workspace")
        self.branch_prefix = env("BEADS_DISPATCH_BRANCH_PREFIX", "task")
        self.port_base = int(env("BEADS_DISPATCH_PORT_BASE", "8000"))
        self.state_dir = env("BEADS_DISPATCH_STATE_DIR", "/config/.beads-dispatch")
        self.worker_port = int(env("BEADS_DISPATCH_WORKER_PORT", "8443"))


def state_path(cfg):
    return os.path.join(cfg.state_dir, "state.json")


# --------------------------------------------------------------------------- beads

def get_ready_issues(workspace):
    """Return [{id, title}] for the current ready set, or None if bd is not ready."""
    rc, out, err = run(["bd", "list", "--ready", "--json"], cwd=workspace)
    if rc != 0:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    return [
        {"id": item.get("id", ""), "title": item.get("title", "")}
        for item in data
        if item.get("id")
    ]


# --------------------------------------------------------------------------- state

def load_state(cfg):
    try:
        with open(state_path(cfg)) as fh:
            data = json.load(fh)
        return set(data.get("seen", []))
    except (OSError, ValueError):
        return set()


def save_state(cfg, seen):
    try:
        os.makedirs(cfg.state_dir, exist_ok=True)
        tmp = state_path(cfg) + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"seen": sorted(seen)}, fh)
        os.replace(tmp, state_path(cfg))
    except OSError as e:
        log("WARNING: could not persist state: %s" % e)


# --------------------------------------------------------------------------- self-inspection

def self_container_id():
    """Return this container's short id (via /etc/hostname + docker inspect)."""
    try:
        with open("/etc/hostname") as fh:
            host = fh.read().strip()
    except OSError:
        host = ""
    if host:
        rc, _, _ = run(["docker", "inspect", host, "--format", "{{.Id}}"])
        if rc == 0:
            return host
    try:
        with open("/proc/self/cgroup") as fh:
            for line in fh:
                m = re.search(r"[0-9a-f]{64}", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def inspect_self(container_id):
    """Inspect this container; return the fields needed to clone it."""
    rc, out, err = run(["docker", "inspect", container_id])
    if rc != 0:
        return None
    try:
        data = json.loads(out)[0]
    except (IndexError, ValueError):
        return None
    return {
        "image": (data.get("Config") or {}).get("Image"),
        "env": (data.get("Config") or {}).get("Env", []),
        "name": (data.get("Name") or "").lstrip("/"),
        "restart_policy": (data.get("HostConfig") or {}).get("RestartPolicy", {}).get("Name", ""),
    }


def is_swarm_manager():
    """True when running on a swarm manager node (docker service create is possible)."""
    rc, state, _ = run(["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"])
    if rc != 0 or state != "active":
        return False
    rc, ctrl, _ = run(["docker", "info", "--format", "{{.Swarm.ControlAvailable}}"])
    return rc == 0 and ctrl == "true"


# --------------------------------------------------------------------------- derivation

def slugify(text):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug


def derive_branch_name(issue, prefix):
    issue_id = issue["id"]
    slug = slugify(issue.get("title", ""))
    if slug:
        return "%s/%s-%s" % (prefix, issue_id, slug)
    return "%s/%s" % (prefix, issue_id)


def derive_git_repo_url(parent_env, workspace):
    for e in parent_env:
        if e.startswith("GIT_REPO_URL="):
            val = e.split("=", 1)[1]
            if val:
                return val
    rc, out, _ = run(["git", "-C", workspace, "remote", "get-url", "origin"])
    return out if rc == 0 and out else None


def worker_name(parent_name, issue_id):
    name = "%s-%s" % (parent_name, issue_id)
    # Safe for both container and swarm service names: lowercase, digits, '-'
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return (name or "beads-worker")[:120]


def compose_worker_env(parent_env, branch, repo_url):
    env = [e for e in parent_env if not e.startswith("GIT_BRANCH_NAME=")]
    env.append("GIT_BRANCH_NAME=%s" % branch)
    if repo_url:
        env = [e for e in env if not e.startswith("GIT_REPO_URL=")]
        env.append("GIT_REPO_URL=%s" % repo_url)
    env = [e for e in env if not e.startswith("BEADS_DISPATCH=")]
    env.append("BEADS_DISPATCH=false")
    return env


# --------------------------------------------------------------------------- git

def git_current_branch(workspace):
    rc, out, _ = run(["git", "-C", workspace, "branch", "--show-current"])
    if rc == 0 and out:
        return out
    # detached HEAD -> return the commit sha
    rc, out, _ = run(["git", "-C", workspace, "rev-parse", "HEAD"])
    return out if rc == 0 and out else None


def branch_exists_remote(workspace, branch, repo_url):
    rc, out, _ = run(["git", "-C", workspace, "ls-remote", repo_url,
                      "refs/heads/%s" % branch], env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    return rc == 0 and bool(out.strip())


def push_task_branch(workspace, branch, repo_url):
    """Create <branch> off the current HEAD, push it, restore the original branch.

    Returns: True (pushed), "exists" (branch already in origin — nothing to push),
    or False (failed; original branch restored).
    """
    original = git_current_branch(workspace)
    if not original:
        log("ERROR: cannot determine current git branch in %s" % workspace)
        return False

    if branch_exists_remote(workspace, branch, repo_url):
        log("Branch %s already exists in origin — skipping create/push." % branch)
        return "exists"

    git_env = dict(os.environ, GIT_TERMINAL_PROMPT="0")

    def restore():
        try:
            run(["git", "-C", workspace, "checkout", original], env=git_env)
        except Exception:
            pass

    # 1. Create the branch off current HEAD (no commit).
    rc, out, err = run(["git", "-C", workspace, "checkout", "-b", branch], env=git_env)
    if rc != 0:
        log("ERROR: git checkout -b %s failed: %s" % (branch, err or out))
        return False

    # 2. Determine the push target: origin if it matches repo_url, else repo_url.
    rc, origin, _ = run(["git", "-C", workspace, "remote", "get-url", "origin"])
    if rc == 0 and origin == repo_url:
        push_cmd = ["git", "-C", workspace, "push", "-u", "origin", branch]
    else:
        push_cmd = ["git", "-C", workspace, "push", repo_url, "%s:%s" % (branch, branch)]

    rc, out, err = run(push_cmd, env=git_env)
    restore()
    if rc != 0:
        log("ERROR: git push of %s failed: %s (is the parent configured to push to %s?)"
            % (branch, (err or out).splitlines()[-1] if (err or out) else "unknown", repo_url))
        return False
    log("Pushed branch %s to %s" % (branch, repo_url))
    return True


def ensure_safe_directory(workspace):
    """Allow git-as-root to operate on the workspace repo (which is abc-owned).

    Git 2.35+ refuses to run in a repo owned by another user (dubious ownership).
    The dispatcher runs git as root but the workspace is owned by the `abc` user,
    so add the workspace to root's safe.directory list (idempotent).
    """
    rc, out, _ = run(["git", "config", "--global", "--get-all", "safe.directory"])
    if rc == 0 and workspace in out.splitlines():
        return
    run(["git", "config", "--global", "--add", "safe.directory", workspace])


def effective_hooks_dir(workspace):
    """Return the git hooks dir for the workspace, honoring core.hooksPath (set by beads)."""
    if os.path.isdir(os.path.join(workspace, ".git")):
        rc, out, _ = run(["git", "-C", workspace, "config", "--get", "core.hooksPath"])
        if rc == 0 and out:
            hooks = out if os.path.isabs(out) else os.path.join(workspace, out)
            if os.path.isdir(hooks):
                return hooks
    return os.path.join(workspace, ".git", "hooks")


def install_post_commit_hook(workspace, socket_path=SOCKET_PATH):
    """Install a post-commit hook that pings the dispatcher socket (non-blocking).

    Installs into the effective hooks dir (beads sets core.hooksPath to
    .beads/hooks), backing up any existing post-commit.
    """
    if not os.path.isdir(os.path.join(workspace, ".git")):
        return False
    hooks_dir = effective_hooks_dir(workspace)
    os.makedirs(hooks_dir, exist_ok=True)
    hook_path = os.path.join(hooks_dir, "post-commit")

    backup = hook_path + ".beads-dispatch.bak"
    if os.path.exists(hook_path) and not os.path.exists(backup):
        shutil.copy2(hook_path, backup)

    hook = """#!/bin/sh
# Beads Dispatch post-commit hook (installed by beads-dispatch).
# Pings the dispatcher daemon so it can create workers for ready tasks.
# Non-blocking; failures are ignored so commits are never slowed or broken.
command -v python3 >/dev/null 2>&1 || exit 0
python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(0.5)
    s.connect("%(sock)s")
    s.sendall(b"commit")
    s.close()
except Exception:
    pass
PY
""" % {"sock": socket_path}
    try:
        with open(hook_path, "w") as fh:
            fh.write(hook)
        os.chmod(hook_path, 0o755)
    except OSError as e:
        log("WARNING: could not install post-commit hook: %s" % e)
        return False
    log("Installed post-commit hook at %s" % hook_path)
    return True


# --------------------------------------------------------------------------- ports

def used_host_ports():
    """Collect host ports already published by docker containers/services."""
    used = set()
    rc, out, _ = run(["docker", "ps", "-a", "--format", "{{.Ports}}"])
    if rc == 0:
        for line in out.splitlines():
            for m in re.finditer(r":(\d+)->", line):
                used.add(int(m.group(1)))
    rc, out, _ = run(["docker", "service", "ls", "--format", "{{.Ports}}"])
    if rc == 0:
        for line in out.splitlines():
            for m in re.finditer(r":(\d+)->", line):
                used.add(int(m.group(1)))
    return used


def find_free_host_port(base):
    used = used_host_ports()
    for port in range(base, base + 1000):
        if port not in used:
            return port
    return None


# --------------------------------------------------------------------------- dispatch

def worker_exists(name, swarm):
    if swarm:
        rc, _, _ = run(["docker", "service", "inspect", name])
    else:
        rc, _, _ = run(["docker", "inspect", name])
    return rc == 0


def dispatch_local(worker, image, env, port, worker_port, restart_policy, issue_id):
    cmd = ["docker", "run", "-d", "--name", worker, "-l", "beads.task=%s" % issue_id]
    if restart_policy and restart_policy not in ("", "no"):
        cmd += ["--restart", restart_policy]
    for e in env:
        cmd += ["-e", e]
    cmd += ["-p", "%d:%d" % (port, worker_port), image]
    return run(cmd)


def dispatch_swarm(worker, image, env, port, worker_port, issue_id):
    cmd = [
        "docker", "service", "create",
        "--name", worker,
        "--detach",
        "--label", "beads.task=%s" % issue_id,
        "--restart-condition", "any",
    ]
    for e in env:
        cmd += ["-e", e]
    cmd += ["--publish", "published=%d,target=%d" % (port, worker_port), image]
    return run(cmd)


def dispatch_worker(issue, cfg, self_info):
    """Dispatch a worker for a ready issue. Returns True when handled."""
    issue_id = issue["id"]
    worker = worker_name(self_info["name"], issue_id)

    branch = derive_branch_name(issue, cfg.branch_prefix)
    repo_url = derive_git_repo_url(self_info["env"], cfg.workspace)
    if not repo_url:
        log("WARNING: no GIT_REPO_URL and no git origin in %s — skipping %s"
            % (cfg.workspace, issue_id))
        return False

    # Push the task branch so the worker can clone/check it out.
    push_result = push_task_branch(cfg.workspace, branch, repo_url)
    if push_result is False:
        log("ERROR: could not push branch for %s — skipping dispatch." % issue_id)
        return False

    port = find_free_host_port(cfg.port_base)
    if port is None:
        log("WARNING: no free host port >= %d — skipping %s" % (cfg.port_base, issue_id))
        return False

    env = compose_worker_env(self_info["env"], branch, repo_url)

    swarm = is_swarm_manager()
    if worker_exists(worker, swarm):
        log("Worker %s already exists for %s — skipping." % (worker, issue_id))
        return True  # treated as handled (dedup)

    if swarm:
        log("Swarm manager detected — dispatching service %s for %s (branch %s)"
            % (worker, issue_id, branch))
        rc, out, err = dispatch_swarm(worker, self_info["image"], env, port,
                                      cfg.worker_port, issue_id)
    else:
        log("Local mode — dispatching container %s for %s (branch %s)"
            % (worker, issue_id, branch))
        rc, out, err = dispatch_local(worker, self_info["image"], env, port,
                                      cfg.worker_port, self_info.get("restart_policy", ""),
                                      issue_id)

    if rc != 0:
        log("ERROR: dispatch failed for %s: %s" % (issue_id, err or out))
        return False
    log("Dispatched %s for %s — branch %s, http://localhost:%d"
        % (worker, issue_id, branch, port))
    return True


# --------------------------------------------------------------------------- engine

def dispatch_all(cfg, self_info, seen):
    """Dispatch a worker for every ready issue not yet seen. Returns number dispatched."""
    ready = get_ready_issues(cfg.workspace)
    if ready is None:
        log("bd is not ready yet (no beads database?) — skipping this trigger.")
        return 0
    dispatched = 0
    for issue in ready:
        iid = issue["id"]
        if iid in seen:
            continue
        # Re-check: the issue may have been re-blocked since the snapshot.
        fresh = {i["id"] for i in (get_ready_issues(cfg.workspace) or [])}
        if iid not in fresh:
            log("Issue %s is no longer ready — skipping dispatch." % iid)
            continue
        if dispatch_worker(issue, cfg, self_info):
            seen.add(iid)
            save_state(cfg, seen)
            dispatched += 1
    return dispatched


def run_daemon(cfg, self_info, seen):
    """Listen on the unix socket; on each trigger, dispatch ready tasks."""
    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass
    try:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)
        srv.listen(16)
    except OSError as e:
        log("ERROR: cannot bind %s: %s" % (SOCKET_PATH, e))
        return 1

    stop = threading.Event()
    def _sig(_signum, _frame):
        stop.set()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    log("Beads dispatch daemon listening on %s (workspace=%s, image=%s)"
        % (SOCKET_PATH, cfg.workspace, self_info["image"]))
    srv.settimeout(1.0)
    while not stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            if stop.is_set():
                break
            continue
        with conn:
            try:
                conn.recv(64)
            except Exception:
                pass
        log("Commit trigger received — checking ready tasks.")
        try:
            dispatch_all(cfg, self_info, seen)
        except Exception as e:
            log("ERROR: unexpected error during dispatch: %s" % e)

    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass
    log("Beads dispatch daemon stopped.")
    return 0


def main(argv):
    cfg = Config()

    if env("BEADS_DISPATCH") != "true":
        log("Beads dispatch not enabled (BEADS_DISPATCH is not 'true'). Exiting.")
        return 0

    for binary in ("bd", "docker", "git", "python3"):
        if not shutil.which(binary):
            log("WARNING: %s not found on PATH. Exiting." % binary)
            return 0
    if not os.path.exists("/var/run/docker.sock"):
        log("WARNING: /var/run/docker.sock not found. Exiting.")
        return 0

    container_id = self_container_id()
    self_info = inspect_self(container_id) if container_id else None
    if not self_info or not self_info.get("image"):
        log("ERROR: could not determine this container's image (is the docker socket mounted?). Exiting.")
        return 0

    seen = load_state(cfg)

    ensure_safe_directory(cfg.workspace)

    if "--once" in argv:
        installed = install_post_commit_hook(cfg.workspace)
        n = dispatch_all(cfg, self_info, seen)
        save_state(cfg, seen)
        log("One-shot dispatch complete (%d dispatched, hook installed=%s)." % (n, installed))
        return 0

    install_post_commit_hook(cfg.workspace)
    return run_daemon(cfg, self_info, seen)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
