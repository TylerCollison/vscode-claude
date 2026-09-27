"""Functional tests for configure-beads.sh BEADS_ENABLED gating.

Runs the real script against a stub `bd` binary that logs its invocations, and
asserts on which beads operations ran for each env combination.

Run with: python3 -m pytest tests/test_configure_beads.py
"""

import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "configure-beads.sh")

STUB_BD = """#!/bin/bash
echo "$*" >> "{calls}"
case "$1" in
  --version) echo "bd version 1.0.0-test" ;;
  bootstrap) exit {bootstrap_rc} ;;
  init) exit 0 ;;
  *) exit 0 ;;
esac
"""


def run_configure_beads(tmp_path, env, bootstrap_rc=1):
    """Run configure-beads.sh with a stub bd; return (log, calls, workspace)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    calls = tmp_path / "calls.log"
    calls.write_text("")
    (bin_dir / "bd").write_text(STUB_BD.format(calls=calls, bootstrap_rc=bootstrap_rc))
    (bin_dir / "bd").chmod(0o755)

    workspace = tmp_path / "ws"
    workspace.mkdir(exist_ok=True)

    full_env = {
        "PATH": "%s:/usr/bin:/bin" % bin_dir,
        "HOME": "/root",
        "DEFAULT_WORKSPACE": str(workspace),
    }
    full_env.update(env)
    proc = subprocess.run(
        ["bash", SCRIPT], env=full_env, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout, calls.read_text(), workspace


def test_no_beads_enabled_no_init_no_sync(tmp_path):
    # A plain container that never opted into beads gets no beads setup at all:
    # no bd init, no .beads/ in the workspace, no dolt remote add / bootstrap.
    log, calls, workspace = run_configure_beads(tmp_path, {})
    assert "init" not in calls.replace("--version", ""), calls
    assert "bootstrap" not in calls, calls
    assert "dolt" not in calls, calls
    assert "Skipping bd init" in log
    assert not (workspace / ".beads").exists()


def test_no_beads_enabled_git_repo_url_does_not_trigger_sync(tmp_path):
    # The GIT_REPO_URL / git-origin fallback must not apply without opt-in:
    # this is the reported bug (beads init in a workspace the user never
    # opted into beads for).
    log, calls, workspace = run_configure_beads(
        tmp_path, {"GIT_REPO_URL": "https://example.com/repo.git"})
    assert "dolt" not in calls, calls
    assert "bootstrap" not in calls, calls
    assert "Skipping bd init" in log
    assert not (workspace / ".beads").exists()


def test_beads_enabled_true_preserves_init_and_sync(tmp_path):
    # With BEADS_ENABLED=true the fallback chain applies: GIT_REPO_URL resolves
    # a remote, the sync block runs, and the parent pushes (BEADS_DISPATCH not
    # 'false'). bootstrap succeeds here, so bd init is not run.
    log, calls, _ = run_configure_beads(
        tmp_path, {"BEADS_ENABLED": "true", "GIT_REPO_URL": "https://example.com/repo.git"},
        bootstrap_rc=0)
    assert "dolt remote add origin https://example.com/repo.git" in calls, calls
    assert "bootstrap --yes" in calls, calls
    assert "dolt push" in calls, calls
    assert "Bootstrapped Beads database" in log
    assert "init\n" not in calls, calls  # no bd init after a successful bootstrap


def test_beads_enabled_true_init_fallback_without_remote(tmp_path):
    # Opted in but no remote: the sync block is skipped and bd init runs
    # (pre-c5f3ef8 behavior for opted-in containers).
    log, calls, workspace = run_configure_beads(tmp_path, {"BEADS_ENABLED": "true"})
    assert "init\n" in calls, calls
    assert "dolt" not in calls, calls
    assert "Beads initialized" in log


def test_worker_beads_remote_bootstraps_without_beads_enabled(tmp_path):
    # Worker containers (BEADS_REMOTE set by the dispatcher, BEADS_ENABLED=false,
    # BEADS_DISPATCH=false): bootstrap the task DB from BEADS_REMOTE on startup,
    # never run bd init, and never push back.
    log, calls, _ = run_configure_beads(
        tmp_path,
        {"BEADS_ENABLED": "false", "BEADS_REMOTE": "https://example.com/repo.git",
         "BEADS_DISPATCH": "false"},
        bootstrap_rc=0)
    assert "dolt remote add origin https://example.com/repo.git" in calls, calls
    assert "bootstrap --yes" in calls, calls
    assert "dolt push" not in calls, calls  # workers never push back
    assert "init\n" not in calls, calls  # workers rely on the bootstrap, not bd init
    assert "Bootstrapped Beads database" in log


def test_worker_bootstrap_failure_does_not_run_bd_init(tmp_path):
    # If the remote has no Dolt data (bootstrap fails), a worker (BEADS_ENABLED
    # false, not stealth) must not fall back to bd init — a fresh init would
    # create an empty DB without the parent's tasks.
    log, calls, _ = run_configure_beads(
        tmp_path,
        {"BEADS_ENABLED": "false", "BEADS_REMOTE": "https://example.com/repo.git",
         "BEADS_DISPATCH": "false"},
        bootstrap_rc=1)
    assert "bootstrap --yes" in calls, calls
    assert "init\n" not in calls, calls
    assert "Skipping bd init" in log


def test_stealth_mode_implies_opt_in_for_init(tmp_path):
    # Stealth mode (BEADS_DIR set) implies opt-in for init: bd init
    # --quiet --stealth runs at $BEADS_DIR even without BEADS_ENABLED=true.
    beads_dir = tmp_path / "stealth"
    beads_dir.mkdir(exist_ok=True)
    log, calls, _ = run_configure_beads(tmp_path, {"BEADS_DIR": str(beads_dir)})
    assert "init --quiet --stealth" in calls, calls
    assert "Beads initialized" in log
    assert "dolt" not in calls, calls  # no remote configured -> no sync
