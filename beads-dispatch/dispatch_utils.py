import json
import os
import pwd
import re
import shutil
import subprocess
import time


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


def load_state(state_path):
    try:
        with open(state_path) as fh:
            data = json.load(fh)
        return set(data.get("seen", []))
    except (OSError, ValueError):
        return set()


def save_state(state_path, seen):
    try:
        os.makedirs(os.path.dirname(state_path), exist_ok=True)
        tmp = state_path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"seen": sorted(list(seen))}, fh)
        os.replace(tmp, state_path)
    except OSError as e:
        log("WARNING: could not persist state: %s" % e)


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
    host_config = data.get("HostConfig") or {}
    return {
        "image": (data.get("Config") or {}).get("Image"),
        "env": (data.get("Config") or {}).get("Env", []),
        "name": (data.get("Name") or "").lstrip("/"),
        "restart_policy": host_config.get("RestartPolicy", {}).get("Name", ""),
        # Network/DNS settings — replicated workers must match the host's
        # network properties so they can reach the same DNS, registries, etc.
        "dns": host_config.get("Dns", []) or [],
        "dns_search": host_config.get("DnsSearch", []) or [],
        "dns_options": host_config.get("DnsOptions", []) or [],
        "extra_hosts": host_config.get("ExtraHosts", []) or [],
    }


def is_swarm_manager():
    """True when running on a swarm manager node (docker service create is possible)."""
    rc, state, _ = run(["docker", "info", "--format", "{{.Swarm.LocalNodeState}}"])
    if rc != 0 or state != "active":
        return False
    rc, ctrl, _ = run(["docker", "info", "--format", "{{.Swarm.ControlAvailable}}"])
    return rc == 0 and ctrl == "true"


def slugify(text):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug


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


def worker_exists(name, swarm):
    if swarm:
        rc, _, _ = run(["docker", "service", "inspect", name])
    else:
        rc, _, _ = run(["docker", "inspect", name])
    return rc == 0


# The only volume the worker gets: the host docker socket, so the replicated
# container can drive the host daemon too. No other mounts are replicated.
# Check for docker socket at both common locations
_dockersock = None
for sock in ("/var/run/docker.sock", "/run/docker.sock"):
    if os.path.exists(sock):
        _dockersock = sock
        break
DOCKER_SOCK_SOURCE = _dockersock if _dockersock else "/var/run/docker.sock"
DOCKER_SOCK_TARGET = "/var/run/docker.sock"


def add_network_args(cmd, net, swarm=False):
    """Append DNS / extra-host flags for the worker based on the host's config.

    net is the dict produced by inspect_self() (dns, dns_search, dns_options,
    extra_hosts). Workers replicate the parent's network properties so they can
    resolve the same names (internal DNS like the compose 'dns:' entry).
    swarm=True uses docker service create's --host for host mappings (docker run
    uses --add-host).
    """
    for dns in net.get("dns", []) or []:
        cmd += ["--dns", dns]
    for dns_search in net.get("dns_search", []) or []:
        cmd += ["--dns-search", dns_search]
    for opt in net.get("dns_options", []) or []:
        cmd += ["--dns-option", opt]
    host_flag = "--host" if swarm else "--add-host"
    for host in net.get("extra_hosts", []) or []:
        cmd += [host_flag, host]
    return cmd


def dispatch_local(worker, image, env, port, worker_port, restart_policy, issue_id, net=None, labels=None):
    cmd = ["docker", "run", "-d", "--name", worker, "--hostname", worker]
    if labels:
        for k, v in labels.items():
            cmd += ["-l", f"{k}={v}"]
    if restart_policy and restart_policy not in ("", "no"):
        cmd += ["--restart", restart_policy]
    for e in env:
        cmd += ["-e", e]
    cmd += ["-v", f"{DOCKER_SOCK_SOURCE}:{DOCKER_SOCK_TARGET}"]
    if net:
        cmd = add_network_args(cmd, net, swarm=False)
    cmd += ["-p", f"{port}:{worker_port}", image]
    return run(cmd)


def dispatch_swarm(worker, image, env, port, worker_port, issue_id, net=None, labels=None):
    cmd = [
        "docker", "service", "create",
        "--name", worker,
        "--hostname", worker,
        "--detach",
        "--restart-condition", "any",
    ]
    if labels:
        for k, v in labels.items():
            cmd += ["--label", f"{k}={v}"]
    for e in env:
        cmd += ["-e", e]
    cmd += ["--mount", f"type=bind,source={DOCKER_SOCK_SOURCE},target={DOCKER_SOCK_TARGET}"]
    if net:
        cmd = add_network_args(cmd, net, swarm=True)
    cmd += ["--publish", f"published={port},target={worker_port}", image]
    return run(cmd)
