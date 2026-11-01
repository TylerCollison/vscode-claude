"""Unit tests for the Worker Killer daemon and Worker PR/MR Setup.

Acceptance criteria covered (workspace-ehp):
- Worker killer only runs when WORKER_KILLER=true (gated env)
- MR/PR-dispatched workers: killer watches existing MR_PR_ID from env
- Beads-dispatched workers: killer reads PR/MR from /config/.worker-pr.json,
  with a branch-lookup fallback when that file is missing
- Polls gh/glab for PR/MR state every ~300s
- Shuts down on CLOSED or MERGED state after a 5-min grace + re-verification
- Reopen during grace cancels pending shutdown
- API error, empty response, or auth failure fails closed (never kills)
- Best-effort git push before exec /usr/local/bin/shutdown
- Never kills on a failed lookup, on a name pattern alone, on an unlabeled
  container, or on the dispatcher/parent/another worker
- Both providers for PR creation, existing-PR reuse, empty-commit content,
  the bd-failure fallback (branch-name title + placeholder description),
  and no PROMPT title usage anywhere in the PR creation path
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))

# Make dispatch_utils importable
sys.path.insert(0, "/usr/local/bin")
sys.path.insert(0, os.path.join(HERE, "..", "beads-dispatch"))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(HERE, "..", relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wk = _load("worker_killer", "worker_killer.py")
wps = _load("worker_pr_setup", "worker_pr_setup.py")

# The isolated _StateDir context manager repoints the killers' state paths, so
# capture the import-time defaults before any test mutates them.
KILLER_DEFAULT_PR_INFO = Path(str(wk.PR_INFO_FILE))
SETUP_DEFAULT_PR_INFO = Path(str(wps.PR_INFO_FILE))


class _StateDir:
    """Context manager: a fresh killer Config on an isolated state dir."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="worker-killer-test-")
        self._old_env = {
            "WORKER_KILLER_STATE_DIR": os.environ.get("WORKER_KILLER_STATE_DIR"),
            "WORKER_KILLER_INTERVAL": os.environ.get("WORKER_KILLER_INTERVAL"),
            "WORKER_KILLER_GRACE": os.environ.get("WORKER_KILLER_GRACE"),
        }
        os.environ["WORKER_KILLER_STATE_DIR"] = self.dir
        os.environ["WORKER_KILLER_INTERVAL"] = "300"
        os.environ["WORKER_KILLER_GRACE"] = "300"
        # Point the module's state/PR-info paths at the isolated dir: they are
        # module-level constants resolved at import time, before this env var.
        wk.STATE_FILE = wk.Path(self.dir, "state.json")
        wk.PR_INFO_FILE = wk.Path(self.dir, "worker-pr.json")
        self.cfg = wk.Config()
        return self.cfg

    def __exit__(self, *exc):
        for key, val in self._old_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        shutil.rmtree(self.dir, ignore_errors=True)

    def state(self):
        with open(wk.STATE_FILE) as fh:
            return json.load(fh)


from contextlib import contextmanager


@contextmanager
def _mock_run_as_abc(returncode=0, stdout="", stderr="", side_effect=None):
    """Mock run_as_abc to return a controlled result."""
    if side_effect is not None:
        def fake(cmd, env=None, cwd=None):
            return side_effect(cmd, env, cwd)
    else:
        def fake(cmd, env=None, cwd=None):
            return returncode, stdout, stderr
    with mock.patch.object(wk, "run_as_abc", side_effect=fake):
        yield


@contextmanager
def _mock_worker_label_true():
    """Mock the dispatch.worker label check to return 'true'."""
    with mock.patch.object(wk.du, "self_container_id", return_value="abc123"):
        with mock.patch.object(wk.du, "run", return_value=(0, "true\n", "")):
            yield


@contextmanager
def _mock_worker_label_false():
    """Mock the dispatch.worker label check to return 'false' (or missing)."""
    with mock.patch.object(wk.du, "self_container_id", return_value="abc123"):
        with mock.patch.object(wk.du, "run", return_value=(0, "false\n", "")):
            yield


def _mock_pr_info(provider="github", pr_id="42", repo_url="https://github.com/o/r.git", branch="task/probe-1-slug"):
    """Create a mock /config/.worker-pr.json."""
    return {
        "id": pr_id,
        "provider": provider,
        "repo_url": repo_url,
        "branch": branch,
        "url": f"https://github.com/o/r/pull/{pr_id}",
        "bead_id": "probe-1"
    }


# --------------------------------------------------------------------------- main gates

def test_main_not_enabled_is_noop():
    old = os.environ.pop("WORKER_KILLER", None)
    try:
        with mock.patch.object(wk, "run_as_abc", side_effect=AssertionError("run_as_abc called")):
            assert wk.main([]) == 0
    finally:
        if old is not None:
            os.environ["WORKER_KILLER"] = old


def test_main_exits_when_gh_glab_missing():
    os.environ["WORKER_KILLER"] = "true"
    try:
        with mock.patch("shutil.which", side_effect=lambda b: None if b in ("gh", "glab") else "/usr/bin/" + b), \
                mock.patch.object(wk.du, "run", side_effect=AssertionError("docker called")):
            assert wk.main([]) == 0
    finally:
        os.environ.pop("WORKER_KILLER", None)


def test_main_once_runs_single_cycle():
    os.environ["WORKER_KILLER"] = "true"
    try:
        with mock.patch("shutil.which", return_value="/usr/bin/gh"), \
                mock.patch.object(wk, "killer_cycle") as cycle:
            assert wk.main(["--once"]) == 0
        assert cycle.call_count == 1
    finally:
        os.environ.pop("WORKER_KILLER", None)


# --------------------------------------------------------------------------- config and state

def test_config_defaults():
    with _StateDir() as cfg:
        assert cfg.poll_interval == 300
        assert cfg.grace_period == 300


def test_state_persists_across_cycles():
    with _StateDir() as cfg:
        state = {"github:o/r:42": {"grace_start": 1700000000}}
        wk.save_state(state)
        loaded = wk.load_state()
        assert loaded == state


# --------------------------------------------------------------------------- parse_repo_url

def test_parse_repo_url_github():
    host, owner, repo = wk.parse_repo_url("https://github.com/o/r.git")
    assert (host, owner, repo) == ("github.com", "o", "r")

def test_parse_repo_url_gitlab():
    host, owner, repo = wk.parse_repo_url("https://gitlab.com/o/r.git")
    assert (host, owner, repo) == ("gitlab.com", "o", "r")

def test_parse_repo_url_self_hosted():
    host, owner, repo = wk.parse_repo_url("https://gitlab.home.com/o/r.git")
    assert (host, owner, repo) == ("gitlab.home.com", "o", "r")

def test_parse_repo_url_strips_userinfo():
    host, owner, repo = wk.parse_repo_url("https://user:token@github.com/o/r.git")
    assert (host, owner, repo) == ("github.com", "o", "r")


# --------------------------------------------------------------------------- get_provider

def test_get_provider_override_wins():
    assert wk.get_provider("gitlab.com", "github") == "github"
    assert wk.get_provider("github.com", "gitlab") == "gitlab"

def test_get_provider_auto_detect():
    assert wk.get_provider("github.com", None) == "github"
    assert wk.get_provider("gitlab.com", None) == "gitlab"
    assert wk.get_provider("gitlab.home.com", None) is None


# --------------------------------------------------------------------------- query functions

def test_query_pr_state_github_open():
    with _mock_run_as_abc(returncode=0, stdout="OPEN|", stderr=""):
        state, error = wk.query_pr_state_github("o/r", "42")
        assert state == "open"
        assert error is None

def test_query_pr_state_github_closed():
    with _mock_run_as_abc(returncode=0, stdout="CLOSED|", stderr=""):
        state, error = wk.query_pr_state_github("o/r", "42")
        assert state == "closed"
        assert error is None

def test_query_pr_state_github_merged():
    with _mock_run_as_abc(returncode=0, stdout="MERGED|2026-01-01T00:00:00Z", stderr=""):
        state, error = wk.query_pr_state_github("o/r", "42")
        assert state == "merged"
        assert error is None

def test_query_pr_state_github_error():
    with _mock_run_as_abc(returncode=1, stdout="", stderr="not found"):
        state, error = wk.query_pr_state_github("o/r", "42")
        assert state is None
        assert "not found" in error


def test_query_mr_state_gitlab_open():
    with _mock_run_as_abc(returncode=0, stdout='{"state": "opened"}', stderr=""):
        state, error = wk.query_mr_state_gitlab("o/r", "42")
        assert state == "opened"
        assert error is None

def test_query_mr_state_gitlab_closed():
    with _mock_run_as_abc(returncode=0, stdout='{"state": "closed"}', stderr=""):
        state, error = wk.query_mr_state_gitlab("o/r", "42")
        assert state == "closed"
        assert error is None

def test_query_mr_state_gitlab_merged():
    with _mock_run_as_abc(returncode=0, stdout='{"state": "merged"}', stderr=""):
        state, error = wk.query_mr_state_gitlab("o/r", "42")
        assert state == "merged"
        assert error is None


# --------------------------------------------------------------------------- killer_cycle: MR/PR-dispatched worker

def test_killer_cycle_mr_pr_worker_open_no_action():
    """MR/PR-dispatched worker: PR is open -> no action, no grace start."""
    with _StateDir() as cfg:
        os.environ["MR_PR_ID"] = "42"
        os.environ["MR_PR_PROVIDER"] = "github"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        try:
            with _mock_run_as_abc(returncode=0, stdout="OPEN|", stderr=""):
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
            state = wk.load_state()
            # No grace_start because PR is open
            assert state == {}
        finally:
            for k in ("MR_PR_ID", "MR_PR_PROVIDER", "GIT_REPO_URL"):
                os.environ.pop(k, None)


def test_killer_cycle_mr_pr_worker_closed_starts_grace():
    """MR/PR-dispatched worker: PR closed -> starts 5-min grace period."""
    with _StateDir() as cfg:
        os.environ["MR_PR_ID"] = "42"
        os.environ["MR_PR_PROVIDER"] = "github"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        try:
            with _mock_run_as_abc(returncode=0, stdout="CLOSED|", stderr=""):
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
            state = wk.load_state()
            key = "github:o/r:42"
            assert key in state
            assert "grace_start" in state[key]
            assert state[key]["grace_start"] > 0
        finally:
            for k in ("MR_PR_ID", "MR_PR_PROVIDER", "GIT_REPO_URL"):
                os.environ.pop(k, None)


def test_killer_cycle_mr_pr_worker_grace_not_elapsed():
    """Grace period not elapsed -> no shutdown."""
    with _StateDir() as cfg:
        os.environ["MR_PR_ID"] = "42"
        os.environ["MR_PR_PROVIDER"] = "github"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        try:
            # Pre-populate state with grace_start 60 seconds ago
            wk.save_state({"github:o/r:42": {"grace_start": int(time.time()) - 60}})
            with _mock_run_as_abc(returncode=0, stdout="CLOSED|", stderr=""):
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
            state = wk.load_state()
            # Grace_start still present (not removed)
            assert "grace_start" in state.get("github:o/r:42", {})
        finally:
            for k in ("MR_PR_ID", "MR_PR_PROVIDER", "GIT_REPO_URL"):
                os.environ.pop(k, None)


def test_killer_cycle_mr_pr_worker_grace_elapsed_reverify_closed_shutdown():
    """Grace elapsed, re-verify closed -> shutdown."""
    with _StateDir() as cfg:
        os.environ["MR_PR_ID"] = "42"
        os.environ["MR_PR_PROVIDER"] = "github"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        try:
            # Pre-populate state with grace_start 301 seconds ago
            wk.save_state({"github:o/r:42": {"grace_start": int(time.time()) - 301}})
            # First call: initial closed (already in state, grace elapsed)
            # Second call: re-verify closed
            def mock_run_as_abc(cmd, env=None, cwd=None):
                return 0, "CLOSED|", ""
            with _mock_run_as_abc(side_effect=mock_run_as_abc), \
                    _mock_worker_label_true(), \
                    mock.patch.object(wk, "attempt_shutdown") as mock_shutdown:
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
                mock_shutdown.assert_called_once()
        finally:
            for k in ("MR_PR_ID", "MR_PR_PROVIDER", "GIT_REPO_URL"):
                os.environ.pop(k, None)


def test_killer_cycle_mr_pr_worker_grace_elapsed_reverify_reopened_cancels():
    """Grace elapsed, but re-verify shows reopened -> cancel shutdown."""
    with _StateDir() as cfg:
        os.environ["MR_PR_ID"] = "42"
        os.environ["MR_PR_PROVIDER"] = "github"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        try:
            wk.save_state({"github:o/r:42": {"grace_start": int(time.time()) - 301}})
            # Re-verify returns OPEN
            calls = []
            def mock_run(cmd, env=None, cwd=None):
                calls.append(cmd)
                return 0, "OPEN|", ""
            with mock.patch.object(wk, "run_as_abc", side_effect=mock_run), \
                    mock.patch.object(wk, "attempt_shutdown") as mock_shutdown:
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
                mock_shutdown.assert_not_called()
            state = wk.load_state()
            assert "github:o/r:42" not in state  # cancelled
        finally:
            for k in ("MR_PR_ID", "MR_PR_PROVIDER", "GIT_REPO_URL"):
                os.environ.pop(k, None)


def test_killer_cycle_mr_pr_worker_api_error_fails_closed():
    """API error on initial query -> skip cycle, never kill."""
    with _StateDir() as cfg:
        os.environ["MR_PR_ID"] = "42"
        os.environ["MR_PR_PROVIDER"] = "github"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        try:
            with _mock_run_as_abc(returncode=1, stdout="", stderr="auth failed"):
                with mock.patch.object(wk.du, "log", lambda msg: None), \
                        mock.patch.object(wk, "attempt_shutdown") as mock_shutdown:
                    wk.killer_cycle(cfg)
                mock_shutdown.assert_not_called()
            # State unchanged
            assert wk.load_state() == {}
        finally:
            for k in ("MR_PR_ID", "MR_PR_PROVIDER", "GIT_REPO_URL"):
                os.environ.pop(k, None)


def test_killer_cycle_mr_pr_worker_merged_triggers_shutdown():
    """MERGED state triggers shutdown same as CLOSED."""
    with _StateDir() as cfg:
        os.environ["MR_PR_ID"] = "42"
        os.environ["MR_PR_PROVIDER"] = "github"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        try:
            wk.save_state({"github:o/r:42": {"grace_start": int(time.time()) - 301}})
            with _mock_run_as_abc(returncode=0, stdout="MERGED|2026-01-01T00:00:00Z", stderr=""), \
                    _mock_worker_label_true(), \
                    mock.patch.object(wk, "attempt_shutdown") as mock_shutdown:
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
                mock_shutdown.assert_called_once()
        finally:
            for k in ("MR_PR_ID", "MR_PR_PROVIDER", "GIT_REPO_URL"):
                os.environ.pop(k, None)


# --------------------------------------------------------------------------- killer_cycle: beads-dispatched worker (reads .worker-pr.json)

def test_killer_cycle_beads_worker_reads_pr_info_file():
    """Beads worker: reads PR info from /config/.worker-pr.json."""
    with _StateDir() as cfg:
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        # No MR_PR_ID in env (beads worker)
        try:
            pr_info = _mock_pr_info()
            wk.PR_INFO_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(wk.PR_INFO_FILE, "w") as f:
                json.dump(pr_info, f)
            with _mock_run_as_abc(returncode=0, stdout="OPEN|", stderr=""):
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
            state = wk.load_state()
            # Grace not started because PR is open
            assert state == {}
        finally:
            os.environ.pop("GIT_REPO_URL", None)
            if wk.PR_INFO_FILE.exists():
                wk.PR_INFO_FILE.unlink()


def test_killer_cycle_beads_worker_fallback_to_branch_lookup():
    """Beads worker: auto-detects provider and branch without a state file."""
    with _StateDir() as cfg:
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        os.environ.pop("MR_PR_PROVIDER", None)
        os.environ.pop("MR_PR_ID", None)
        try:
            # No .worker-pr.json, no MR_PR_ID in env. The branch lookup returns
            # "<id>|<state>|" while the subsequent state query returns
            # "<state>|<mergedAt>", so the mock must key off the command.
            def by_cmd(cmd, env=None, cwd=None):
                if "pr" in cmd and "list" in cmd:
                    return 0, "42|OPEN|", ""
                return 0, "OPEN|", ""
            with mock.patch.object(wk, "run_as_abc",
                                    side_effect=lambda cmd, env=None, cwd=None: (
                                        (0, "task/probe-1-slug\n", "") if "rev-parse" in cmd
                                        else by_cmd(cmd, env, cwd)
                                    )), \
                    _mock_worker_label_true():
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
            # PR is open after the branch lookup found it -> no action
            assert wk.load_state() == {}
        finally:
            os.environ.pop("GIT_REPO_URL", None)
            os.environ.pop("MR_PR_PROVIDER", None)


def test_killer_cycle_beads_worker_branch_lookup_ambiguous_no_action():
    """Branch lookup returns multiple PRs -> no action."""
    with _StateDir() as cfg:
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        os.environ.pop("MR_PR_PROVIDER", None)
        try:
            with mock.patch.object(wk, "get_worker_branch", return_value="task/probe-1-slug"), \
                    _mock_run_as_abc(returncode=0, stdout="42|OPEN|\n43|OPEN|", stderr=""):
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
            assert wk.load_state() == {}
        finally:
            os.environ.pop("GIT_REPO_URL", None)
            os.environ.pop("MR_PR_PROVIDER", None)


# --------------------------------------------------------------------------- killer: branch lookup only adopts open PRs/MRs

def test_query_pr_state_by_branch_github_lists_open_only():
    """The branch lookup must ask for open PRs only, and a closed PR that
    slips through must not be returned as an association."""
    seen = {}

    def by_cmd(cmd, env=None, cwd=None):
        seen["cmd"] = cmd
        return 0, "42|OPEN|", ""

    with mock.patch.object(wk, "run_as_abc", side_effect=by_cmd):
        assert wk.query_pr_state_by_branch_github("o/r", "task/probe-1-x") == ("42", "open")
    assert "--state" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--state") + 1] == "open"


def test_query_pr_state_by_branch_github_closed_returns_none():
    """A closed PR for the branch is not an association to adopt."""
    with mock.patch.object(wk, "run_as_abc", return_value=(0, "42|CLOSED|", "")):
        assert wk.query_pr_state_by_branch_github("o/r", "task/probe-1-x") == (None, None)


def test_query_pr_state_by_branch_github_merged_returns_none():
    """A merged PR for the branch is not an association to adopt."""
    with mock.patch.object(wk, "run_as_abc", return_value=(0, "42|MERGED|2026-11-01T00:00:00Z", "")):
        assert wk.query_pr_state_by_branch_github("o/r", "task/probe-1-x") == (None, None)


def test_query_mr_state_by_branch_gitlab_opened_returns_id():
    """An opened MR for the branch is adopted."""
    mrs = [{"iid": 7, "state": "opened"}]
    with mock.patch.object(wk, "run_as_abc",
                           return_value=(0, '{"merge_requests": %s}' % json.dumps(mrs), "")):
        assert wk.query_mr_state_by_branch_gitlab("o/r", "task/probe-1-x") == ("7", "opened")


def test_query_mr_state_by_branch_gitlab_closed_returns_none():
    """A closed MR for the branch is not an association to adopt."""
    mrs = [{"iid": 7, "state": "closed"}]
    with mock.patch.object(wk, "run_as_abc",
                           return_value=(0, '{"merge_requests": %s}' % json.dumps(mrs), "")):
        assert wk.query_mr_state_by_branch_gitlab("o/r", "task/probe-1-x") == (None, None)


def test_query_mr_state_by_branch_gitlab_merged_returns_none():
    """A merged MR for the branch is not an association to adopt."""
    mrs = [{"iid": 7, "state": "merged"}]
    with mock.patch.object(wk, "run_as_abc",
                           return_value=(0, '{"merge_requests": %s}' % json.dumps(mrs), "")):
        assert wk.query_mr_state_by_branch_gitlab("o/r", "task/probe-1-x") == (None, None)


def test_killer_cycle_no_association_no_action():
    """No PR/MR association at all -> no action."""
    with _StateDir() as cfg:
        with _mock_worker_label_true():
            with mock.patch.object(wk.du, "log", lambda msg: None):
                wk.killer_cycle(cfg)
        assert wk.load_state() == {}


def test_killer_cycle_reverify_api_error_keeps_pending_shutdown():
    """A re-verify API error fails closed and keeps the pending shutdown.

    Cancelling on an API error would leave a worker running forever against
    a MR/PR that is still closed, so the grace entry must survive.
    """
    with _StateDir() as cfg:
        os.environ["MR_PR_ID"] = "42"
        os.environ["MR_PR_PROVIDER"] = "github"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        try:
            wk.save_state({"github:o/r:42": {"grace_start": int(time.time()) - 301}})

            # First query reports closed; the re-verify query errors out.
            calls = {"n": 0}

            def by_call(cmd, env=None, cwd=None):
                calls["n"] += 1
                if calls["n"] == 1:
                    return 0, "CLOSED|", ""
                return 1, "", "network error"

            with _mock_run_as_abc(side_effect=by_call), \
                    _mock_worker_label_true(), \
                    mock.patch.object(wk, "attempt_shutdown") as mock_shutdown:
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
                mock_shutdown.assert_not_called()
            # The pending shutdown survives, so the next poll re-verifies.
            entry = wk.load_state().get("github:o/r:42", {})
            assert "grace_start" in entry
        finally:
            for k in ("MR_PR_ID", "MR_PR_PROVIDER", "GIT_REPO_URL"):
                os.environ.pop(k, None)


def test_killer_cycle_label_check_fails_no_shutdown():
    """Safety gate: when dispatch.worker=true label is missing/falsy, no shutdown occurs."""
    with _StateDir() as cfg:
        os.environ["MR_PR_ID"] = "42"
        os.environ["MR_PR_PROVIDER"] = "github"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        try:
            wk.save_state({"github:o/r:42": {"grace_start": int(time.time()) - 301}})
            with _mock_run_as_abc(returncode=0, stdout="CLOSED|", stderr=""), \
                    _mock_worker_label_false(), \
                    mock.patch.object(wk, "attempt_shutdown") as mock_shutdown:
                with mock.patch.object(wk.du, "log", lambda msg: None):
                    wk.killer_cycle(cfg)
            mock_shutdown.assert_not_called()
            # Fail-closed: the pending shutdown is NOT cancelled, so it is
            # re-verified (label re-checked) on the next poll.
            assert "github:o/r:42" in wk.load_state()
        finally:
            for k in ("MR_PR_ID", "MR_PR_PROVIDER", "GIT_REPO_URL"):
                os.environ.pop(k, None)


# --------------------------------------------------------------------------- attempt_shutdown

def test_attempt_shutdown_execs_shutdown():
    with mock.patch.object(wk, "get_worker_branch", return_value="task/probe-1-x"), \
            mock.patch.object(wk, "run_as_abc", return_value=(0, "", "")) as mock_run, \
            mock.patch.object(wk.os, "execv") as mock_execv:
        wk.attempt_shutdown()
        mock_run.assert_called_once_with(
            ["git", "push", "origin", "HEAD:task/probe-1-x"], cwd=wk.WORKSPACE
        )
        mock_execv.assert_called_once_with("/usr/local/bin/shutdown", ["/usr/local/bin/shutdown"])


def test_attempt_shutdown_logs_push_failure_and_still_shuts_down():
    logs = []
    with mock.patch.object(wk, "get_worker_branch", return_value="task/probe-1-x"), \
            mock.patch.object(wk, "run_as_abc", return_value=(1, "", "rejected")), \
            mock.patch.object(wk.os, "execv") as mock_execv, \
            mock.patch.object(wk, "log", side_effect=logs.append):
        wk.attempt_shutdown()
    assert any("Push failed (ignored): rejected" in line for line in logs)
    mock_execv.assert_called_once_with("/usr/local/bin/shutdown", ["/usr/local/bin/shutdown"])


def test_get_worker_branch_handles_git_execution_error():
    with mock.patch.object(wk, "run_as_abc", side_effect=FileNotFoundError("no git")):
        assert wk.get_worker_branch() is None


# --------------------------------------------------------------------------- dispatcher contract: WORKER_KILLER is opt-in

def test_beads_dispatch_worker_env_has_worker_killer_when_opted_in():
    """Parent opts in via WORKER_KILLER_ENABLED=true: worker gets WORKER_KILLER=true."""
    bdd = _load("beads_dispatch", "beads-dispatch/beads_dispatch.py")
    env = bdd.compose_worker_env(
        parent_env=["WORKER_KILLER_ENABLED=true", "WORKER_KILLER=false"],
        branch="task/probe-1-x",
        repo_url="https://github.com/o/r.git",
        beads_remote="https://github.com/o/r.git"
    )
    killer_vals = [e for e in env if e.startswith("WORKER_KILLER=")]
    assert killer_vals == ["WORKER_KILLER=true"], killer_vals
    assert not [e for e in env if e.startswith("WORKER_KILLER_ENABLED=")]


def test_beads_dispatch_worker_env_no_worker_killer_when_not_opted_in():
    """No opt-in on the parent: worker gets no WORKER_KILLER at all, and an
    inherited WORKER_KILLER=true must not leak into the worker."""
    bdd = _load("beads_dispatch", "beads-dispatch/beads_dispatch.py")
    env = bdd.compose_worker_env(
        parent_env=["WORKER_KILLER=true"],
        branch="task/probe-1-x",
        repo_url="https://github.com/o/r.git",
        beads_remote="https://github.com/o/r.git"
    )
    assert not [e for e in env if e.startswith("WORKER_KILLER=")], env


def test_mr_pr_dispatch_worker_env_has_worker_killer_when_opted_in():
    """Parent opts in via WORKER_KILLER_ENABLED=true: worker gets WORKER_KILLER=true."""
    md = _load("mr_pr_dispatch", "mr_pr_dispatch.py")
    env = md.compose_worker_env(
        parent_env=["WORKER_KILLER_ENABLED=true", "WORKER_KILLER=false"],
        branch="feature/x",
        repo_url="https://github.com/o/r.git",
        mr_pr_id="42"
    )
    killer_vals = [e for e in env if e.startswith("WORKER_KILLER=")]
    assert killer_vals == ["WORKER_KILLER=true"], killer_vals
    assert not [e for e in env if e.startswith("WORKER_KILLER_ENABLED=")]


def test_mr_pr_dispatch_worker_env_no_worker_killer_when_not_opted_in():
    """No opt-in on the parent: worker gets no WORKER_KILLER at all, and an
    inherited WORKER_KILLER=true must not leak into the worker."""
    md = _load("mr_pr_dispatch", "mr_pr_dispatch.py")
    env = md.compose_worker_env(
        parent_env=["WORKER_KILLER=true"],
        branch="feature/x",
        repo_url="https://github.com/o/r.git",
        mr_pr_id="42"
    )
    assert not [e for e in env if e.startswith("WORKER_KILLER=")], env


# --------------------------------------------------------------------------- no PROMPT usage in PR creation

def test_default_dispatch_prompt_never_uses_PROMPT():
    """The default prompt must not reference PROMPT as a title/description source."""
    bdd = _load("beads_dispatch", "beads-dispatch/beads_dispatch.py")
    prompt = bdd.default_dispatch_prompt("probe-1", "task/probe-1-x", "https://github.com/o/r.git")
    # The prompt should NOT say to use PROMPT for PR title/description
    assert "PROMPT" not in prompt or "never from PROMPT" in prompt


# --------------------------------------------------------------------------- worker_pr_setup: run gating

def test_pr_setup_skips_in_parent_container():
    """The PR setup step must never run in a parent/dispatcher container."""
    for var in ("BEADS_DISPATCH", "MR_PR_DISPATCH"):
        os.environ[var] = "true"
        old_branch = os.environ.get("GIT_BRANCH_NAME")
        os.environ["GIT_BRANCH_NAME"] = "task/probe-1-x"
        try:
            assert wps.should_run() is False
        finally:
            os.environ.pop(var, None)
            if old_branch is None:
                os.environ.pop("GIT_BRANCH_NAME", None)
            else:
                os.environ["GIT_BRANCH_NAME"] = old_branch


def test_pr_setup_skips_non_task_branch():
    """MR/PR-dispatched workers already have their MR/PR: no creation step."""
    for var in ("BEADS_DISPATCH", "MR_PR_DISPATCH"):
        os.environ.pop(var, None)
    old = os.environ.get("GIT_BRANCH_NAME")
    os.environ["GIT_BRANCH_NAME"] = "feature/x"
    os.environ["WORKER_KILLER"] = "true"
    try:
        assert wps.should_run() is False
    finally:
        os.environ.pop("GIT_BRANCH_NAME", None)
        os.environ.pop("WORKER_KILLER", None)
        if old is not None:
            os.environ["GIT_BRANCH_NAME"] = old


def test_pr_setup_skips_when_killer_not_enabled():
    """No killer means no PR association is wanted."""
    for var in ("BEADS_DISPATCH", "MR_PR_DISPATCH"):
        os.environ.pop(var, None)
    old = os.environ.get("GIT_BRANCH_NAME")
    os.environ["GIT_BRANCH_NAME"] = "task/probe-1-x"
    os.environ.pop("WORKER_KILLER", None)
    try:
        assert wps.should_run() is False
    finally:
        for var in ("GIT_BRANCH_NAME", "WORKER_KILLER"):
            had = os.environ.get(var)
            os.environ.pop(var, None)
            if var == "GIT_BRANCH_NAME" and old is not None:
                os.environ[var] = old


def test_pr_setup_runs_for_beads_worker():
    """A beads-dispatched worker on a task branch with the killer on."""
    for var in ("BEADS_DISPATCH", "MR_PR_DISPATCH"):
        os.environ.pop(var, None)
    old = os.environ.get("GIT_BRANCH_NAME")
    os.environ["GIT_BRANCH_NAME"] = "task/probe-1-x"
    os.environ["WORKER_KILLER"] = "true"
    try:
        assert wps.should_run() is True
    finally:
        os.environ.pop("GIT_BRANCH_NAME", None)
        os.environ.pop("WORKER_KILLER", None)
        if old is not None:
            os.environ["GIT_BRANCH_NAME"] = old


# --------------------------------------------------------------------------- worker_pr_setup: bead id derivation

def test_derive_bead_id_from_branch():
    # Ids are matched against the beads DB: an id containing dashes is not
    # split incorrectly, and the DB is only consulted when needed.
    with mock.patch.object(wps, "_bead_ids_from_db", return_value=["probe-1", "probe-2"]):
        assert wps.derive_bead_id("task/probe-1-slug") == "probe-1"
        assert wps.derive_bead_id("task/probe-2-slug") == "probe-2"
    with mock.patch.object(wps, "_bead_ids_from_db",
                           return_value=["workspace-8ez.8", "workspace-ehp"]):
        assert wps.derive_bead_id("task/workspace-8ez.8-title") == "workspace-8ez.8"
        assert wps.derive_bead_id("task/workspace-ehp-slug") == "workspace-ehp"


def test_derive_bead_id_prefers_longest_prefix_match():
    """An id that is a prefix of another id must not win the shorter way."""
    with mock.patch.object(wps, "_bead_ids_from_db",
                           return_value=["workspace", "workspace-ehp"]):
        assert wps.derive_bead_id("task/workspace-ehp-slug") == "workspace-ehp"


def test_derive_bead_id_falls_back_without_db():
    """Without a beads DB, fall back to the first-dash split."""
    with mock.patch.object(wps, "_bead_ids_from_db", return_value=[]):
        assert wps.derive_bead_id("task/abc") == "abc"
        assert wps.derive_bead_id("task/probe-1-slug") == "probe"


# --------------------------------------------------------------------------- worker_pr_setup: empty-commit message content

def test_commit_message_carries_bead_id_and_title():
    """The --allow-empty commit's subject carries the bead id and title."""
    subject, body = wps.build_commit_message("probe-1", "Fix the login probe")
    assert "probe-1" in subject
    assert "Fix the login probe" in subject
    assert subject.startswith("WIP: ")
    assert "probe-1" in body


def test_commit_message_without_bead_title_uses_id_only():
    """bd show failed: the subject carries the id only — never PROMPT."""
    subject, body = wps.build_commit_message("probe-1", None)
    assert "probe-1" in subject
    assert subject.startswith("WIP: ")
    # No title, and certainly none sourced from PROMPT.
    assert "Fix" not in subject


def test_commit_message_never_references_prompt():
    """The commit message must never be derived from PROMPT."""
    os.environ["PROMPT"] = "SECRET PROMPT TITLE"
    try:
        subject, body = wps.build_commit_message("probe-1", None)
        assert "SECRET PROMPT TITLE" not in subject
        assert "SECRET PROMPT TITLE" not in body
        subject2, body2 = wps.build_commit_message("probe-1", "Real bead title")
        assert "SECRET PROMPT TITLE" not in subject2
    finally:
        os.environ.pop("PROMPT", None)


# --------------------------------------------------------------------------- worker_pr_setup: PR title/body sources

def test_pr_title_body_uses_bead_data():
    """Normal case: the bead's own title and description."""
    title, body = wps.build_pr_title_body("task/probe-1-x", "probe-1",
                                         "Fix the login probe", "It is broken.")
    assert title == "Fix the login probe"
    assert "It is broken." in body
    assert "probe-1" in body


def test_pr_title_body_bd_failure_fallback():
    """bd show failed: branch name is the title, placeholder is the body."""
    os.environ["PROMPT"] = "SECRET PROMPT TITLE"
    try:
        title, body = wps.build_pr_title_body("task/probe-1-x", "probe-1",
                                             None, None)
        assert title == "task/probe-1-x"
        assert "Placeholder" in body
        assert "bd show failed" in body
        assert "SECRET PROMPT TITLE" not in title
        assert "SECRET PROMPT TITLE" not in body
    finally:
        os.environ.pop("PROMPT", None)


def test_pr_title_body_never_uses_prompt():
    """PROMPT is never a title/description source, in any state."""
    os.environ["PROMPT"] = "SECRET PROMPT TITLE"
    try:
        for bead_title in (None, "Real bead title"):
            title, body = wps.build_pr_title_body("task/probe-1-x", "probe-1",
                                                 bead_title, "desc")
            assert "SECRET PROMPT TITLE" not in title
            assert "SECRET PROMPT TITLE" not in body
    finally:
        os.environ.pop("PROMPT", None)


# --------------------------------------------------------------------------- worker_pr_setup: existing-PR reuse

def test_find_existing_pr_github_reuses_single_match():
    """Exactly one PR for the branch: adopt it, never create a duplicate."""
    def by_cmd(cmd, env=None, cwd=None):
        # gh pr list -q prints "number|url" per line
        return 0, "42|https://github.com/o/r/pull/42", ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        pr_id, url = wps.find_existing_pr_github("o/r", "task/probe-1-x")
        assert pr_id == "42"
        assert "pull/42" in url


def test_find_existing_pr_github_no_match_returns_none():
    """No PR for the branch: return (None, None) so one is created."""
    with mock.patch.object(wps, "run_as_abc", return_value=(0, "", "")):
        assert wps.find_existing_pr_github("o/r", "task/probe-1-x") == (None, None)


def test_find_existing_pr_github_ambiguous_returns_none():
    """More than one PR for the branch: ambiguous, so never adopt one."""
    def by_cmd(cmd, env=None, cwd=None):
        return 0, "42|https://github.com/o/r/pull/42\n43|https://github.com/o/r/pull/43", ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        assert wps.find_existing_pr_github("o/r", "task/probe-1-x") == (None, None)


def test_find_existing_pr_github_error_returns_none():
    with mock.patch.object(wps, "run_as_abc", return_value=(1, "", "error")):
        assert wps.find_existing_pr_github("o/r", "task/probe-1-x") == (None, None)


def test_find_existing_pr_github_lists_open_only():
    """The reuse query must ask for open PRs only: a closed PR for the
    branch must never be adopted as the worker's association."""
    seen = {}

    def by_cmd(cmd, env=None, cwd=None):
        seen["cmd"] = cmd
        return 0, "42|https://github.com/o/r/pull/42", ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        pr_id, url = wps.find_existing_pr_github("o/r", "task/probe-1-x")
        assert pr_id == "42"
        assert "pull/42" in url
    assert "--state" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--state") + 1] == "open"


def test_find_existing_mr_gitlab_reuses_single_match():
    mrs = [{"iid": 7, "state": "opened", "web_url": "https://gitlab.com/o/r/-/merge_requests/7"}]
    with mock.patch.object(wps, "run_as_abc",
                           return_value=(0, '{"merge_requests": %s}' % json.dumps(mrs), "")):
        mr_id, url = wps.find_existing_mr_gitlab("o/r", "task/probe-1-x")
        assert mr_id == "7"
        assert "merge_requests/7" in url


def test_find_existing_mr_gitlab_no_match_returns_none():
    with mock.patch.object(wps, "run_as_abc", return_value=(0, "[]", "")):
        assert wps.find_existing_mr_gitlab("o/r", "task/probe-1-x") == (None, None)


def test_find_existing_mr_gitlab_ambiguous_returns_none():
    mrs = [{"iid": 7, "web_url": "u1"}, {"iid": 8, "web_url": "u2"}]
    with mock.patch.object(wps, "run_as_abc",
                           return_value=(0, '{"merge_requests": %s}' % json.dumps(mrs), "")):
        assert wps.find_existing_mr_gitlab("o/r", "task/probe-1-x") == (None, None)


def test_find_existing_mr_gitlab_error_returns_none():
    with mock.patch.object(wps, "run_as_abc", return_value=(1, "", "error")):
        assert wps.find_existing_mr_gitlab("o/r", "task/probe-1-x") == (None, None)


def test_find_existing_mr_gitlab_closed_returns_none():
    """A closed MR for the branch is not an association to adopt."""
    mrs = [{"iid": 7, "state": "closed", "web_url": "https://gitlab.com/o/r/-/merge_requests/7"}]
    with mock.patch.object(wps, "run_as_abc",
                           return_value=(0, '{"merge_requests": %s}' % json.dumps(mrs), "")):
        assert wps.find_existing_mr_gitlab("o/r", "task/probe-1-x") == (None, None)


def test_find_existing_mr_gitlab_merged_returns_none():
    """A merged MR for the branch is not an association to adopt."""
    mrs = [{"iid": 7, "state": "merged", "web_url": "https://gitlab.com/o/r/-/merge_requests/7"}]
    with mock.patch.object(wps, "run_as_abc",
                           return_value=(0, '{"merge_requests": %s}' % json.dumps(mrs), "")):
        assert wps.find_existing_mr_gitlab("o/r", "task/probe-1-x") == (None, None)


# --------------------------------------------------------------------------- worker_pr_setup: bead data lookup

def test_get_bead_info_from_bd_show():
    # Real `bd show <id> --json` (bd 1.3.2) returns a list with one issue
    # dict, not a bare dict — unwrapping it is what the worker actually does.
    data = [{"title": "Fix the login probe", "description": "It is broken."}]
    proc = mock.Mock()
    proc.returncode = 0
    proc.stdout = json.dumps(data)
    with mock.patch("subprocess.run", return_value=proc):
        title, description = wps.get_bead_info("probe-1")
        assert title == "Fix the login probe"
        assert description == "It is broken."


def test_get_bead_info_bd_show_empty_list_returns_none():
    """An empty list from `bd show` means the bead was not found."""
    proc = mock.Mock()
    proc.returncode = 0
    proc.stdout = "[]"
    with mock.patch("subprocess.run", return_value=proc):
        assert wps.get_bead_info("probe-1") == (None, None)


def test_get_bead_info_bd_show_failure_returns_none():
    """A bd failure degrades to the fallback rather than aborting PR creation."""
    proc = mock.Mock()
    proc.returncode = 1
    proc.stdout = ""
    with mock.patch("subprocess.run", return_value=proc):
        assert wps.get_bead_info("probe-1") == (None, None)


def test_get_bead_info_bd_show_non_json_returns_none():
    proc = mock.Mock()
    proc.returncode = 0
    proc.stdout = "not json"
    with mock.patch("subprocess.run", return_value=proc):
        assert wps.get_bead_info("probe-1") == (None, None)


# --------------------------------------------------------------------------- worker_pr_setup: push credentials

def test_push_branch_runs_as_abc_with_gh_credential_helper():
    """GitHub push: as abc, with gh as the credential helper.

    Regression test for the 2026-11-01 worker log: a plain `git push` as
    root has no credential helper, so git tried to prompt for a username
    and failed with exit 128 ("could not read Username ... No such device
    or address"), and no draft PR was ever created.
    """
    seen = {}

    def by_cmd(cmd, env=None, cwd=None):
        seen.update({"cmd": list(cmd), "env": env, "cwd": cwd})
        return 0, "", ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        proc = wps.push_branch("task/probe-1-x", "github")
    assert proc.returncode == 0
    assert seen["cmd"] == ["git", "-c",
                           "credential.helper=!gh auth git-credential",
                           "push", "-u", "origin", "task/probe-1-x"]
    assert seen["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_push_branch_runs_as_abc_with_glab_credential_helper():
    """GitLab push: as abc, with glab as the credential helper."""
    seen = {}

    def by_cmd(cmd, env=None, cwd=None):
        seen.update({"cmd": list(cmd)})
        return 0, "", ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        proc = wps.push_branch("task/probe-1-x", "gitlab")
    assert proc.returncode == 0
    assert "credential.helper=!glab auth git-credential" in seen["cmd"]


def test_push_branch_without_provider_still_runs_as_abc():
    """Unknown provider: still as abc (never a bare root `git push`), just
    with no provider helper configured."""
    seen = {}

    def by_cmd(cmd, env=None, cwd=None):
        seen.update({"cmd": list(cmd)})
        return 0, "", ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        proc = wps.push_branch("task/probe-1-x")
    assert proc.returncode == 0
    assert seen["cmd"] == ["git", "push", "-u", "origin", "task/probe-1-x"]
    assert not any("credential.helper" in arg for arg in seen["cmd"])


# --------------------------------------------------------------------------- worker_pr_setup: base branch

def test_resolve_default_branch_prefers_checkout_base_branch():
    """GIT_CHECKOUT_BASE_BRANCH wins: the task branch was cut from it, so
    the draft PR must target it, not the remote default (main)."""
    old = os.environ.get("GIT_CHECKOUT_BASE_BRANCH")
    os.environ["GIT_CHECKOUT_BASE_BRANCH"] = "beads"
    try:
        with mock.patch.object(wps, "git", side_effect=AssertionError("no git")):
            assert wps.resolve_default_branch() == "beads"
    finally:
        if old is None:
            os.environ.pop("GIT_CHECKOUT_BASE_BRANCH", None)
        else:
            os.environ["GIT_CHECKOUT_BASE_BRANCH"] = old


def test_resolve_default_branch_falls_back_to_remote_head():
    """No checkout base: the remote's default branch (remote HEAD)."""
    os.environ.pop("GIT_CHECKOUT_BASE_BRANCH", None)
    proc = subprocess.CompletedProcess([], 0, stdout="refs/remotes/origin/main\n")
    with mock.patch.object(wps, "git", return_value=proc):
        assert wps.resolve_default_branch() == "main"


def test_resolve_default_branch_blank_checkout_base_falls_back():
    """A blank GIT_CHECKOUT_BASE_BRANCH is treated as unset."""
    old = os.environ.get("GIT_CHECKOUT_BASE_BRANCH")
    os.environ["GIT_CHECKOUT_BASE_BRANCH"] = "   "
    try:
        proc = subprocess.CompletedProcess([], 0, stdout="refs/remotes/origin/beads\n")
        with mock.patch.object(wps, "git", return_value=proc):
            assert wps.resolve_default_branch() == "beads"
    finally:
        if old is None:
            os.environ.pop("GIT_CHECKOUT_BASE_BRANCH", None)
        else:
            os.environ["GIT_CHECKOUT_BASE_BRANCH"] = old


def test_resolve_default_branch_falls_back_to_main():
    """No checkout base and no remote HEAD: hardcoded "main"."""
    os.environ.pop("GIT_CHECKOUT_BASE_BRANCH", None)
    proc = subprocess.CompletedProcess([], 1, stdout="")
    with mock.patch.object(wps, "git", return_value=proc):
        assert wps.resolve_default_branch() == "main"


# --------------------------------------------------------------------------- worker_pr_setup: creation both providers

def test_create_draft_pr_github_parses_id_and_url():
    def by_cmd(cmd, env=None, cwd=None):
        assert "pr" in cmd and "create" in cmd
        assert "--draft" in cmd
        # Title/body must come from the caller, and --title must not be
        # sourced from PROMPT env.
        assert "SECRET PROMPT TITLE" not in cmd
        return 0, "https://github.com/o/r/pull/42\n", ""

    os.environ["PROMPT"] = "SECRET PROMPT TITLE"
    try:
        with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
            pr_id, url = wps.create_draft_pr_github("o/r", "task/probe-1-x",
                                                   "main", "Bead title", "Bead body")
            assert pr_id == "42"
            assert "pull/42" in url
    finally:
        os.environ.pop("PROMPT", None)


def test_create_draft_pr_github_failure_returns_none():
    with mock.patch.object(wps, "run_as_abc", return_value=(1, "", "gh failed")):
        assert wps.create_draft_pr_github("o/r", "task/probe-1-x", "main",
                                         "t", "b") == (None, None)


def test_create_draft_mr_gitlab_parses_id_and_url():
    def by_cmd(cmd, env=None, cwd=None):
        assert "mr" in cmd and "create" in cmd
        assert "--draft" in cmd
        assert "--yes" in cmd
        assert "SECRET PROMPT TITLE" not in cmd
        return 0, "https://gitlab.com/o/r/-/merge_requests/7\n", ""

    os.environ["PROMPT"] = "SECRET PROMPT TITLE"
    try:
        with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
            mr_id, url = wps.create_draft_mr_gitlab("o/r", "task/probe-1-x",
                                                   "main", "Bead title", "Bead body")
            assert mr_id == "7"
            assert "merge_requests/7" in url
    finally:
        os.environ.pop("PROMPT", None)


def test_create_draft_mr_gitlab_self_hosted_parses_url():
    """Self-hosted GitLab is not on gitlab.com: match the MR path shape."""
    def by_cmd(cmd, env=None, cwd=None):
        return 0, "https://gitlab.home.com/o/r/-/merge_requests/9\n", ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        mr_id, url = wps.create_draft_mr_gitlab("o/r", "task/probe-1-x",
                                               "main", "t", "b")
        assert mr_id == "9"
        assert "merge_requests/9" in url


def test_create_draft_mr_gitlab_failure_returns_none():
    with mock.patch.object(wps, "run_as_abc", return_value=(1, "", "glab failed")):
        assert wps.create_draft_mr_gitlab("o/r", "task/probe-1-x", "main",
                                         "t", "b") == (None, None)


# --------------------------------------------------------------------------- worker_pr_setup / worker_killer: gh/glab run in /workspace

def test_create_draft_mr_gitlab_runs_in_workspace():
    """glab shells out to git for repo context even with --repo given, so it
    must run in /workspace — run from the startup script's cwd it fails
    with 'Fatal: not a git repository'."""
    seen = {}

    def by_cmd(cmd, env=None, cwd=None):
        seen["cwd"] = cwd
        return 0, "https://gitlab.home.com/o/r/-/merge_requests/9\n", ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        wps.create_draft_mr_gitlab("o/r", "task/probe-1-x", "main", "t", "b")
    assert seen["cwd"] == wps.WORKSPACE


def test_create_draft_pr_github_runs_in_workspace():
    """Same working-directory requirement for the GitHub create path."""
    seen = {}

    def by_cmd(cmd, env=None, cwd=None):
        seen["cwd"] = cwd
        return 0, "https://github.com/o/r/pull/42\n", ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        wps.create_draft_pr_github("o/r", "task/probe-1-x", "main", "t", "b")
    assert seen["cwd"] == wps.WORKSPACE


def test_find_existing_mr_gitlab_runs_in_workspace():
    """glab mr list also needs the repo cwd, or it fails and silently
    returns no match, so an existing MR is never reused."""
    seen = {}
    mrs = [{"iid": 7, "state": "opened", "web_url": "https://gitlab.com/o/r/-/merge_requests/7"}]

    def by_cmd(cmd, env=None, cwd=None):
        seen["cwd"] = cwd
        return 0, '{"merge_requests": %s}' % json.dumps(mrs), ""

    with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd):
        assert wps.find_existing_mr_gitlab("o/r", "task/probe-1-x") == (
            "7", "https://gitlab.com/o/r/-/merge_requests/7")
    assert seen["cwd"] == wps.WORKSPACE


def test_query_mr_state_gitlab_runs_in_workspace():
    """The killer's glab mr view poll needs the repo cwd too, or the poll
    always errors and a GitLab worker never sees its MR close."""
    seen = {}

    def by_cmd(cmd, env=None, cwd=None):
        seen["cwd"] = cwd
        return 0, '{"state": "opened"}', ""

    with mock.patch.object(wk, "run_as_abc", side_effect=by_cmd):
        assert wk.query_mr_state_gitlab("o/r", "7") == ("opened", None)
    assert seen["cwd"] == wk.WORKSPACE


def test_query_mr_state_by_branch_gitlab_runs_in_workspace():
    """The killer's glab mr list branch lookup needs the repo cwd too."""
    seen = {}
    mrs = [{"iid": 7, "state": "opened"}]

    def by_cmd(cmd, env=None, cwd=None):
        seen["cwd"] = cwd
        return 0, '{"merge_requests": %s}' % json.dumps(mrs), ""

    with mock.patch.object(wk, "run_as_abc", side_effect=by_cmd):
        assert wk.query_mr_state_by_branch_gitlab("o/r", "task/probe-1-x") == ("7", "opened")
    assert seen["cwd"] == wk.WORKSPACE


# --------------------------------------------------------------------------- worker_pr_setup: provider/repo parsing

def test_pr_setup_parse_repo_url_strips_credentials():
    assert wps.parse_repo_url("https://user:token@github.com/o/r.git") == ("github.com", "o/r")
    assert wps.parse_repo_url("https://gitlab.home.com/o/r.git") == ("gitlab.home.com", "o/r")


def test_pr_setup_detect_provider():
    assert wps.detect_provider("github.com") == "github"
    assert wps.detect_provider("gitlab.com") == "gitlab"
    assert wps.detect_provider("gitlab.home.com", "gitlab") == "gitlab"
    assert wps.detect_provider("gitlab.home.com") is None


# --------------------------------------------------------------------------- subprocess contracts

def test_worker_pr_setup_run_as_abc_returns_tuple():
    completed = subprocess.CompletedProcess(
        args=["gh"], returncode=0, stdout="42|https://github.com/o/r/pull/42\n", stderr=""
    )
    with mock.patch.object(wps.subprocess, "run", return_value=completed):
        rc, out, err = wps.run_as_abc(["gh", "pr", "list"])
    assert (rc, out, err) == (0, completed.stdout, completed.stderr)


def test_worker_pr_setup_provider_lookup_accepts_completed_process():
    completed = subprocess.CompletedProcess(
        args=["gh"], returncode=0, stdout="42|https://github.com/o/r/pull/42\n", stderr=""
    )
    with mock.patch.object(wps.subprocess, "run", return_value=completed):
        assert wps.find_existing_pr_github("o/r", "task/probe-1-x") == (
            "42", "https://github.com/o/r/pull/42"
        )


def test_worker_killer_run_as_abc_returns_tuple():
    completed = subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout="task/probe-1-slug\n", stderr=""
    )
    with mock.patch.object(wk.subprocess, "run", return_value=completed):
        rc, out, err = wk.run_as_abc(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    assert (rc, out, err) == (0, completed.stdout, completed.stderr)


def test_get_worker_branch_reads_successful_output():
    with mock.patch.object(wk, "run_as_abc", return_value=(0, "task/probe-1-slug\n", "")):
        assert wk.get_worker_branch() == "task/probe-1-slug"


def test_get_worker_branch_returns_none_on_git_failure():
    with mock.patch.object(wk, "run_as_abc", return_value=(128, "", "not a git repository")):
        assert wk.get_worker_branch() is None


# --------------------------------------------------------------------------- worker_pr_setup: orchestration

def test_setup_reuses_existing_pr_and_skips_all_creation():
    """Existing PR: no commit, no push, no create — and the association is recorded."""
    with tempfile.TemporaryDirectory() as tmp:
        old_env = os.environ.copy()
        os.environ["GIT_BRANCH_NAME"] = "task/probe-1-x"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        os.environ["WORKER_KILLER"] = "true"
        for var in ("BEADS_DISPATCH", "MR_PR_DISPATCH", "PROMPT"):
            os.environ.pop(var, None)
        wps.PR_INFO_FILE = wk.Path(tmp, "worker-pr.json")
        try:
            def by_cmd(cmd, env=None, cwd=None):
                return 0, "42|https://github.com/o/r/pull/42", ""

            with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd), \
                    mock.patch.object(wps, "git", side_effect=AssertionError("no git")), \
                    mock.patch.object(wps, "get_bead_info", return_value=("t", "d")) as bead_info, \
                    mock.patch.object(wps, "push_branch", side_effect=AssertionError("no push")), \
                    mock.patch.object(wps, "record_on_bead") as record:
                result = wps.setup()
            assert result["created"] is True
            assert result["id"] == "42"
            # No PR creation happened.
            bead_info.assert_not_called()
            record.assert_called_once()
            # The association the killer reads.
            with open(wps.PR_INFO_FILE) as f:
                info = json.load(f)
            assert info["id"] == "42"
            assert info["provider"] == "github"
            assert info["branch"] == "task/probe-1-x"
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            wps.PR_INFO_FILE = wk.Path("/config/.worker-pr.json")


def test_setup_creates_draft_pr_when_none_exists():
    """No existing PR: commit, push, create, record — bead data drives the title."""
    with tempfile.TemporaryDirectory() as tmp:
        old_env = os.environ.copy()
        os.environ["GIT_BRANCH_NAME"] = "task/probe-1-x"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        os.environ["WORKER_KILLER"] = "true"
        for var in ("BEADS_DISPATCH", "MR_PR_DISPATCH"):
            os.environ.pop(var, None)
        wps.PR_INFO_FILE = wk.Path(tmp, "worker-pr.json")
        try:
            def lookup(cmd, env=None, cwd=None):
                return 0, "", ""  # no existing PR

            def create(cmd, env=None, cwd=None):
                return 0, "https://github.com/o/r/pull/42\n", ""

            created = {}
            with mock.patch.object(wps, "run_as_abc",
                                   side_effect=lambda cmd, **kw: (lookup(cmd, **kw) if "list" in cmd else create(cmd, **kw))), \
                    mock.patch.object(wps, "_bead_ids_from_db", return_value=["probe-1", "other"]), \
                    mock.patch.object(wps, "get_bead_info",
                                      return_value=("Fix the login probe", "It is broken.")), \
                    mock.patch.object(wps, "commit_empty", side_effect=lambda bid, bt: created.update({"commit": (bid, bt)})), \
                    mock.patch.object(wps, "push_branch", side_effect=lambda b, provider=None: created.update({"push": (b, provider)}) or subprocess.CompletedProcess([], 0)), \
                    mock.patch.object(wps, "branch_has_commits", return_value=False), \
                    mock.patch.object(wps, "resolve_default_branch", return_value="main"), \
                    mock.patch.object(wps, "record_on_bead"):
                result = wps.setup()
            assert result["created"] is True
            assert result["id"] == "42"
            # The --allow-empty commit carries bead id and title.
            assert created["commit"] == ("probe-1", "Fix the login probe")
            assert created["push"] == ("task/probe-1-x", "github")
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            wps.PR_INFO_FILE = wk.Path("/config/.worker-pr.json")


def test_setup_uses_fallback_title_when_bd_show_fails():
    """bd show failure: the commit subject and PR title fall back to the branch name."""
    with tempfile.TemporaryDirectory() as tmp:
        old_env = os.environ.copy()
        os.environ["GIT_BRANCH_NAME"] = "task/probe-1-x"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        os.environ["WORKER_KILLER"] = "true"
        os.environ["PROMPT"] = "SECRET PROMPT TITLE"
        for var in ("BEADS_DISPATCH", "MR_PR_DISPATCH"):
            os.environ.pop(var, None)
        wps.PR_INFO_FILE = wk.Path(tmp, "worker-pr.json")
        try:
            seen_title = {}

            def by_cmd(cmd, env=None, cwd=None):
                if "list" in cmd:
                    return 0, "", ""
                seen_title.update({"cmd": list(cmd)})
                return 0, "https://github.com/o/r/pull/42\n", ""

            with mock.patch.object(wps, "run_as_abc", side_effect=by_cmd), \
                    mock.patch.object(wps, "get_bead_info", return_value=(None, None)), \
                    mock.patch.object(wps, "branch_has_commits", return_value=False), \
                    mock.patch.object(wps, "resolve_default_branch", return_value="main"), \
                    mock.patch.object(wps, "commit_empty"), \
                    mock.patch.object(wps, "push_branch",
                                      return_value=subprocess.CompletedProcess([], 0)), \
                    mock.patch.object(wps, "record_on_bead"):
                result = wps.setup()
            assert result["created"] is True
            cmd = seen_title["cmd"]
            title_idx = cmd.index("--title") + 1
            assert cmd[title_idx] == "task/probe-1-x"
            assert "SECRET PROMPT TITLE" not in cmd
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            wps.PR_INFO_FILE = wk.Path("/config/.worker-pr.json")


def test_setup_push_failure_still_attempts_and_reports():
    """A push failure is logged and setup continues; creation then also fails
    gracefully and the killer falls back to a branch lookup."""
    with tempfile.TemporaryDirectory() as tmp:
        old_env = os.environ.copy()
        os.environ["GIT_BRANCH_NAME"] = "task/probe-1-x"
        os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
        os.environ["WORKER_KILLER"] = "true"
        for var in ("BEADS_DISPATCH", "MR_PR_DISPATCH"):
            os.environ.pop(var, None)
        wps.PR_INFO_FILE = wk.Path(tmp, "worker-pr.json")
        try:
            with mock.patch.object(wps, "run_as_abc", return_value=(0, "", "")), \
                    mock.patch.object(wps, "get_bead_info", return_value=("t", "d")), \
                    mock.patch.object(wps, "branch_has_commits", return_value=False), \
                    mock.patch.object(wps, "commit_empty"), \
                    mock.patch.object(wps, "push_branch",
                                      return_value=subprocess.CompletedProcess([], 1, "", "push failed")), \
                    mock.patch.object(wps, "record_on_bead") as record:
                result = wps.setup()
            # No PR was created (push failed, so gh pr create was never tried).
            assert result["created"] is False
            record.assert_not_called()
            # The state file still exists, so the killer can fall back to a
            # branch lookup rather than doing nothing.
            assert wps.PR_INFO_FILE.exists()
        finally:
            os.environ.clear()
            os.environ.update(old_env)
            wps.PR_INFO_FILE = wk.Path("/config/.worker-pr.json")


def test_setup_never_runs_in_mr_pr_worker():
    """An MR/PR-dispatched worker must not create a PR at startup."""
    with tempfile.TemporaryDirectory() as tmp:
        old_env = os.environ.copy()
        os.environ["BEADS_DISPATCH"] = "false"
        os.environ["MR_PR_DISPATCH"] = "false"
        os.environ["GIT_BRANCH_NAME"] = "feature/x"  # not a task branch
        os.environ["MR_PR_ID"] = "42"
        os.environ["WORKER_KILLER"] = "true"
        try:
            assert wps.should_run() is False
        finally:
            os.environ.clear()
            os.environ.update(old_env)


def test_main_is_noop_without_task_branch():
    old = {k: os.environ.get(k) for k in ("GIT_BRANCH_NAME", "BEADS_DISPATCH",
                                          "MR_PR_DISPATCH", "WORKER_KILLER")}
    os.environ.pop("BEADS_DISPATCH", None)
    os.environ.pop("MR_PR_DISPATCH", None)
    os.environ["GIT_BRANCH_NAME"] = "feature/x"
    os.environ["WORKER_KILLER"] = "true"
    try:
        with mock.patch.object(wps, "setup", side_effect=AssertionError("setup ran")):
            assert wps.main([]) == 0
    finally:
        for key, val in old.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val


def test_main_swallows_setup_errors():
    """A setup failure must never abort container startup."""
    old = {k: os.environ.get(k) for k in ("GIT_BRANCH_NAME", "GIT_REPO_URL",
                                          "BEADS_DISPATCH", "MR_PR_DISPATCH",
                                          "WORKER_KILLER")}
    os.environ.pop("BEADS_DISPATCH", None)
    os.environ.pop("MR_PR_DISPATCH", None)
    os.environ["GIT_BRANCH_NAME"] = "task/probe-1-x"
    os.environ["GIT_REPO_URL"] = "https://github.com/o/r.git"
    os.environ["WORKER_KILLER"] = "true"
    try:
        with mock.patch.object(wps, "setup", side_effect=RuntimeError("boom")):
            assert wps.main([]) == 0
    finally:
        for key, val in old.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val


def test_state_file_matches_killer_default():
    """The state file worker_pr_setup writes is the one worker_killer reads."""
    assert str(SETUP_DEFAULT_PR_INFO) == "/config/.worker-pr.json"
    assert str(KILLER_DEFAULT_PR_INFO) == "/config/.worker-pr.json"
    assert str(SETUP_DEFAULT_PR_INFO) == str(KILLER_DEFAULT_PR_INFO)


def test_killer_state_paths_honor_shared_overrides():
    state_dir = "/tmp/custom-killer-state"
    pr_info_file = "/tmp/custom-worker-pr.json"
    with mock.patch.dict(os.environ, {
        "WORKER_KILLER_STATE_DIR": state_dir,
        "WORKER_PR_STATE_FILE": pr_info_file,
    }):
        # Reload to exercise import-time path configuration.
        module = _load("worker_killer_overrides", "worker_killer.py")
    assert str(module.STATE_FILE) == state_dir + "/state.json"
    assert str(module.PR_INFO_FILE) == pr_info_file


if __name__ == "__main__":
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except Exception:
                failures += 1
                print("FAIL %s" % name)
                traceback.print_exc()
    sys.exit(1 if failures else 0)