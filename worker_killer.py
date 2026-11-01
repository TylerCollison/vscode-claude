#!/usr/bin/env python3
"""Worker Killer — self-shutdown when the worker's MR/PR closes.

This daemon runs INSIDE a worker container. It polls the associated
MR/PR and triggers container shutdown when the MR/PR is closed (merged
or closed without merging) after a 5-minute grace period with re-verification.

Principles
----------
- Self-shutdown, not parent shutdown. The worker kills itself when its
  MR/PR closes. This makes shutdown independent of the parent node.
- The parent reaper is complementary: after the worker kills itself,
  the reaper cleans up the lingering service/container object.
- Opt-in at the dispatcher: both beads_dispatch.py and mr_pr_dispatch.py
  append WORKER_KILLER=true to the worker env only when the parent node
  opts in via WORKER_KILLER_ENABLED=true. The killer startup script gates
  on WORKER_KILLER=true, so parent containers never run it.
- Other worker flags unchanged: BEADS_DISPATCH=false, MR_PR_DISPATCH=false,
  WORKER_REAPER=false. The killer is separate from the reaper.

Polling
-------
Explicit state query via gh/glab as the abc user (same credential pattern
as MR/PR sync scripts: setpriv + HOME=/config), every ~300s (configurable
via WORKER_KILLER_INTERVAL, aligned with MR_PR_SYNC_INTERVAL).

Trigger
-------
PR/MR state CLOSED or MERGED, for any reason. Merged, closed without
merging, and abandoned all shut the worker down. No closed-unmerged exception.

Grace Period
------------
5 minutes (configurable via WORKER_KILLER_GRACE). On first closed observation,
record the time and do not kill yet. After 5 minutes, re-verify: PR/MR still
closed, worker still exists, association still matches. A reopen in between
cancels the pending shutdown. An API error, empty response, or auth failure
fails closed: skip the cycle, retry next poll, never kill.

Shutdown Action
---------------
Best-effort `git push` of the branch (ignored on failure), then exec
/usr/local/bin/shutdown, which already exists in the image: Happier machine
revocation, then SIGTERM to PID 1, then SIGKILL. No docker socket and no
parent involvement are needed.

Safety
------
Never kill on disappearance from an open list, on name pattern alone, or
on an unlabeled container. A live kill requires the worker label
dispatch.worker=true plus a verified PR/MR association. Never kill the
dispatcher, the parent container, or another worker. Each worker watches
only its own PR/MR, so multiple workers for one PR each shut themselves
down independently; no cross-worker coordination needed.

MR/PR-dispatched workers
------------------------
No PR creation needed. The worker already has MR_PR_ID in env and
mr_pr.id / mr_pr.provider labels from mr_pr_dispatch.py. The killer
reads MR_PR_ID (plus provider and repo from the worker env) and watches
that MR/PR.

Beads-dispatched workers
------------------------
The worker creates the PR/MR during startup (in start-worker-pr-setup.sh).
The killer reads the PR/MR association from /config/.worker-pr.json (written
by the setup script). Fallback: branch PR lookup (gh pr list --head /
glab mr list --source-branch) for its own branch only; if that finds no
unique PR, it does nothing.
"""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import dispatch_utils as du

WORKSPACE = os.environ.get("DEFAULT_WORKSPACE", "/workspace")
STATE_DIR = Path(os.environ.get("WORKER_KILLER_STATE_DIR", "/config/.worker-killer"))
STATE_FILE = STATE_DIR / "state.json"
PR_INFO_FILE = Path(os.environ.get("WORKER_PR_STATE_FILE", "/config/.worker-pr.json"))

# Default intervals (seconds)
DEFAULT_POLL_INTERVAL = 300
DEFAULT_GRACE_PERIOD = 300  # 5 minutes


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [WORKER-KILLER] {msg}", flush=True)


def load_state():
    """Load killer state from file."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    """Persist killer state atomically."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, sort_keys=True)
        tmp.replace(STATE_FILE)
    except OSError as e:
        log(f"WARNING: could not persist killer state: {e}")


def run_as_abc(cmd, env=None, cwd=None):
    """Run a command as the abc user with HOME=/config for credentials."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    full_env["HOME"] = "/config"
    if cmd and cmd[0] == "glab":
        full_env.setdefault("GLAB_SEND_TELEMETRY", "false")
    # Use setpriv to drop to abc user (UID/GID typically 911:911)
    setpriv_cmd = ["setpriv", "--reuid=abc", "--regid=abc", "--init-groups", "env"]
    for k, v in full_env.items():
        setpriv_cmd.append(f"{k}={v}")
    setpriv_cmd.extend(cmd)
    result = subprocess.run(setpriv_cmd, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout, result.stderr


def parse_repo_url(repo_url):
    """Parse owner/repo from GIT_REPO_URL."""
    # Strip userinfo and scheme
    url = re.sub(r"^([a-zA-Z][a-zA-Z0-9+.-]*://)[^/@]*@", r"\1", repo_url or "")
    if "://" in url:
        rest = url.split("://", 1)[1]
    else:
        rest = url
    host = rest.split("/")[0].split(":")[0]
    path = "/".join(rest.split("/")[1:])
    path = path.removesuffix(".git")
    if "/" not in path:
        return None, None, None
    return host, path.split("/")[0], path.split("/")[1]


def get_provider(host, mr_pr_provider_env):
    """Determine provider from host or env override."""
    if mr_pr_provider_env:
        return mr_pr_provider_env
    if host == "github.com":
        return "github"
    if host == "gitlab.com":
        return "gitlab"
    return None


def query_pr_state_github(owner_repo, pr_id):
    """Query PR state via gh. Returns (state, error) where state is 'open', 'closed', 'merged', or None on error."""
    rc, out, err = run_as_abc([
        "gh", "pr", "view", str(pr_id),
        "--repo", owner_repo,
        "--json", "state,mergedAt",
        "-q", ".state + \"|\" + (.mergedAt // \"\")"
    ], cwd=WORKSPACE)
    if rc != 0:
        return None, f"gh pr view failed (rc={rc}): {err.strip()}"
    out = out.strip()
    if not out:
        return None, "empty output"
    state, merged_at = out.split("|", 1)
    if state == "MERGED" or merged_at:
        return "merged", None
    return state.lower(), None


def query_mr_state_gitlab(owner_repo, mr_id):
    """Query MR state via glab. Returns (state, error)."""
    rc, out, err = run_as_abc([
        "glab", "mr", "view", str(mr_id),
        "--repo", owner_repo,
        "-F", "json"
    ], cwd=WORKSPACE)
    if rc != 0:
        return None, f"glab mr view failed (rc={rc}): {err.strip()}"
    out = out.strip()
    if not out:
        return None, "empty output"
    try:
        data = json.loads(out)
        state = data.get("state", "").lower()
        if state == "merged":
            return "merged", None
        return state, None
    except json.JSONDecodeError:
        return None, "failed to parse JSON"


def query_pr_state_by_branch_github(owner_repo, branch):
    """Fallback: find an OPEN PR for branch. Returns (pr_id, state) or (None, None).

    --state open on purpose: a closed/merged PR is not an association to
    adopt — returning it would let the killer latch onto a dead PR and shut
    a fresh worker down on it. A PR that closes after adoption is handled
    by the poll in killer_cycle, not here.
    """
    rc, out, err = run_as_abc([
        "gh", "pr", "list",
        "--head", branch,
        "--state", "open",
        "--repo", owner_repo,
        "--json", "number,state,mergedAt",
        "-q", ".[] | \"\\(.number)|\\(.state)|\\(.mergedAt // \"\")\""
    ], cwd=WORKSPACE)
    if rc != 0:
        return None, None
    out = out.strip()
    if not out:
        return None, None
    lines = out.splitlines()
    if len(lines) != 1:
        return None, None  # ambiguous or none
    pr_id, state, merged_at = lines[0].split("|", 2)
    # Filter on the returned state as well as --state open above: a closed
    # or merged PR is never an association, even if it slips through.
    if state == "MERGED" or merged_at:
        return None, None
    if state.lower() != "open":
        return None, None
    return pr_id, state.lower()


def query_mr_state_by_branch_gitlab(owner_repo, branch):
    """Fallback: find an OPEN MR for branch. Returns (mr_id, state) or (None, None).

    glab mr list defaults to open MRs, but filter explicitly: a closed or
    merged MR is not an association to adopt, for the same reason as the
    GitHub --state open above.
    """
    rc, out, err = run_as_abc([
        "glab", "mr", "list",
        "--source-branch", branch,
        "--repo", owner_repo,
        "-F", "json"
    ], cwd=WORKSPACE)
    if rc != 0:
        return None, None
    out = out.strip()
    if not out:
        return None, None
    try:
        data = json.loads(out)
        mrs = data.get("merge_requests", data if isinstance(data, list) else [])
        if len(mrs) != 1:
            return None, None
        mr = mrs[0]
        state = mr.get("state", "").lower()
        if state != "opened":
            return None, None
        return str(mr.get("iid")), state
    except json.JSONDecodeError:
        return None, None


def get_worker_branch():
    """Get the current branch name from git."""
    try:
        rc, out, _ = run_as_abc(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=WORKSPACE
        )
        if rc == 0:
            return out.strip()
    except Exception:
        pass
    return None


def is_dispatched_worker():
    """True when this container carries the dispatch.worker=true label.

    The kill decision is safety-gated on the container being a dispatched
    worker: a live kill requires the worker label PLUS a verified PR/MR
    association. This is what keeps the killer from ever shutting down the
    dispatcher, the parent container, or any other container.

    The docker socket is used only to READ this container's own labels — the
    shutdown itself needs no docker access. When the socket is unavailable
    (or the labels cannot be read), the check fails closed and the killer
    does nothing: a missing label must never be read as "not a worker".
    """
    container_id = du.self_container_id()
    if not container_id:
        log("Could not determine this container's ID — refusing to kill (label check failed).")
        return False
    rc, out, err = du.run([
        "docker", "inspect", "--type", "container", container_id,
        "--format", "{{index .Config.Labels \"dispatch.worker\"}}",
    ])
    if rc != 0:
        log("Could not read this container's labels (rc=%d) — refusing to kill." % rc)
        return False
    label = (out or "").strip()
    if label != "true":
        log("This container is not labeled dispatch.worker=true (label=%r) — refusing to kill."
            % label)
        return False
    return True


def attempt_shutdown():
    """Best-effort git push then exec shutdown."""
    log("Initiating shutdown sequence...")
    # Best-effort push (ignore failures)
    branch = get_worker_branch()
    if branch and branch != "HEAD":
        try:
            rc, out, err = run_as_abc(
                ["git", "push", "origin", f"HEAD:{branch}"], cwd=WORKSPACE
            )
            if rc == 0:
                log(f"Pushed branch {branch} before shutdown")
            else:
                log(f"Push failed (ignored): {err.strip()}")
        except Exception as e:
            log(f"Push exception (ignored): {e}")
    # Exec shutdown script
    log("Executing /usr/local/bin/shutdown")
    os.execv("/usr/local/bin/shutdown", ["/usr/local/bin/shutdown"])


def killer_cycle(cfg):
    """One polling cycle."""
    # Load PR/MR association info from worker-local state file
    pr_info = {}
    if PR_INFO_FILE.exists():
        try:
            with open(PR_INFO_FILE) as f:
                pr_info = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    # Primary association: MR_PR_ID (for MR/PR-dispatched workers) or .worker-pr.json
    mr_pr_id = pr_info.get("id") or os.environ.get("MR_PR_ID")
    provider = pr_info.get("provider") or os.environ.get("MR_PR_PROVIDER")
    repo_url = pr_info.get("repo_url") or os.environ.get("GIT_REPO_URL")

    # Fallback: branch lookup for beads workers that lost the state file or
    # had a PR creation failure at startup. The branch name is derived from
    # GIT_BRANCH_NAME (set by beads dispatcher) or git.
    branch = None
    if not mr_pr_id or not provider or not repo_url:
        branch = get_worker_branch()
        if branch:
            log("No MR/PR association found — attempting branch lookup for %s" % branch)
            repo_url = repo_url or os.environ.get("GIT_REPO_URL")
            host, owner, repo = parse_repo_url(repo_url) if repo_url else (None, None, None)
            provider = get_provider(host, provider or os.environ.get("MR_PR_PROVIDER"))
            if provider and owner and repo:
                owner_repo = f"{owner}/{repo}"
                # Query by branch (returns id + state if unique)
                if provider == "github":
                    mr_pr_id, state = query_pr_state_by_branch_github(owner_repo, branch)
                else:
                    mr_pr_id, state = query_mr_state_by_branch_gitlab(owner_repo, branch)
                if mr_pr_id and state:
                    # Found unique PR/MR: proceed with that association.
                    log("Branch lookup found %s #%s (state=%s)" % (provider, mr_pr_id, state))
                else:
                    log("Branch lookup returned no unique PR/MR for %s — skipping cycle." % branch)
                    return
    # If still no association, skip cycle
    if not mr_pr_id or not provider or not repo_url:
        log("No MR/PR association found and no branch lookup possible. Skipping cycle.")
        return

    # Parse repo for subsequent queries (host/owner/repo)
    host, owner, repo = parse_repo_url(repo_url)
    if not owner or not repo:
        log(f"Could not parse owner/repo from {repo_url}. Skipping cycle.")
        return
    owner_repo = f"{owner}/{repo}"
    provider = get_provider(host, provider)
    if not provider:
        log(f"Could not determine provider for {host}. Skipping cycle.")
        return

    log(f"Polling {provider} {owner_repo} #{mr_pr_id}")

    # Query current state
    state = None
    error = None
    try:
        if provider == "github":
            state, error = query_pr_state_github(owner_repo, mr_pr_id)
        else:
            state, error = query_mr_state_gitlab(owner_repo, mr_pr_id)
    except Exception as e:
        error = f"exception: {e}"

    if error:
        log(f"API error querying {provider} #{mr_pr_id}: {error}. Failing closed — will retry next cycle.")
        return

    if state is None:
        log(f"Could not determine state for {provider} #{mr_pr_id}. Skipping cycle.")
        return

    log(f"Current state: {state}")

    # Load persistent state
    killer_state = load_state()
    key = f"{provider}:{owner_repo}:{mr_pr_id}"
    entry = killer_state.get(key, {})
    grace_start = entry.get("grace_start")

    if state in ("closed", "merged"):
        if not grace_start:
            # First time seeing closed/merged: start grace period
            grace_start = int(time.time())
            entry["grace_start"] = grace_start
            killer_state[key] = entry
            save_state(killer_state)
            log(f"PR/MR #{mr_pr_id} is {state}. Grace period started (5 min).")
            return

        # In grace period: check if 5 minutes elapsed
        elapsed = int(time.time()) - grace_start
        if elapsed < cfg.grace_period:
            remaining = cfg.grace_period - elapsed
            log(f"PR/MR #{mr_pr_id} is {state}. Grace period: {remaining}s remaining.")
            return

        # Grace period elapsed: re-verify state
        log(f"Grace period elapsed for #{mr_pr_id}. Re-verifying...")
        # Re-query
        if provider == "github":
            verify_state, verify_error = query_pr_state_github(owner_repo, mr_pr_id)
        else:
            verify_state, verify_error = query_mr_state_gitlab(owner_repo, mr_pr_id)

        if verify_error:
            # An API error here fails closed: skip this cycle and keep the
            # pending shutdown so the next poll re-verifies. It must NOT
            # cancel the shutdown, or a transient hiccup would leave a
            # worker running forever on a MR/PR that is still closed.
            log(f"Re-verify query failed for #{mr_pr_id}: {verify_error}. "
                "Failing closed — retrying next cycle.")
            return

        if verify_state not in ("closed", "merged"):
            # The MR/PR is genuinely open again: cancel the pending shutdown.
            log(f"PR/MR #{mr_pr_id} reopened (state={verify_state}). "
                "Cancelling pending shutdown.")
            killer_state.pop(key, None)
            save_state(killer_state)
            return

        # Still closed/merged: SAFETY GATE — verify this container is a dispatched worker
        log(f"PR/MR #{mr_pr_id} confirmed {verify_state}. Verifying worker label...")
        if not is_dispatched_worker():
            log("Safety check failed: container is not a dispatched worker. Aborting shutdown.")
            return

        # Shut down
        log(f"PR/MR #{mr_pr_id} confirmed {verify_state}. Shutting down worker.")
        attempt_shutdown()

    else:
        # PR/MR is open: cancel any pending grace period
        if grace_start:
            log(f"PR/MR #{mr_pr_id} reopened (state={state}). Cancelling pending shutdown.")
            killer_state.pop(key, None)
            save_state(killer_state)


def run_daemon(cfg):
    """Periodically check MR/PR state; exits on SIGTERM/SIGINT."""
    stop = threading.Event()

    def _sig(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    log(f"Worker killer daemon running (interval={cfg.poll_interval}s, grace={cfg.grace_period}s).")
    while not stop.is_set():
        try:
            killer_cycle(cfg)
        except Exception as e:
            log(f"ERROR: unexpected error during killer cycle: {e}")
        if not stop.is_set():
            stop.wait(cfg.poll_interval)
    log("Worker killer daemon stopped.")
    return 0


class Config:
    def __init__(self):
        self.poll_interval = int(du.env("WORKER_KILLER_INTERVAL", str(DEFAULT_POLL_INTERVAL)))
        self.grace_period = int(du.env("WORKER_KILLER_GRACE", str(DEFAULT_GRACE_PERIOD)))


def main(argv):
    if du.env("WORKER_KILLER") != "true":
        log("Worker killer not enabled (WORKER_KILLER is not 'true'). Exiting.")
        return 0

    # The killer polls the provider CLI: at least one of gh/glab must exist,
    # and git is needed for the pre-shutdown push. Without them the killer
    # cannot determine any state, so exit instead of spinning uselessly.
    if not shutil.which("git"):
        log("WARNING: git not found on PATH. Exiting.")
        return 0
    if not (shutil.which("gh") or shutil.which("glab")):
        log("WARNING: neither gh nor glab found on PATH. Exiting.")
        return 0

    cfg = Config()

    if "--once" in argv:
        killer_cycle(cfg)
        return 0

    return run_daemon(cfg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))