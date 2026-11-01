#!/usr/bin/env python3
"""Worker PR/MR Setup — create a draft PR/MR for beads-dispatched workers.

Runs once at worker startup, after git-repo-setup.sh creates/checks out the
task branch and after configure-beads.sh syncs the beads DB, and before the
prompt session starts. Only runs in workers dispatched by the beads
dispatcher: a `task/<id>-<slug>` branch with BEADS_DISPATCH=false and
MR_PR_DISPATCH=false. MR/PR-dispatched workers already have their MR/PR at
dispatch time, so this step never runs for them.

Why creation happens here, in the worker
---------------------------------------
The PR/MR does not exist at dispatch time for a beads worker, and the
design requires the worker — not the dispatcher, and not by monitoring
provider CLI activity — to create it. Keeping it in the worker keeps the
feature parent-independent and keeps the change to the dispatcher minimal
(the dispatcher only forces WORKER_KILLER=true and rewrites its prompt).

Sequence
--------
1. The branch already exists (created/checked out by git-repo-setup.sh).
2. Look for an existing PR/MR for the branch first and reuse it. Never
   create a duplicate on retry or forced re-dispatch.
3. Get title/description from the beads database only, via `bd show`,
   using the bead id derived from the branch name.
4. Create an --allow-empty commit whose message carries the bead
   information. A branch identical to its base is rejected as having no
   commits to merge, so this commit is what makes the branch PR-able — and
   it is useful history: anyone reading the branch sees which task it is
   for before real changes land.
5. Push the branch, then create a draft PR/MR.
6. Write the association to /config/.worker-pr.json for the worker killer,
   and record it on the bead via `bd update <id> --external-ref` +
   `bd dolt push` so the association is visible outside the worker.

Title/description source
------------------------
The beads database, via `bd show`, in the normal case. PROMPT is never used
as a title/description source anywhere in this flow: the user can override
PROMPT to be anything, so it is not a reliable bead record. If `bd show`
fails, creation still proceeds using the branch name as the title and a
placeholder in the description, so a worker never starts with no PR (and
therefore no killer association) just because the beads DB was briefly
unavailable. The branch name is safe here because the dispatcher derived
it from the bead at dispatch time, unlike PROMPT.

Failure handling
----------------
A failure that happens *after* a PR is known to exist is fatal (the push or
the CLI call). A `bd show` failure is not: it degrades to the branch-name
+ placeholder fallback. Either way the agent is started anyway: the killer
has no association until a PR exists, and the agent's own fallback may
create one later under the same rules.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

# State file the worker killer reads (must match worker_killer.py's constant).
PR_INFO_FILE = Path(os.environ.get("WORKER_PR_STATE_FILE", "/config/.worker-pr.json"))

WORKSPACE = os.environ.get("DEFAULT_WORKSPACE", "/workspace")

# The credential pattern the MR/PR sync scripts already use: drop to the abc
# user (whose gh/glab auth and git credentials live in /config) via setpriv.
ABC_USER = "abc"
ABC_HOME = "/config"


def log(msg):
    print("[WORKER-PR-SETUP] %s" % msg, flush=True)


# --------------------------------------------------------------------------- helpers


def parse_repo_url(repo_url):
    """Parse (host, owner_repo) from a git URL, ignoring userinfo."""
    url = re.sub(r"^([a-zA-Z][a-zA-Z0-9+.-]*://)[^/@]*@", r"\1", repo_url or "")
    if "://" in url:
        rest = url.split("://", 1)[1]
    else:
        rest = url
    host = rest.split("/")[0].split(":")[0]
    path = "/".join(rest.split("/")[1:]).removesuffix(".git")
    if "/" not in path:
        return None, None
    return host, path


def detect_provider(host, override=None):
    """Provider from the explicit override, else auto-detected from the host."""
    if override:
        return override
    if host == "github.com":
        return "github"
    if host == "gitlab.com":
        return "gitlab"
    return None


def run_as_abc(cmd, env=None, cwd=None):
    """Run a command as the abc user with HOME=/config for credentials."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    full_env["HOME"] = ABC_HOME
    if cmd and cmd[0] == "glab":
        full_env.setdefault("GLAB_SEND_TELEMETRY", "false")
    setpriv = ["setpriv", "--reuid=%s" % ABC_USER, "--regid=%s" % ABC_USER,
               "--init-groups", "env"]
    for key, val in full_env.items():
        setpriv.append("%s=%s" % (key, val))
    setpriv.extend(cmd)
    result = subprocess.run(setpriv, capture_output=True, text=True, cwd=cwd)
    return result.returncode, result.stdout, result.stderr


def _bead_ids_from_db():
    """Issue ids currently in the beads database ([] when unavailable)."""
    try:
        proc = subprocess.run(["bd", "list", "--json"],
                              capture_output=True, text=True, cwd=WORKSPACE)
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item.get("id") for item in data
            if isinstance(item, dict) and item.get("id")]


def derive_bead_id(branch):
    """Bead id from a task/<id>-<slug> branch name.

    Issue ids may themselves contain dashes (e.g. ``workspace-8ez.8``) while
    the slug suffix is dash-separated too, so a naive first-dash split would
    guess ``workspace`` for both ``workspace-ehp-...`` and
    ``workspace-8ez.8-...``. Match instead against the ids actually present
    in the beads database: the branch was derived from the bead at dispatch
    time, so exactly one id is a prefix of the remainder. The longest match
    wins when ids are prefixes of one another. Falls back to the first-dash
    split only when the database cannot be read.
    """
    remainder = branch[len("task/"):] if branch.startswith("task/") else branch
    if not remainder:
        return ""
    matches = [i for i in _bead_ids_from_db()
               if remainder == i or remainder.startswith(i + "-")]
    if matches:
        return max(matches, key=len)
    return remainder.split("-")[0]


def build_commit_message(bead_id, bead_title):
    """(subject, body) for the --allow-empty commit.

    Bead data present: subject carries the bead id and title. Bead data
    absent (bd show failed): subject carries the id only — the title is
    the branch name, never PROMPT.
    """
    if bead_title:
        subject = "WIP: %s - %s" % (bead_id, bead_title)
    else:
        subject = "WIP: %s" % bead_id
    body = ("Bead: %s\nBranch auto-created by the beads dispatcher so the "
            "worker opens a draft PR/MR and shuts down when it closes.\n"
            % bead_id)
    return subject, body


def build_pr_title_body(branch, bead_id, bead_title, bead_description):
    """(title, body) for the draft PR/MR.

    The bead's own title/description in the normal case. When the bead data
    is unavailable, the branch name is the title and a placeholder is the
    description. PROMPT is never a source.
    """
    if bead_title:
        title = bead_title
        body = bead_description
    else:
        title = branch
        body = ("Placeholder: bead description unavailable at PR creation "
                "time (bd show failed); to be updated by the agent.")
    footer = ("\n\n---\n*This PR was created automatically by the worker for "
              "bead %s.*" % bead_id)
    return title, (body + footer) if body else footer.lstrip("\n")


# --------------------------------------------------------------------------- provider queries


def find_existing_pr_github(owner_repo, branch):
    """(id, url) of an existing open PR for this branch, else (None, None).

    --state open on purpose: a closed/merged PR for this branch is not an
    association to adopt — reusing it would record a dead PR, skip creating
    a new draft, and let the killer shut the fresh worker down on it.
    """
    rc, out, err = run_as_abc([
        "gh", "pr", "list", "--head", branch, "--state", "open",
        "--repo", owner_repo,
        "--json", "number,url",
        "-q", ".[] | \"\\(.number)|\\(.url)\"",
    ])
    if rc != 0:
        return None, None
    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if len(lines) != 1:
        # None, or more than one: not a unique association, so never adopt it.
        return None, None
    pr_id, _, url = lines[0].partition("|")
    return pr_id, url


def _parse_mr_list(raw):
    """The merge_requests array from glab's -F json output.

    glab prints either the API's object shape ({"merge_requests": [...]}) or,
    in some versions, a bare array. Parse the whole document when it is valid
    JSON, and only fall back to slicing from the first '[' when it is not —
    slicing an object shape at '[' yields invalid JSON and silently loses
    every MR.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("[")
        if start == -1:
            return []
        try:
            data = json.loads(raw[start:])
        except json.JSONDecodeError:
            return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        mrs = data.get("merge_requests", [])
        return mrs if isinstance(mrs, list) else []
    return []


def find_existing_mr_gitlab(owner_repo, branch):
    """(id, url) of an existing open MR for this branch, else (None, None).

    glab mr list defaults to open MRs, but filter explicitly: a closed or
    merged MR is not an association to adopt, for the same reason as the
    GitHub --state open above.
    """
    rc, out, err = run_as_abc([
        "glab", "mr", "list", "--source-branch", branch,
        "--repo", owner_repo, "-F", "json",
    ])
    if rc != 0:
        return None, None
    mrs = _parse_mr_list(out)
    if len(mrs) != 1:
        # Not unique (or none): never adopt an ambiguous association.
        return None, None
    mr = mrs[0]
    if mr.get("state", "").lower() != "opened":
        return None, None
    return str(mr.get("iid", "")), mr.get("web_url", "")


def get_bead_info(bead_id):
    """(title, description) from the beads DB, or (None, None) on failure.

    A beads DB hiccup here degrades PR creation to the branch-name +
    placeholder fallback rather than leaving the worker with no PR at all.
    """
    if not bead_id:
        return None, None
    try:
        proc = subprocess.run(["bd", "show", bead_id, "--json"],
                              capture_output=True, text=True, cwd=WORKSPACE)
    except OSError:
        return None, None
    if proc.returncode != 0:
        return None, None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, None
    # `bd show <id> --json` returns a list with one issue dict, not a dict
    # itself (bd 1.3.2). An empty list means the bead was not found.
    if isinstance(data, list):
        if not data:
            return None, None
        data = data[0]
    if not isinstance(data, dict):
        return None, None
    return data.get("title") or None, data.get("description") or None


# --------------------------------------------------------------------------- creation


def create_draft_pr_github(owner_repo, branch, base_branch, title, body):
    """(id, url) of the new draft PR, or (None, None) on failure."""
    rc, out, err = run_as_abc([
        "gh", "pr", "create", "--draft", "--head", branch,
        "--base", base_branch, "--title", title, "--body", body,
        "--repo", owner_repo,
    ])
    if rc != 0:
        log("gh pr create failed: %s" % (err or out))
        return None, None
    url = ""
    for token in out.split():
        if token.startswith("https://github.com/"):
            url = token
            break
    pr_id = ""
    match = re.search(r"/pull/(\d+)", url)
    if match:
        pr_id = match.group(1)
    return pr_id, url


def create_draft_mr_gitlab(owner_repo, branch, base_branch, title, body):
    """(id, url) of the new draft MR, or (None, None) on failure."""
    rc, out, err = run_as_abc([
        "glab", "mr", "create", "--draft", "--source-branch", branch,
        "--target-branch", base_branch, "--title", title,
        "--description", body, "--yes", "--repo", owner_repo,
    ])
    if rc != 0:
        log("glab mr create failed: %s" % (err or out))
        return None, None
    url = ""
    for token in out.split():
        # Self-hosted instances are not on gitlab.com, so match the MR path
        # shape rather than the host.
        if "/-/merge_requests/" in token:
            url = token
            break
    mr_id = ""
    match = re.search(r"/merge_requests/(\d+)", url)
    if match:
        mr_id = match.group(1)
    return mr_id, url


# --------------------------------------------------------------------------- git


def git(args, cwd=WORKSPACE):
    return subprocess.run(["git"] + args, capture_output=True, text=True,
                          cwd=cwd)


def resolve_default_branch():
    """The branch the draft PR/MR should target.

    Precedence: GIT_CHECKOUT_BASE_BRANCH when set, then the remote's
    default branch (remote HEAD), then "main". The checkout base wins
    because git-repo-setup.sh creates the task branch from it when it
    is set — so it, not the remote default, is the branch the worker's
    changes are actually based on. This value is also the comparison
    base for branch_has_commits(), so a branch cut from e.g. `beads`
    with no new commits correctly gets the --allow-empty commit instead
    of being judged ahead of `main` and skipping it.
    """
    base = (os.environ.get("GIT_CHECKOUT_BASE_BRANCH") or "").strip()
    if base:
        return base
    proc = git(["symbolic-ref", "refs/remotes/origin/HEAD"])
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()[len("refs/remotes/origin/"):]
    return "main"


def branch_has_commits(default_branch):
    """True when HEAD has commits not in the default branch."""
    proc = git(["merge-base", "--is-ancestor", "origin/%s" % default_branch, "HEAD"])
    if proc.returncode != 0:
        return True  # not a descendant: assume it carries work
    ahead = git(["rev-list", "origin/%s..HEAD" % default_branch])
    return bool(ahead.stdout.strip())


def commit_empty(bead_id, bead_title):
    """Create the --allow-empty commit that makes the branch PR-able.

    A worker clone carries no git identity, so provide one only when none is
    configured: git refuses to commit without one. Non-fatal on failure —
    the caller continues (and the agent may commit real work later).
    """
    subject, body = build_commit_message(bead_id, bead_title)
    env = os.environ.copy()
    name_probe = git(["config", "user.name"])
    email_probe = git(["config", "user.email"])
    if name_probe.returncode != 0 or not name_probe.stdout.strip():
        env.setdefault("GIT_AUTHOR_NAME", "vscode-claude-worker")
        env.setdefault("GIT_COMMITTER_NAME", "vscode-claude-worker")
    if email_probe.returncode != 0 or not email_probe.stdout.strip():
        env.setdefault("GIT_AUTHOR_EMAIL", "worker@localhost")
        env.setdefault("GIT_COMMITTER_EMAIL", "worker@localhost")
    subprocess.run(["git", "commit", "--allow-empty", "-m", subject, "-m", body],
                   env=env, cwd=WORKSPACE)


def push_branch(branch, provider=None):
    """Best-effort push of the branch. Non-fatal: returns the exit code.

    Runs as the abc user (whose gh/glab auth lives in /config, or whose
    GH_TOKEN/GITLAB_TOKEN is inherited via env) with an explicit per-push
    credential helper, so git can answer non-interactively from the
    provider CLI's token. A plain `git push` as root has neither: no
    credential helper is configured for root in a fresh worker, so git
    tries to prompt for a username and fails with exit 128
    ("could not read Username ... No such device or address") and the
    draft PR is never created. GIT_TERMINAL_PROMPT=0 makes a missing
    helper fail fast instead of prompting on a nonexistent TTY.
    """
    cmd = ["git"]
    if provider == "github":
        cmd += ["-c", "credential.helper=!gh auth git-credential"]
    elif provider == "gitlab":
        cmd += ["-c", "credential.helper=!glab auth git-credential"]
    cmd += ["push", "-u", "origin", branch]
    rc, out, err = run_as_abc(cmd, env={"GIT_TERMINAL_PROMPT": "0"},
                              cwd=WORKSPACE)
    return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)


def record_on_bead(bead_id, url, provider, pr_id):
    """Record the PR/MR on the bead so the association is visible remotely.

    Both calls are non-fatal: the killer still watches the PR/MR locally,
    which is what actually governs shutdown.
    """
    if not bead_id:
        return
    subprocess.run(["bd", "update", bead_id, "--external-ref", url,
                    "--notes", "PR/MR: %s (provider: %s, id: %s)"
                    % (url, provider, pr_id)],
                   capture_output=True, text=True, cwd=WORKSPACE)
    subprocess.run(["bd", "dolt", "push"], capture_output=True, text=True,
                   cwd=WORKSPACE)


def write_pr_info(pr_id, provider, repo_url, branch, url, bead_id):
    """Persist the association the worker killer reads."""
    try:
        PR_INFO_FILE.parent.mkdir(parents=True, exist_ok=True)
        PR_INFO_FILE.write_text(json.dumps({
            "id": pr_id,
            "provider": provider,
            "repo_url": repo_url,
            "branch": branch,
            "url": url,
            "bead_id": bead_id,
        }, indent=2))
    except OSError as e:
        log("WARNING: could not write %s: %s" % (PR_INFO_FILE, e))


# --------------------------------------------------------------------------- orchestration


def should_run():
    """True only in a beads-dispatched worker on a task branch."""
    if os.environ.get("BEADS_DISPATCH") == "true":
        log("Not a worker container (BEADS_DISPATCH=true). Skipping.")
        return False
    if os.environ.get("MR_PR_DISPATCH") == "true":
        log("Not a worker container (MR_PR_DISPATCH=true). Skipping.")
        return False
    branch = os.environ.get("GIT_BRANCH_NAME", "")
    if not branch.startswith("task/"):
        log("Not a task branch (GIT_BRANCH_NAME=%r). Skipping." % branch)
        return False
    if os.environ.get("WORKER_KILLER") != "true":
        log("WORKER_KILLER not enabled. Skipping.")
        return False
    return True


def setup():
    """Create (or reuse) the draft PR/MR. Returns a summary dict."""
    branch = os.environ["GIT_BRANCH_NAME"]
    repo_url = os.environ.get("GIT_REPO_URL", "")
    bead_id = derive_bead_id(branch)
    host, owner_repo = parse_repo_url(repo_url)
    provider = detect_provider(host, os.environ.get("MR_PR_PROVIDER"))
    if not provider:
        log("Could not determine provider for %r. Skipping." % repo_url)
        return {"created": False}

    log("Setting up PR/MR for bead %s on branch %s (%s, %s)"
        % (bead_id, branch, provider, owner_repo))

    # 1-2. Reuse an existing PR/MR for this branch when there is exactly one.
    if provider == "github":
        pr_id, pr_url = find_existing_pr_github(owner_repo, branch)
    else:
        pr_id, pr_url = find_existing_mr_gitlab(owner_repo, branch)
    if pr_id:
        log("Reusing existing %s %s for branch %s" % (provider, pr_id, branch))
    else:
        # 3. Bead data from the beads database only.
        bead_title, bead_description = get_bead_info(bead_id)
        if bead_title:
            log("Bead %s: %s" % (bead_id, bead_title))
        else:
            log("No bead data for %s — using the branch name and a placeholder."
                % bead_id)

        # 4. Make the branch PR-able with an --allow-empty commit.
        default_branch = resolve_default_branch()
        if not branch_has_commits(default_branch):
            commit_empty(bead_id, bead_title)
            log("Created --allow-empty commit for bead %s" % bead_id)

        # 5. Push, then create the draft PR/MR.
        proc = push_branch(branch, provider)
        if proc.returncode != 0:
            log("WARNING: git push exited %d — the agent may create the PR/MR "
                "itself: %s" % (proc.returncode, (proc.stderr or "").strip()))
        else:
            title, body = build_pr_title_body(branch, bead_id, bead_title,
                                              bead_description)
            if provider == "github":
                pr_id, pr_url = create_draft_pr_github(owner_repo, branch,
                                                      default_branch, title, body)
            else:
                pr_id, pr_url = create_draft_mr_gitlab(owner_repo, branch,
                                                      default_branch, title, body)
            if not pr_id:
                log("WARNING: could not create a draft %s — the killer will "
                    "fall back to a branch lookup." % provider)
            else:
                log("Created draft %s %s: %s" % (provider, pr_id, pr_url))

    # 6. Record the association for the killer and on the bead.
    write_pr_info(pr_id or "", provider, repo_url, branch, pr_url or "", bead_id)
    if pr_id:
        record_on_bead(bead_id, pr_url, provider, pr_id)
        log("PR/MR setup complete: %s %s" % (provider, pr_id))
        return {"created": True, "provider": provider, "id": pr_id, "url": pr_url}
    log("PR/MR setup finished without an association.")
    return {"created": False}


def main(argv):
    if not should_run():
        return 0
    if not os.environ.get("GIT_REPO_URL"):
        log("GIT_REPO_URL not set. Skipping.")
        return 0
    try:
        setup()
    except Exception as e:
        # Never abort container startup over PR setup.
        log("ERROR: PR/MR setup failed: %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
