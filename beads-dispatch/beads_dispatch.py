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
The dispatcher derives the branch name (`task/<id>-<slug>`) and passes it to the worker
via the `GIT_BRANCH_NAME` environment variable. The worker (via `git-repo-setup.sh`)
clones the repository and automatically creates the branch off the default branch (typically
`main`) if it doesn't exist, or checks it out if it does.

Dispatch mode
-------------
  * swarm manager node  -> `docker service create` (a swarm service)
  * otherwise           -> `docker run -d` (a local container)

Workers get the **docker socket mounted as their only volume** (so a replicated
container can drive the host daemon), the worker **hostname = the container name**
(derived from the task), and `BEADS_DISPATCH=false` (no recursion). No repository,
config, or data volumes are replicated — `/config` and `/workspace` stay ephemeral.

Stdlib only (no pip deps): shells out to the `bd`, `docker`, and `git` CLIs.
"""

import signal
import socket
import sys
import threading

import dispatch_utils as du

# Short-circuit expensive imports when only type-checking.
# These are only used by the worker-cloning logic, which itself only runs
# inside the daemon.
import json
import os
import pwd
import re
import shutil
import subprocess
import time

SOCKET_PATH = "/run/beads-dispatch.sock"


# --------------------------------------------------------------------------- helpers













# --------------------------------------------------------------------------- config

class Config:
    def __init__(self):
        self.workspace = du.env("DEFAULT_WORKSPACE", "/workspace")
        self.branch_prefix = du.env("BEADS_DISPATCH_BRANCH_PREFIX", "task")
        self.port_base = int(du.env("BEADS_DISPATCH_PORT_BASE", "8000"))
        self.state_dir = du.env("BEADS_DISPATCH_STATE_DIR", "/config/.beads-dispatch")
        self.worker_port = int(du.env("BEADS_DISPATCH_WORKER_PORT", "8443"))
        # Prompt to inject into worker containers. Can be overridden via BEADS_DISPATCH_PROMPT env var.
        self.dispatch_prompt = du.env("BEADS_DISPATCH_PROMPT")


def state_path(cfg):
    return os.path.join(cfg.state_dir, "state.json")


# --------------------------------------------------------------------------- beads

def get_ready_issues(workspace):
    """Return [{id, title}] for the current ready set, or None if bd is not ready."""
    rc, out, err = du.run(["bd", "list", "--ready", "--json"], cwd=workspace)
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


# --------------------------------------------------------------------------- dolt sync

def dolt_remote_add(workspace, repo_url, user):
    """Point the beads Dolt DB at <repo_url> so the db can be pushed/pulled.

    Idempotent: 'origin' is only added if it isn't already configured for the
    same URL. bd stores the remote wrapped as git+<url>; the check strips that
    prefix so /srv/x.git matches git+file:///srv/x.git and https://... matches
    git+https://....
    Returns True when the remote exists (added or already there).
    """
    rc, out, _ = du.run_as_user(user, ["bd", "dolt", "remote", "list"],
                             cwd=workspace, env=du.git_env())
    if rc == 0:
        existing = [ln.split(None, 1)[-1] if len(ln.split(None, 1)) > 1 else ln
                    for ln in out.splitlines()
                    if ln.strip() and not ln.strip().startswith("No remotes")]
        for url in existing:
            url = url.replace("git+", "", 1)
            if url == repo_url or url.rstrip("/") == repo_url.rstrip("/"):
                return True
    rc, out, err = du.run_as_user(user, ["bd", "dolt", "remote", "add", "origin", repo_url],
                               cwd=workspace, env=du.git_env())
    if rc == 0 or "already exists" in (err or "").lower() or "already exists" in (out or "").lower():
        return True
    du.log("WARNING: could not add dolt remote origin=%s: %s" % (repo_url, err or out))
    return False


def dolt_push(workspace, user):
    """Push the beads Dolt database to its git remote (syncs tasks to workers).

    Non-fatal: errors are logged but dispatch continues — a failure here means
    workers won't see the very latest task state, but the branch push (which
    already happened) is what gates the worker's repo clone.
    """
    rc, out, err = du.run_as_user(user, ["bd", "dolt", "push"],
                               cwd=workspace, env=du.git_env())
    if rc != 0:
        du.log("WARNING: bd dolt push failed: %s" % ((err or out).splitlines()[-1] if (err or out) else "unknown"))
        return False
    du.log("Pushed beads Dolt database to remote.")
    return True


# --------------------------------------------------------------------------- state



# --------------------------------------------------------------------------- self-inspection





# --------------------------------------------------------------------------- derivation



def derive_branch_name(issue, prefix):
    issue_id = issue["id"]
    slug = du.slugify(issue.get("title", ""))
    if slug:
        return "%s/%s-%s" % (prefix, issue_id, slug)
    return "%s/%s" % (prefix, issue_id)




def worker_name(issue, parent_name):
    """Derive the worker name/hostname from the issue title + id.

    Format: <slugified-title>-<issue-id> (e.g. 'update-readme-workspace-4yd').
    Falls back to <parent>-<issue-id> when the title has no slug-able content.
    Safe for both container and swarm service names: lowercase, digits, '-'.
    """
    issue_id = issue["id"]
    slug = du.slugify(issue.get("title", ""))
    if slug:
        name = "%s-%s" % (slug, issue_id)
    else:
        name = "%s-%s" % (parent_name, issue_id)
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return (name or "beads-worker")[:120]


def default_dispatch_prompt(issue_id, branch, repo_url):
    """Generate the default prompt for a worker container.

    The prompt instructs the agent to:
    1. Check beads for the task corresponding to the branch name
    2. Complete the task
    3. Commit and push changes
    4. Create a GitHub or GitLab MR (using gh/glab CLI)
    5. Update beads to mark the task as complete
    6. Push the update to beads
    """
    # Detect if it's a GitHub or GitLab repo from the URL
    is_github = "github.com" in repo_url.lower()
    is_gitlab = "gitlab.com" in repo_url.lower()

    mr_instruction = ""
    if is_github:
        mr_instruction = "Create a GitHub Pull Request using 'gh pr create' for the changes."
    elif is_gitlab:
        mr_instruction = "Create a GitLab Merge Request using 'glab mr create' for the changes."
    else:
        mr_instruction = "Create a merge/pull request using the appropriate CLI (gh or glab) for the changes."

    return (
        "You are a worker agent dispatched to complete a Beads task.\n"
        "\n"
        "Task: Issue ID %s on branch '%s'\n"
        "\n"
        "Instructions:\n"
        "1. Run 'bd list --json' to see all tasks and find the one matching this branch.\n"
        "2. Complete the task by implementing the required changes.\n"
        "3. Commit your changes and push to the branch.\n"
        "4. %s\n"
        "5. Run 'bd complete <issue-id>' to mark the task as complete in Beads.\n"
        "6. Run 'bd dolt push' to sync the Beads database with the remote.\n"
        "\n"
        "Use the appropriate CLI tools (gh for GitHub, glab for GitLab) as needed."
    ) % (issue_id, branch, mr_instruction)


def compose_worker_env(parent_env, branch, repo_url, beads_remote=None, dispatch_prompt=None):
    env = [e for e in parent_env if not e.startswith("GIT_BRANCH_NAME=")]
    env.append("GIT_BRANCH_NAME=%s" % branch)
    if repo_url:
        env = [e for e in env if not e.startswith("GIT_REPO_URL=")]
        env.append("GIT_REPO_URL=%s" % repo_url)
    env = [e for e in env if not e.startswith("BEADS_DISPATCH=")]
    env.append("BEADS_DISPATCH=false")

    # Override BEADS_ENABLED, ENABLE_SCOTTY, MR_PR_DISPATCH to false in the worker
    env = [e for e in env if not e.startswith("BEADS_ENABLED=")]
    env.append("BEADS_ENABLED=false")
    env = [e for e in env if not e.startswith("ENABLE_SCOTTY=")]
    env.append("ENABLE_SCOTTY=false")
    env = [e for e in env if not e.startswith("MR_PR_DISPATCH=")]
    env.append("MR_PR_DISPATCH=false")

    # Override HAPPIER_MODE to "agent" if parent has it set (don't add if parent doesn't have it)
    parent_has_happier_mode = any(e.startswith("HAPPIER_MODE=") for e in parent_env)
    if parent_has_happier_mode:
        env = [e for e in env if not e.startswith("HAPPIER_MODE=")]
        env.append("HAPPIER_MODE=agent")

    # BEADS_REMOTE tells the worker where to clone/pull the beads Dolt DB from.
    # Defaults to repo_url when not explicitly provided.
    remote = beads_remote or repo_url
    if remote:
        env = [e for e in env if not e.startswith("BEADS_REMOTE=")]
        env.append("BEADS_REMOTE=%s" % remote)
    # Inject the prompt if provided (or default)
    if dispatch_prompt:
        env = [e for e in env if not e.startswith("PROMPT=")]
        env.append("PROMPT=%s" % dispatch_prompt)
    return env


# --------------------------------------------------------------------------- git











def effective_hooks_dir(workspace):
    """Return the git hooks dir for the workspace, honoring core.hooksPath (set by beads)."""
    if os.path.isdir(os.path.join(workspace, ".git")):
        rc, out, _ = du.run(["git", "-C", workspace, "config", "--get", "core.hooksPath"])
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

    # Use absolute path to python3 to avoid PATH issues in git hooks
    python3_path = shutil.which("python3") or "/usr/bin/python3"
    hook = """#!/bin/sh
# Beads Dispatch post-commit hook (installed by beads-dispatch).
# Pings the dispatcher daemon so it can create workers for ready tasks.
# Non-blocking; failures are ignored so commits are never slowed or broken.
%(python)s - <<'PY'
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
""" % {"sock": socket_path, "python": python3_path}
    try:
        with open(hook_path, "w") as fh:
            fh.write(hook)
        os.chmod(hook_path, 0o755)
    except OSError as e:
        du.log("WARNING: could not install post-commit hook: %s" % e)
        return False
    du.log("Installed post-commit hook at %s" % hook_path)
    return True


# --------------------------------------------------------------------------- ports



# --------------------------------------------------------------------------- dispatch





def dispatch_worker(issue, cfg, self_info):
    """Dispatch a worker for a ready issue. Returns True when handled."""
    issue_id = issue["id"]
    worker = worker_name(issue, self_info["name"])

    # Run git operations as the owner of the workspace (e.g. abc), so the user's
    # credentials are used for dolt sync. The daemon itself runs as root (required
    # to reach the docker socket) but root typically has no git credentials.
    git_user = du.env("BEADS_DISPATCH_GIT_USER") or du.get_workspace_owner(cfg.workspace)

    branch = derive_branch_name(issue, cfg.branch_prefix)
    repo_url = du.derive_git_repo_url(self_info["env"], cfg.workspace, git_user)
    if not repo_url:
        du.log("WARNING: no GIT_REPO_URL and no git origin in %s — skipping %s"
            % (cfg.workspace, issue_id))
        return False

    # Sync the beads Dolt database (which is gitignored and NOT in the branch) so
    # the worker can see the tasks. Non-fatal: the worker still gets the repo.
    if dolt_remote_add(cfg.workspace, repo_url, git_user):
        dolt_push(cfg.workspace, git_user)
    else:
        du.log("WARNING: dolt remote could not be configured for %s — tasks may not sync." % issue_id)

    port = du.find_free_host_port(cfg.port_base)
    if port is None:
        du.log("WARNING: no free host port >= %d — skipping %s" % (cfg.port_base, issue_id))
        return False

    # Build the dispatch prompt: use override from config, or generate default
    dispatch_prompt = cfg.dispatch_prompt or default_dispatch_prompt(issue_id, branch, repo_url)

    env_vars = compose_worker_env(self_info["env"], branch, repo_url, beads_remote=repo_url,
                                  dispatch_prompt=dispatch_prompt)

    swarm = du.is_swarm_manager()
    if du.worker_exists(worker, swarm):
        du.log("Worker %s already exists for %s — skipping." % (worker, issue_id))
        return True  # treated as handled (dedup)

    if swarm:
        du.log("Swarm manager detected — dispatching service %s for %s (branch %s)"
            % (worker, issue_id, branch))
        rc, out, err = du.dispatch_swarm(worker, self_info["image"], env_vars, port,
                                      cfg.worker_port, issue_id, net=self_info)
    else:
        du.log("Local mode — dispatching container %s for %s (branch %s)"
            % (worker, issue_id, branch))
        rc, out, err = du.dispatch_local(worker, self_info["image"], env_vars, port,
                                      cfg.worker_port, self_info.get("restart_policy", ""),
                                      issue_id, net=self_info)

    if rc != 0:
        du.log("ERROR: dispatch failed for %s: %s" % (issue_id, err or out))
        return False
    du.log("Dispatched %s for %s — branch %s, http://localhost:%d"
        % (worker, issue_id, branch, port))
    return True


# --------------------------------------------------------------------------- engine

def dispatch_all(cfg, self_info, seen):
    """Dispatch a worker for every ready issue not yet seen. Returns number dispatched."""
    ready = get_ready_issues(cfg.workspace)
    if ready is None:
        du.log("bd is not ready yet (no beads database?) — skipping this trigger.")
        return 0
    dispatched = 0
    for issue in ready:
        iid = issue["id"]
        if iid in seen:
            continue
        # Re-check: the issue may have been re-blocked since the snapshot.
        fresh = {i["id"] for i in (get_ready_issues(cfg.workspace) or [])}
        if iid not in fresh:
            du.log("Issue %s is no longer ready — skipping dispatch." % iid)
            continue
        if dispatch_worker(issue, cfg, self_info):
            seen.add(iid)
            du.save_state(state_path(cfg), seen)
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
        du.log("ERROR: cannot bind %s: %s" % (SOCKET_PATH, e))
        return 1

    stop = threading.Event()
    def _sig(_signum, _frame):
        stop.set()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    du.log("Beads dispatch daemon listening on %s (workspace=%s, image=%s)"
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
        du.log("Commit trigger received — checking ready tasks.")
        try:
            dispatch_all(cfg, self_info, seen)
        except Exception as e:
            du.log("ERROR: unexpected error during dispatch: %s" % e)

    try:
        os.unlink(SOCKET_PATH)
    except OSError:
        pass
    du.log("Beads dispatch daemon stopped.")
    return 0


def main(argv):
    cfg = Config()

    if du.env("BEADS_DISPATCH") != "true":
        du.log("Beads dispatch not enabled (BEADS_DISPATCH is not 'true'). Exiting.")
        return 0

    for binary in ("bd", "docker", "git", "python3"):
        if not shutil.which(binary):
            du.log("WARNING: %s not found on PATH. Exiting." % binary)
            return 0
    if not os.path.exists("/var/run/docker.sock"):
        du.log("WARNING: /var/run/docker.sock not found. Exiting.")
        return 0

    container_id = du.self_container_id()
    self_info = du.inspect_self(container_id) if container_id else None
    if not self_info or not self_info.get("image"):
        du.log("ERROR: could not determine this container's image (is the docker socket mounted?). Exiting.")
        return 0

    seen = du.load_state(state_path(cfg))

    du.ensure_safe_directory(cfg.workspace)
    du.copy_abc_git_credentials(cfg.workspace)
    du.configure_credential_helpers()

    if "--once" in argv:
        installed = install_post_commit_hook(cfg.workspace)
        n = dispatch_all(cfg, self_info, seen)
        du.save_state(state_path(cfg), seen)
        du.log("One-shot dispatch complete (%d dispatched, hook installed=%s)." % (n, installed))
        return 0

    install_post_commit_hook(cfg.workspace)
    return run_daemon(cfg, self_info, seen)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
