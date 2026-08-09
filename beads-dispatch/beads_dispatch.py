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

Workers get the **docker socket mounted as their only volume** (so a replicated
container can drive the host daemon), the worker **hostname = the container name**
(derived from the task), and `BEADS_DISPATCH=false` (no recursion). No repository,
config, or data volumes are replicated — `/config` and `/workspace` stay ephemeral.

Stdlib only (no pip deps): shells out to the `bd`, `docker`, and `git` CLIs.
"""

import json
import os
import pwd
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


def run_as_user(user, cmd, **kwargs):
    """Run a command as a specific user (via sudo -u), falling back to root.

    Returns (rc, stdout, stderr) — same contract as run().
    """
    try:
        uid = pwd.getpwnam(user).pw_uid
        home = pwd.getpwnam(user).pw_dir
    except KeyError:
        uid = None
        home = "/home/%s" % user
    # Already running as that user -> run directly (no sudo).
    if uid is not None and os.geteuid() == uid:
        return run(cmd, **kwargs)
    # If sudo is unavailable, fall back to running as root with the credential
    # files that copy_abc_git_credentials() placed in /root.
    if not shutil.which("sudo"):
        return run(cmd, **kwargs)
    # Ensure HOME points at the target user's home so git finds that user's
    # credential helper (gh, .gitconfig, .netrc), ssh keys, etc. sudo -E preserves
    # the parent env (including our HOME override) when running as root.
    kwargs["env"] = dict(kwargs.get("env") or os.environ)
    kwargs["env"]["HOME"] = home
    # -n: never prompt for a password (root can sudo -u without one; if it would
    # prompt, fail fast rather than hang the dispatcher).
    sudo_cmd = ["sudo", "-n", "-u", user, "-E", "--"] + cmd
    return run(sudo_cmd, **kwargs)


def get_workspace_owner(workspace):
    """Return the username that owns the workspace directory.

    Prefer a non-root owner: the root-owned fallback almost always means the
    workspace was provisioned by an init script before the user chown pass,
    and root has no git credentials. If the workspace is root-owned, fall back
    to the first non-root user with a shell (e.g. abc) so git runs as the user
    who actually has credentials.
    """
    candidates = []
    try:
        st = os.stat(workspace)
        candidates.append(pwd.getpwuid(st.st_uid).pw_name)
    except Exception:
        pass
    for username in ("abc", "coder", "user"):
        try:
            if pwd.getpwnam(username).pw_uid not in (0, 65534):
                candidates.append(username)
        except (KeyError, TypeError):
            pass
    for name in candidates:
        if name != "root":
            return name
    return candidates[0] if candidates else "abc"


def env(name, default=None):
    return os.environ.get(name, default)


def git_env():
    """Build the environment for git subprocesses (no prompts, CLIs ready).

    Both gh (GitHub) and glab (GitLab) have a preferred token env var and a
    fallback alias; normalize so whichever is set is visible to both the helper
    and git itself.
    """
    e = dict(os.environ)
    e["GIT_TERMINAL_PROMPT"] = "0"
    token_pairs = (
        ("GH_TOKEN", "GITHUB_TOKEN"),
        ("GITHUB_TOKEN", "GH_TOKEN"),
        ("GITLAB_TOKEN", "GITLAB_ACCESS_TOKEN"),
        ("GITLAB_ACCESS_TOKEN", "GITLAB_TOKEN"),
        ("GITLAB_TOKEN", "OAUTH_TOKEN"),
    )
    for k, v in token_pairs:
        if not e.get(k) and e.get(v):
            e[k] = e[v]
    return e


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


# --------------------------------------------------------------------------- dolt sync

def dolt_remote_add(workspace, repo_url, user):
    """Point the beads Dolt DB at <repo_url> so the db can be pushed/pulled.

    Idempotent: 'origin' is only added if it isn't already configured for the
    same URL. bd stores the remote wrapped as git+<url>; the check strips that
    prefix so /srv/x.git matches git+file:///srv/x.git and https://... matches
    git+https://....
    Returns True when the remote exists (added or already there).
    """
    rc, out, _ = run_as_user(user, ["bd", "dolt", "remote", "list"],
                             cwd=workspace, env=git_env())
    if rc == 0:
        existing = [ln.split(None, 1)[-1] if len(ln.split(None, 1)) > 1 else ln
                    for ln in out.splitlines()
                    if ln.strip() and not ln.strip().startswith("No remotes")]
        for url in existing:
            url = url.replace("git+", "", 1)
            if url == repo_url or url.rstrip("/") == repo_url.rstrip("/"):
                return True
    rc, out, err = run_as_user(user, ["bd", "dolt", "remote", "add", "origin", repo_url],
                               cwd=workspace, env=git_env())
    if rc == 0 or "already exists" in (err or "").lower() or "already exists" in (out or "").lower():
        return True
    log("WARNING: could not add dolt remote origin=%s: %s" % (repo_url, err or out))
    return False


def dolt_push(workspace, user):
    """Push the beads Dolt database to its git remote (syncs tasks to workers).

    Non-fatal: errors are logged but dispatch continues — a failure here means
    workers won't see the very latest task state, but the branch push (which
    already happened) is what gates the worker's repo clone.
    """
    rc, out, err = run_as_user(user, ["bd", "dolt", "push"],
                               cwd=workspace, env=git_env())
    if rc != 0:
        log("WARNING: bd dolt push failed: %s" % ((err or out).splitlines()[-1] if (err or out) else "unknown"))
        return False
    log("Pushed beads Dolt database to remote.")
    return True


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


def derive_git_repo_url(parent_env, workspace, user=None):
    # First check the environment variable
    env_url = None
    for e in parent_env:
        if e.startswith("GIT_REPO_URL="):
            val = e.split("=", 1)[1]
            if val:
                env_url = val
                break

    # Get the git remote URL
    if user:
        rc, out, _ = run_as_user(user, ["git", "-C", workspace, "remote", "get-url", "origin"])
    else:
        rc, out, _ = run(["git", "-C", workspace, "remote", "get-url", "origin"])
    git_url = out if rc == 0 and out else None

    # If git URL has credentials (contains @), prefer it over env URL
    # Credentials in git URL look like: https://user:pass@host/... or git@host:...
    if git_url and "@" in git_url:
        # Check if the @ is before a / or : (i.e., in the credential part, not in the path)
        if git_url.startswith("https://") or git_url.startswith("http://"):
            # https://user:pass@host/path - @ before first /
            at_idx = git_url.find("@")
            slash_idx = git_url.find("/", 8)  # after https://
            if at_idx > 0 and at_idx < slash_idx:
                return git_url
        elif git_url.startswith("git@") or git_url.startswith("ssh://"):
            # git@host:path or ssh://user@host/path - has credentials
            return git_url

    # Fall back to env URL if available, then git URL
    return env_url or git_url


def worker_name(parent_name, issue_id):
    name = "%s-%s" % (parent_name, issue_id)
    # Safe for both container and swarm service names: lowercase, digits, '-'
    name = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    return (name or "beads-worker")[:120]


def compose_worker_env(parent_env, branch, repo_url, beads_remote=None):
    env = [e for e in parent_env if not e.startswith("GIT_BRANCH_NAME=")]
    env.append("GIT_BRANCH_NAME=%s" % branch)
    if repo_url:
        env = [e for e in env if not e.startswith("GIT_REPO_URL=")]
        env.append("GIT_REPO_URL=%s" % repo_url)
    env = [e for e in env if not e.startswith("BEADS_DISPATCH=")]
    env.append("BEADS_DISPATCH=false")
    # BEADS_REMOTE tells the worker where to clone/pull the beads Dolt DB from.
    # Defaults to repo_url when not explicitly provided.
    remote = beads_remote or repo_url
    if remote:
        env = [e for e in env if not e.startswith("BEADS_REMOTE=")]
        env.append("BEADS_REMOTE=%s" % remote)
    return env


# --------------------------------------------------------------------------- git

def git_current_branch(workspace, user):
    rc, out, _ = run_as_user(user, ["git", "-C", workspace, "branch", "--show-current"])
    if rc == 0 and out:
        return out
    # detached HEAD -> return the commit sha
    rc, out, _ = run_as_user(user, ["git", "-C", workspace, "rev-parse", "HEAD"])
    return out if rc == 0 and out else None


def branch_exists_remote(workspace, branch, repo_url, user):
    rc, out, _ = run_as_user(user, ["git", "-C", workspace, "ls-remote", repo_url,
                                    "refs/heads/%s" % branch],
                             env=git_env())
    return rc == 0 and bool(out.strip())


def push_task_branch(workspace, branch, repo_url, user):
    """Create <branch> off the current HEAD, push it, restore the original branch.

    All git operations run as <user> (the workspace owner, e.g. abc) so that the
    user's git credentials (helper, ssh, token) are used — root may not have them.

    Returns: True (pushed), "exists" (branch already in origin — nothing to push),
    or False (failed; original branch restored).
    """
    original = git_current_branch(workspace, user)
    if not original:
        log("ERROR: cannot determine current git branch in %s" % workspace)
        return False

    if branch_exists_remote(workspace, branch, repo_url, user):
        log("Branch %s already exists in origin — skipping create/push." % branch)
        return "exists"

    g_env = git_env()

    def restore():
        try:
            run_as_user(user, ["git", "-C", workspace, "checkout", original], env=g_env)
        except Exception:
            pass

    def cleanup_local_branch():
        """Delete the local branch if it exists (to avoid 'already exists' on retry)."""
        try:
            run_as_user(user, ["git", "-C", workspace, "branch", "-D", branch], env=g_env)
        except Exception:
            pass

    # 1. Create the branch off current HEAD (no commit).
    # Use -B (force create/reset) instead of -b to handle retries where the branch
    # might already exist locally from a previous failed attempt.
    rc, out, err = run_as_user(user, ["git", "-C", workspace, "checkout", "-B", branch],
                               env=g_env)
    if rc != 0:
        log("ERROR: git checkout -B %s failed (as %s): %s" % (branch, user, err or out))
        return False

    # 2. Determine the push target: origin if it matches repo_url, else repo_url.
    rc, origin, _ = run_as_user(user, ["git", "-C", workspace, "remote", "get-url", "origin"])
    if rc == 0 and origin == repo_url:
        push_cmd = ["git", "-C", workspace, "push", "-u", "origin", branch]
    else:
        push_cmd = ["git", "-C", workspace, "push", repo_url, "%s:%s" % (branch, branch)]

    rc, out, err = run_as_user(user, push_cmd, env=g_env)
    restore()
    if rc != 0:
        log("ERROR: git push of %s failed (as %s): %s (is the parent configured to push to %s?)"
            % (branch, user, (err or out).splitlines()[-1] if (err or out) else "unknown", repo_url))
        # Clean up the local branch so retries don't fail with "already exists"
        cleanup_local_branch()
        return False
    log("Pushed branch %s to %s" % (branch, repo_url))
    return True


def ensure_safe_directory(workspace):
    """Allow git-as-root to operate on the workspace repo (which is abc-owned).

    git 2.35+ refuses to run in a repo owned by another user (dubious ownership).
    The dispatcher runs git as root but the workspace is owned by the `abc` user,
    so add the workspace to root's safe.directory list (idempotent).
    """
    rc, out, _ = run(["git", "config", "--global", "--get-all", "safe.directory"])
    if rc == 0 and workspace in out.splitlines():
        return
    run(["git", "config", "--global", "--add", "safe.directory", workspace])


def _probe_credential_helper(cli, host):
    """Return True if <cli> can answer a git credential request for <host>.

    Runs '<cli> auth git-credential get' with a probe stdin. Only CLIs that
    answer non-interactively with a password are configured — one that would
    prompt (or lacks a token) is skipped so we never hang the dispatcher.
    """
    probe = "protocol=https\nhost=%s\n\n" % host
    rc, out, err = run([cli, "auth", "git-credential", "get"],
                       input=probe, env=git_env())
    return rc == 0 and "password=" in out


def _has_credential_helper(marker):
    """Return True if git already has a credential.helper containing <marker>."""
    rc, out, _ = run(["git", "config", "--global", "--get-all", "credential.helper"])
    return rc == 0 and marker in out


def configure_credential_helpers():
    """Configure gh (GitHub) and/or glab (GitLab) as git credential helpers.

    gh/glab answer git credential prompts non-interactively via their token env
    vars (GH_TOKEN / GITLAB_TOKEN) or their own auth stores, giving the root
    daemon a way to push regardless of workspace ownership and without
    per-user credential files. Helpers are set only when the CLI is present and
    answers a probe, so existing user setups are never overridden. Existing
    entries are kept (idempotent).

    Note: glab's helper returns an empty username; git accepts that and uses
    the password, which is how GitLab PAT auth over HTTPS works (the username
    is ignored server-side). Verified via 'git credential fill'.
    """
    configured = False

    # GitHub: gh. Its helper already returns username=x-access-token.
    if shutil.which("gh") and not _has_credential_helper("gh auth git-credential"):
        if _probe_credential_helper("gh", "github.com"):
            try:
                run(["git", "config", "--global", "--add", "credential.helper",
                     "!gh auth git-credential"])
                log("Configured gh as git credential helper.")
                configured = True
            except Exception as e:
                log("WARNING: could not configure gh credential helper: %s" % e)
        else:
            log("gh present but cannot answer credential probe — skipping.")

    # GitLab: glab (returns an empty username, which git accepts).
    if shutil.which("glab") and not _has_credential_helper("glab auth git-credential"):
        if _probe_credential_helper("glab", "gitlab.com"):
            try:
                run(["git", "config", "--global", "--add", "credential.helper",
                     "!glab auth git-credential"])
                log("Configured glab as git credential helper.")
                configured = True
            except Exception as e:
                log("WARNING: could not configure glab credential helper: %s" % e)
        else:
            log("glab present but no credential probe response — skipping.")

    return configured


def copy_abc_git_credentials(workspace):
    """Copy git credentials from the abc user to root so the dispatcher can push.

    The dispatcher runs as root but needs git credentials (SSH keys, token files,
    credential helpers) that are configured for the abc user. This function copies
    the relevant files and config from /config (abc's home) to /root.
    """
    # Source: abc user's home (typically /config in linuxserver images)
    abc_home = "/config"
    root_home = "/root"

    # Copy SSH keys if they exist
    abc_ssh = os.path.join(abc_home, ".ssh")
    root_ssh = os.path.join(root_home, ".ssh")
    if os.path.isdir(abc_ssh):
        try:
            os.makedirs(root_ssh, exist_ok=True)
            for fname in os.listdir(abc_ssh):
                src = os.path.join(abc_ssh, fname)
                dst = os.path.join(root_ssh, fname)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    os.chmod(dst, 0o600)  # SSH keys must be 600
        except OSError as e:
            log("WARNING: could not copy SSH keys: %s" % e)

    # Copy git credentials file if it exists
    abc_git_cred = os.path.join(abc_home, ".git-credentials")
    root_git_cred = os.path.join(root_home, ".git-credentials")
    if os.path.isfile(abc_git_cred) and not os.path.isfile(root_git_cred):
        try:
            shutil.copy2(abc_git_cred, root_git_cred)
            os.chmod(root_git_cred, 0o600)
        except OSError as e:
            log("WARNING: could not copy .git-credentials: %s" % e)

    # Copy credential helper config if it exists
    abc_gitconfig = os.path.join(abc_home, ".gitconfig")
    root_gitconfig = os.path.join(root_home, ".gitconfig")
    if os.path.isfile(abc_gitconfig):
        try:
            # Read abc's gitconfig and extract credential section
            rc, out, _ = run(["git", "config", "--file", abc_gitconfig, "--get-regexp", "credential."])
            if rc == 0 and out:
                for line in out.splitlines():
                    key, val = line.split(" ", 1)
                    run(["git", "config", "--global", key, val])
        except Exception as e:
            log("WARNING: could not copy credential helper config: %s" % e)


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


# The only volume the worker gets: the host docker socket, so the replicated
# container can drive the host daemon too. No other mounts are replicated.
DOCKER_SOCK_SOURCE = "/var/run/docker.sock"
DOCKER_SOCK_TARGET = "/var/run/docker.sock"


def dispatch_local(worker, image, env, port, worker_port, restart_policy, issue_id):
    cmd = ["docker", "run", "-d", "--name", worker, "--hostname", worker,
           "-l", "beads.task=%s" % issue_id]
    if restart_policy and restart_policy not in ("", "no"):
        cmd += ["--restart", restart_policy]
    for e in env:
        cmd += ["-e", e]
    cmd += ["-v", "%s:%s" % (DOCKER_SOCK_SOURCE, DOCKER_SOCK_TARGET)]
    cmd += ["-p", "%d:%d" % (port, worker_port), image]
    return run(cmd)


def dispatch_swarm(worker, image, env, port, worker_port, issue_id):
    cmd = [
        "docker", "service", "create",
        "--name", worker,
        "--hostname", worker,
        "--detach",
        "--label", "beads.task=%s" % issue_id,
        "--restart-condition", "any",
    ]
    for e in env:
        cmd += ["-e", e]
    cmd += ["--mount", "type=bind,source=%s,target=%s" % (DOCKER_SOCK_SOURCE, DOCKER_SOCK_TARGET)]
    cmd += ["--publish", "published=%d,target=%d" % (port, worker_port), image]
    return run(cmd)


def dispatch_worker(issue, cfg, self_info):
    """Dispatch a worker for a ready issue. Returns True when handled."""
    issue_id = issue["id"]
    worker = worker_name(self_info["name"], issue_id)

    # Run git operations as the owner of the workspace (e.g. abc), so the user's
    # credentials are used for the push. The daemon itself runs as root (required
    # to reach the docker socket) but root typically has no git credentials.
    git_user = env("BEADS_DISPATCH_GIT_USER") or get_workspace_owner(cfg.workspace)

    branch = derive_branch_name(issue, cfg.branch_prefix)
    repo_url = derive_git_repo_url(self_info["env"], cfg.workspace, git_user)
    if not repo_url:
        log("WARNING: no GIT_REPO_URL and no git origin in %s — skipping %s"
            % (cfg.workspace, issue_id))
        return False

    # Push the task branch so the worker can clone/check it out.
    push_result = push_task_branch(cfg.workspace, branch, repo_url, git_user)
    if push_result is False:
        log("ERROR: could not push branch for %s — skipping dispatch." % issue_id)
        return False

    # Sync the beads Dolt database (which is gitignored and NOT in the branch) so
    # the worker can see the tasks. Non-fatal: the worker still gets the repo.
    if dolt_remote_add(cfg.workspace, repo_url, git_user):
        dolt_push(cfg.workspace, git_user)
    else:
        log("WARNING: dolt remote could not be configured for %s — tasks may not sync." % issue_id)

    port = find_free_host_port(cfg.port_base)
    if port is None:
        log("WARNING: no free host port >= %d — skipping %s" % (cfg.port_base, issue_id))
        return False

    env_vars = compose_worker_env(self_info["env"], branch, repo_url, beads_remote=repo_url)

    swarm = is_swarm_manager()
    if worker_exists(worker, swarm):
        log("Worker %s already exists for %s — skipping." % (worker, issue_id))
        return True  # treated as handled (dedup)

    if swarm:
        log("Swarm manager detected — dispatching service %s for %s (branch %s)"
            % (worker, issue_id, branch))
        rc, out, err = dispatch_swarm(worker, self_info["image"], env_vars, port,
                                      cfg.worker_port, issue_id)
    else:
        log("Local mode — dispatching container %s for %s (branch %s)"
            % (worker, issue_id, branch))
        rc, out, err = dispatch_local(worker, self_info["image"], env_vars, port,
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
    copy_abc_git_credentials(cfg.workspace)
    configure_credential_helpers()

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
