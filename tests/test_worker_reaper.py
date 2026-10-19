"""Unit tests for the Worker Reaper daemon.

The acceptance criteria from the issue, covered here:
  * seen-up-then-down removal (swarm and local dispatch modes)
  * never-seen-up preservation (the created-but-not-started race)
  * out-of-band removal tolerance (state entry for a missing worker is dropped)
  * state survives a restart (fresh Config/process against the same state dir)
  * docker socket unavailable -> skip cycle, state untouched
  * both dispatchers stamp the dispatch.worker label and disable the reaper
    inside workers

The repo copies of the modules under test are loaded via importlib so the
tests exercise the working tree, not a possibly stale install in
/usr/local/bin.

Run with: python3 -m pytest tests/test_worker_reaper.py
"""

import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import time
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))

# Make dispatch_utils importable (the modules under test do `import dispatch_utils`).
sys.path.insert(0, "/usr/local/bin")
sys.path.insert(0, os.path.join(HERE, "..", "beads-dispatch"))


def _load(name, relpath):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(HERE, "..", relpath))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


wr = _load("worker_reaper", "worker_reaper.py")
bdd = _load("beads_dispatch", "beads-dispatch/beads_dispatch.py")
md = _load("mr_pr_dispatch", "mr_pr_dispatch.py")

# Worker names as both dispatchers generate them: prefix + slug/id + a 20-digit
# timestamp suffix (%Y%m%d%H%M%S%f).
W1 = "beads-fix-login-probe-1-20260101000000000001"
W2 = "mr-pr-update-readme-42-20260101000000000002"


class _StateDir:
    """Context manager: a fresh reaper Config on an isolated state dir."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp(prefix="worker-reaper-test-")
        self._old_env = {
            "WORKER_REAPER_STATE_DIR": os.environ.get("WORKER_REAPER_STATE_DIR"),
            "WORKER_REAPER_INTERVAL": os.environ.get("WORKER_REAPER_INTERVAL"),
        }
        os.environ["WORKER_REAPER_STATE_DIR"] = self.dir
        os.environ["WORKER_REAPER_INTERVAL"] = "60"
        self.cfg = wr.Config()
        return self.cfg

    def __exit__(self, *exc):
        for key, val in self._old_env.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val
        shutil.rmtree(self.dir, ignore_errors=True)

    def state(self):
        """The state file's current contents ({name: ts})."""
        with open(wr.state_path(self.cfg)) as fh:
            return json.load(fh).get("seen_up", {})


def _swarm_ls(running="1/1", extra=""):
    """Fake `docker service ls` (unfiltered pass; label-filtered pass)."""
    def fake_run(cmd, **kwargs):
        assert cmd[:3] == ["docker", "service", "ls"], cmd
        if "--filter" in cmd:
            return (0, extra, "")
        return (0, running, "")
    return mock.patch.object(wr.du, "run", side_effect=fake_run)


# --------------------------------------------------------------------------- is_worker

def test_is_worker_accepts_dispatch_label():
    # The label alone identifies a worker, whatever the name.
    assert wr.is_worker("anything-at-all", {wr.WORKER_LABEL: "true"})


def test_is_worker_accepts_dispatch_id_labels():
    # The per-dispatcher id labels count too (workers dispatched before the
    # shared worker label existed carry these).
    assert wr.is_worker(W2, {"mr_pr.id": "42"})
    assert wr.is_worker(W1, {"beads.issue": "probe-1"})


def test_is_worker_accepts_worker_name_pattern():
    # Fallback identification for legacy (pre-label) workers: prefix + the
    # dispatchers' 20-digit timestamp suffix.
    assert wr.is_worker(W1)
    assert wr.is_worker(W2)
    assert re.search(r"-[0-9]{20}$", W1)


def test_is_worker_rejects_non_workers():
    # Node residents and the dispatcher itself must never match: no timestamp
    # suffix, or an unrelated prefix.
    for name in ("vscode-claude", "postgres", "buildx_buildkit_x",
                 "beads-fleet-admiral", "mr-pr-42", "claude-dev", None, ""):
        assert not wr.is_worker(name), name


def test_replicas_running_parses_running_count():
    assert wr.replicas_running("1/1") == 1
    assert wr.replicas_running("0/1") == 0
    assert wr.replicas_running("3/5") == 3
    assert wr.replicas_running("") == 0
    assert wr.replicas_running("garbage") == 0


# --------------------------------------------------------------------------- enumeration

def test_list_swarm_workers_matches_by_name_and_label():
    running_svc = W1 + "\t1/1"
    noise = "postgres\t1/1"
    # Label-tagged service whose name does NOT match the worker pattern
    # (only the label filter finds it).
    labeled = "custom-named-worker\t0/1"
    with _swarm_ls(running=running_svc + "\n" + noise, extra=labeled):
        workers = wr.list_swarm_workers()
    assert workers == {W1: True, "custom-named-worker": False}


def test_list_swarm_workers_returns_none_when_docker_unavailable():
    with mock.patch.object(wr.du, "run", return_value=(1, "", "cannot connect")):
        assert wr.list_swarm_workers() is None


def test_list_local_workers_parses_containers_skips_swarm_tasks():
    lines = [
        # name, state, dispatch.worker, mr_pr.id, com.docker.swarm.service.name
        W1 + "\trunning\ttrue\t\t",
        W2 + "\texited\t\t42\t",
        "postgres\trunning\t\t\t",
        # A swarm task container: its lifecycle belongs to the service, which a
        # swarm manager's reaper reaps. Never rm it from under the service.
        W2 + "\trunning\t\t\tmr-pr-update-readme-42-svc",
        # A "created" (never started) container: a worker, but not running.
        "beads-starting-probe-9-20260101000000000009\tcreated\ttrue\t\t",
    ]
    with mock.patch.object(wr.du, "run", return_value=(0, "\n".join(lines), "")):
        workers = wr.list_local_workers()
    assert workers == {
        W1: True,
        W2: False,
        "beads-starting-probe-9-20260101000000000009": False,
    }


def test_list_local_workers_returns_none_when_docker_unavailable():
    with mock.patch.object(wr.du, "run", return_value=(1, "", "cannot connect")):
        assert wr.list_local_workers() is None


# --------------------------------------------------------------------------- reap cycle

def test_reap_removes_seen_up_then_down_local():
    # Local mode: seen UP in one cycle, exited in the next -> docker rm.
    calls = []
    with _StateDir() as cfg:
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_local_workers", return_value={W1: True}):
                wr.reap_cycle(cfg, swarm=False)
            assert W1 in wr.load_reaper_state(wr.state_path(cfg))
            with mock.patch.object(wr, "list_local_workers", return_value={W1: False}), \
                    mock.patch.object(wr.du, "run",
                                      side_effect=lambda cmd, **kw: calls.append(cmd) or (0, "", "")):
                result = wr.reap_cycle(cfg, swarm=False)
    assert result["removed"] == [W1]
    assert calls == [["docker", "rm", W1]]
    # Local-mode removal never force-removes (a running container survives a
    # failed rm and is retried next cycle).


def test_reap_removes_seen_up_then_down_swarm():
    # Swarm mode: seen UP, service now has no running tasks -> docker service rm
    # (task state double-checked first).
    calls = []
    with _StateDir() as cfg:
        wr.save_reaper_state(wr.state_path(cfg), {W1: 1700000000})
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_swarm_workers", return_value={W1: False}), \
                    mock.patch.object(wr, "swarm_service_running", return_value=False), \
                    mock.patch.object(wr.du, "run",
                                      side_effect=lambda cmd, **kw: calls.append(cmd) or (0, "", "")):
                result = wr.reap_cycle(cfg, swarm=True)
    assert result["removed"] == [W1]
    assert calls == [["docker", "service", "rm", W1]]


def test_reap_preserves_never_seen_up():
    # A worker observed DOWN with no prior UP observation (created but not
    # started yet, or finished faster than one interval) is NEVER removed.
    calls = []
    with _StateDir() as cfg:
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_local_workers", return_value={W1: False, W2: False}), \
                    mock.patch.object(wr.du, "run",
                                      side_effect=lambda cmd, **kw: calls.append(cmd) or (0, "", "")):
                result = wr.reap_cycle(cfg, swarm=False)
        assert calls == []
        assert result["removed"] == []
        # Nothing was observed UP, so nothing is recorded either.
        assert wr.load_reaper_state(wr.state_path(cfg)) == {}


def test_reap_tolerates_out_of_band_removal():
    # A worker removed by hand (or by another reaper) just drops its entry.
    calls = []
    with _StateDir() as cfg:
        wr.save_reaper_state(wr.state_path(cfg), {W1: 1700000000, W2: 1700000000})
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_local_workers", return_value={}), \
                    mock.patch.object(wr.du, "run",
                                      side_effect=lambda cmd, **kw: calls.append(cmd) or (0, "", "")):
                result = wr.reap_cycle(cfg, swarm=False)
            assert result["removed"] == []
            assert calls == []
            assert wr.load_reaper_state(wr.state_path(cfg)) == {}
        # A still-running worker is unaffected.
        wr.save_reaper_state(wr.state_path(cfg), {W2: 1700000000})
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_local_workers", return_value={W2: True}), \
                    mock.patch.object(wr.du, "run", return_value=(0, "", "")):
                result = wr.reap_cycle(cfg, swarm=False)
            assert result["removed"] == []
            assert W2 in wr.load_reaper_state(wr.state_path(cfg))


def test_reap_skips_cycle_when_docker_unavailable():
    # Socket hiccup: skip the cycle entirely and leave state untouched.
    with _StateDir() as cfg:
        wr.save_reaper_state(wr.state_path(cfg), {W1: 1700000000})
        before = wr.load_reaper_state(wr.state_path(cfg))
        with mock.patch.object(wr, "list_local_workers", return_value=None), \
                mock.patch.object(wr.du, "log", lambda msg: None):
            result = wr.reap_cycle(cfg, swarm=False)
        assert result["skipped"] is True
        assert wr.load_reaper_state(wr.state_path(cfg)) == before


def test_reap_swarm_double_check_running_prevents_removal():
    # Enumerated as down (0/1) but the task-state check shows Running: keep it.
    calls = []
    with _StateDir() as cfg:
        wr.save_reaper_state(wr.state_path(cfg), {W1: 1700000000})
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_swarm_workers", return_value={W1: False}), \
                    mock.patch.object(wr, "swarm_service_running", return_value=True), \
                    mock.patch.object(wr.du, "run",
                                      side_effect=lambda cmd, **kw: calls.append(cmd) or (0, "", "")):
                result = wr.reap_cycle(cfg, swarm=True)
        assert result["removed"] == []
        assert calls == []
        assert W1 in wr.load_reaper_state(wr.state_path(cfg))


def test_reap_swarm_double_check_unknown_retries_next_cycle():
    # Task state undeterminable (docker error): skip, keep the entry.
    calls = []
    with _StateDir() as cfg:
        wr.save_reaper_state(wr.state_path(cfg), {W1: 1700000000})
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_swarm_workers", return_value={W1: False}), \
                    mock.patch.object(wr, "swarm_service_running", return_value=None), \
                    mock.patch.object(wr.du, "run",
                                      side_effect=lambda cmd, **kw: calls.append(cmd) or (0, "", "")):
                result = wr.reap_cycle(cfg, swarm=True)
        assert result["removed"] == []
        assert calls == []
        assert W1 in wr.load_reaper_state(wr.state_path(cfg))


def test_reap_swarm_records_up_via_task_state_when_replicas_lag():
    # Resilience to a stale/drifting service-ls replicas snapshot: task state
    # is the authority, so a worker reported down but really running gets its
    # UP observation recorded (instead of never becoming reapable later).
    calls = []
    with _StateDir() as cfg:
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_swarm_workers", return_value={W1: False}), \
                    mock.patch.object(wr, "swarm_service_running", return_value=True), \
                    mock.patch.object(wr.du, "run",
                                      side_effect=lambda cmd, **kw: calls.append(cmd) or (0, "", "")):
                result = wr.reap_cycle(cfg, swarm=True)
        assert result["removed"] == []
        assert calls == []
        assert W1 in wr.load_reaper_state(wr.state_path(cfg))


def test_reap_removal_failure_keeps_entry_for_retry():
    calls = []
    with _StateDir() as cfg:
        wr.save_reaper_state(wr.state_path(cfg), {W1: 1700000000})
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_local_workers", return_value={W1: False}), \
                    mock.patch.object(wr.du, "run",
                                      side_effect=lambda cmd, **kw: (calls.append(cmd), (1, "", "driver error"))[1]):
                result = wr.reap_cycle(cfg, swarm=False)
        assert result["removed"] == []
        assert calls == [["docker", "rm", W1]]
        assert W1 in wr.load_reaper_state(wr.state_path(cfg))


def test_reap_removal_raced_out_of_band_drops_entry():
    # The worker vanished between enumeration and removal: same net effect,
    # the entry is dropped instead of retrying forever.
    with _StateDir() as cfg:
        wr.save_reaper_state(wr.state_path(cfg), {W1: 1700000000})
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_local_workers", return_value={W1: False}), \
                    mock.patch.object(wr.du, "run",
                                      return_value=(1, "", "Error: No such container: " + W1)):
                result = wr.reap_cycle(cfg, swarm=False)
        assert result["removed"] == [W1]
        assert wr.load_reaper_state(wr.state_path(cfg)) == {}


def test_reap_logs_removal_with_name_and_reason():
    logged = []
    with _StateDir() as cfg:
        wr.save_reaper_state(wr.state_path(cfg), {W1: 1700000000})
        with mock.patch.object(wr.du, "log", lambda msg: logged.append(msg)):
            with mock.patch.object(wr, "list_local_workers", return_value={W1: False}), \
                    mock.patch.object(wr.du, "run", return_value=(0, "", "")):
                wr.reap_cycle(cfg, swarm=False)
    joined = "\n".join(logged)
    assert W1 in joined, joined
    assert "Reaped worker" in joined and "now down" in joined, joined


def test_state_survives_restart_without_leaking():
    # The seen-up observation must persist: a restart (fresh Config, same
    # state dir) must still reap the worker when it comes back down, rather
    # than forgetting it was ever up (and leaking it) or double-deciding.
    removed = []
    with _StateDir() as cfg:
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_local_workers", return_value={W1: True}):
                wr.reap_cycle(cfg, swarm=False)
        # "Restart the container": new Config instance against the same state dir.
        cfg2 = wr.Config()
        with mock.patch.object(wr.du, "log", lambda msg: None):
            with mock.patch.object(wr, "list_local_workers", return_value={W1: True}):
                wr.reap_cycle(cfg2, swarm=False)
            assert W1 in wr.load_reaper_state(wr.state_path(cfg2))
            # Back down after the restart: the persisted observation reaps it.
            with mock.patch.object(wr, "list_local_workers", return_value={W1: False}), \
                    mock.patch.object(wr.du, "run",
                                      side_effect=lambda cmd, **kw: (removed.append(cmd), (0, "", ""))[1]):
                result = wr.reap_cycle(cfg2, swarm=False)
        assert result["removed"] == [W1]
    assert removed == [["docker", "rm", W1]]


def test_reap_cycle_records_first_up_observation_once():
    # The seen_up timestamp is the first observation (not refreshed), so a
    # worker's "has been up" fact is stable across cycles.
    with _StateDir() as cfg:
        with mock.patch.object(wr.du, "log", lambda msg: None), \
                mock.patch.object(wr, "list_local_workers", return_value={W1: True}):
            wr.reap_cycle(cfg, swarm=False)
            first = wr.load_reaper_state(wr.state_path(cfg))[W1]
            time.sleep(1.1)  # a later cycle at a visibly later second
            wr.reap_cycle(cfg, swarm=False)
            assert wr.load_reaper_state(wr.state_path(cfg))[W1] == first


# --------------------------------------------------------------------------- main gates

def test_main_not_enabled_is_noop():
    # Consistent with the dispatchers' opt-in: WORKER_REAPER != 'true' exits
    # before any docker interaction.
    old = os.environ.pop("WORKER_REAPER", None)
    try:
        with mock.patch.object(wr.du, "run", side_effect=AssertionError("docker called")):
            assert wr.main([]) == 0
    finally:
        if old is not None:
            os.environ["WORKER_REAPER"] = old


def test_main_exits_when_docker_socket_missing():
    os.environ["WORKER_REAPER"] = "true"
    try:
        with mock.patch("shutil.which", return_value="/usr/bin/docker"), \
                mock.patch.object(os.path, "exists", return_value=False), \
                mock.patch.object(wr.du, "run", side_effect=AssertionError("docker called")):
            assert wr.main([]) == 0
    finally:
        os.environ.pop("WORKER_REAPER", None)


def test_main_once_runs_single_cycle():
    os.environ["WORKER_REAPER"] = "true"
    try:
        with mock.patch("shutil.which", return_value="/usr/bin/docker"), \
                mock.patch.object(os.path, "exists",
                                  side_effect=lambda p: p in wr.DOCKER_SOCKET_PATHS), \
                mock.patch.object(wr.du, "is_swarm_manager", return_value=False), \
                mock.patch.object(wr, "reap_cycle") as cycle:
            assert wr.main(["--once"]) == 0
        assert cycle.call_count == 1
    finally:
        os.environ.pop("WORKER_REAPER", None)


# --------------------------------------------------------------------------- dispatcher contract

def test_beads_dispatch_stamps_worker_label():
    # The reaper identifies workers by label: beads-dispatch must stamp
    # dispatch.worker=true plus the issue id, in both dispatch modes.
    for swarm in (False, True):
        captured = {}
        fake = (lambda worker, image, env, port, worker_port, issue_id, net=None, labels=None:
                (captured.update({"worker": worker, "labels": labels}), (0, "created", ""))[1])
        with mock.patch.object(bdd.du, "env", side_effect=lambda name, default=None: default), \
                mock.patch.object(bdd.du, "get_workspace_owner", return_value="abc"), \
                mock.patch.object(bdd.du, "derive_git_repo_url",
                                  return_value="https://github.com/o/r.git"), \
                mock.patch.object(bdd.du, "find_free_host_port", return_value=8001), \
                mock.patch.object(bdd.du, "is_swarm_manager", return_value=swarm), \
                mock.patch.object(bdd.du, "worker_exists", return_value=False), \
                mock.patch.object(bdd.du, "log", lambda msg: None), \
                mock.patch.object(bdd, "dolt_remote_add", return_value=False):
            if swarm:
                with mock.patch.object(bdd.du, "dispatch_swarm", fake):
                    assert bdd.dispatch_worker(
                        {"id": "probe-1", "title": "Task A"}, bdd.Config(),
                        {"image": "img:1", "env": [], "name": "parent"}) is True
            else:
                with mock.patch.object(bdd.du, "dispatch_local", fake):
                    assert bdd.dispatch_worker(
                        {"id": "probe-1", "title": "Task A"}, bdd.Config(),
                        {"image": "img:1", "env": [], "name": "parent"}) is True
        assert captured["labels"] == {"beads.issue": "probe-1", "dispatch.worker": "true"}
        assert wr.is_worker(captured["worker"])


def test_mr_pr_dispatch_stamps_worker_label():
    captured = {}

    def fake_dispatch_local(worker, image, env, port, worker_port,
                            restart_policy, mr_pr_id, net=None, labels=None):
        captured.update({"worker": worker, "labels": labels})
        return 0, "created", ""

    with mock.patch.object(md.du, "is_swarm_manager", return_value=False), \
            mock.patch.object(md.du, "dispatch_local", fake_dispatch_local), \
            mock.patch.object(md.du, "find_free_host_port", return_value=8100), \
            mock.patch.object(md.du, "env", side_effect=lambda name, default=None: default), \
            mock.patch.object(md.du, "get_workspace_owner", return_value="abc"), \
            mock.patch.object(md.du, "log", lambda msg: None):
        info = {
            "mr_pr_id": "42",
            "title": "Update README",
            "branch": "feature/x",
            "repo_url": "https://github.com/o/r.git",
            "provider": "github",
        }
        assert md.dispatch_mr_pr_worker(info, md.Config(),
                                        {"image": "img:1", "env": [], "restart_policy": ""}) is True
    assert captured["labels"] == {
        "mr_pr.id": "42", "mr_pr.provider": "github", "dispatch.worker": "true"}
    assert wr.is_worker(captured["worker"])


def test_worker_env_disables_nested_reaper():
    # Workers never run their own reaper (like the other dispatch daemons):
    # an overridden parent WORKER_REAPER must be turned off inside the worker.
    for env in (bdd.compose_worker_env(["WORKER_REAPER=true"], "task/probe-1-x",
                                       "https://github.com/o/r.git"),
                md.compose_worker_env(["WORKER_REAPER=true"], "feature/x",
                                      "https://github.com/o/r.git", "42")):
        reaper_vals = [e for e in env if e.startswith("WORKER_REAPER=")]
        assert reaper_vals == ["WORKER_REAPER=false"], reaper_vals


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
