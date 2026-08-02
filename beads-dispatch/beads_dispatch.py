#!/usr/bin/env python3
"""Beads Dispatch — dispatch a worker container/service when a Beads task moves to ready.

Polls `bd list --ready --json`, diffs against a persisted seen-set, and for each
newly-ready issue starts a worker from the *same image* with `GIT_BRANCH_NAME` set
to a branch named after the task.

Workers mount **no volumes** — they run on an ephemeral filesystem and the existing
`git-repo-setup.sh` startup script clones `GIT_REPO_URL` and checks out the branch on
first boot.

Dispatch mode:
  * swarm manager node  -> `docker service create` (a swarm service)
  * otherwise           -> `docker run -d` (a local container)

Stdlib only (no pip deps): shells out to the `bd` and `docker` CLIs.
"""

import json
import os
import re
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time

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
        self.interval = int(env("BEADS_DISPATCH_INTERVAL", "30"))
        self.branch_prefix = env("BEADS_DISPATCH_BRANCH_PREFIX", "task")
        self.seed = env("BEADS_DISPATCH_SEED", "skip")
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
    """Return this container's id (short), resolved via /etc/hostname + docker inspect."""
    try:
        with open("/etc/hostname") as fh:
            host = fh.read().strip()
    except OSError:
        host = ""
    if host:
        rc, _, _ = run(["docker", "inspect", host, "--format", "{{.Id}}"])
        if rc == 0:
            return host
        rc, out, _ = run(["docker", "ps", "-q", "--filter", "name=%s" % host])
        if rc == 0 and out:
            return out.splitlines()[0]
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
    """Inspect this container via the docker API; return the fields we need to clone."""
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
    # (no dots/underscores, no leading/trailing '-')
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
    """Dispatch a worker for a newly-ready issue. Returns True when handled."""
    issue_id = issue["id"]
    worker = worker_name(self_info["name"], issue_id)

    branch = derive_branch_name(issue, cfg.branch_prefix)
    repo_url = derive_git_repo_url(self_info["env"], cfg.workspace)
    if not repo_url:
        log("WARNING: no GIT_REPO_URL set and no git origin in %s — skipping %s"
            % (cfg.workspace, issue_id))
        return False

    env = compose_worker_env(self_info["env"], branch, repo_url)
    port = find_free_host_port(cfg.port_base)
    if port is None:
        log("WARNING: no free host port >= %d — skipping %s" % (cfg.port_base, issue_id))
        return False

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


# --------------------------------------------------------------------------- main loop

def run_once(cfg, self_info, seen):
    ready = get_ready_issues(cfg.workspace)
    if ready is None:
        return
    for issue in ready:
        iid = issue["id"]
        if iid in seen:
            continue
        # The issue may have been re-blocked since this poll snapshot began
        # (dolt auto-commit is off by default, so the ready set can race with
        # writes). Re-verify against a fresh query immediately before dispatch.
        if iid not in {i["id"] for i in (get_ready_issues(cfg.workspace) or [])}:
            log("Issue %s is no longer ready — skipping dispatch." % iid)
            continue
        if dispatch_worker(issue, cfg, self_info):
            seen.add(iid)
            save_state(cfg, seen)


def main(argv):
    cfg = Config()

    if env("BEADS_DISPATCH") != "true":
        log("Beads dispatch not enabled (BEADS_DISPATCH is not 'true'). Exiting.")
        return 0

    for binary in ("bd", "docker", "git"):
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
    first_run = not os.path.exists(state_path(cfg))
    if first_run and cfg.seed != "all":
        log("First run: seeding seen set with current ready issues (BEADS_DISPATCH_SEED=skip).")
        run_once_seed(cfg, seen)
        save_state(cfg, seen)

    if "--once" in argv:
        run_once(cfg, self_info, seen)
        save_state(cfg, seen)
        return 0

    stop = threading.Event()
    def _sig(_signum, _frame):
        stop.set()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    log("Beads dispatch watcher started (interval=%ss, workspace=%s, image=%s)"
        % (cfg.interval, cfg.workspace, self_info["image"]))
    while not stop.is_set():
        try:
            run_once(cfg, self_info, seen)
        except Exception as e:  # keep the loop alive on unexpected errors
            log("ERROR: unexpected error in poll cycle: %s" % e)
        stop.wait(cfg.interval)

    log("Beads dispatch watcher stopped.")
    return 0


def run_once_seed(cfg, seen):
    """On first run with seed=skip, mark current ready issues as already seen."""
    ready = get_ready_issues(cfg.workspace)
    if ready:
        for issue in ready:
            seen.add(issue["id"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
