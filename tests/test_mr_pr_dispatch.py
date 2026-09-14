"""Unit tests for the MR/PR Dispatcher daemon.

Run with: python3 -m pytest tests/test_mr_pr_dispatch.py
"""

import importlib.util
import os
import re
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))

# Make dispatch_utils importable (mr_pr_dispatch.py does `import dispatch_utils`).
sys.path.insert(0, os.path.join(HERE, "..", "beads-dispatch"))
sys.path.insert(0, "/usr/local/bin")

SPEC = importlib.util.spec_from_file_location(
    "mr_pr_dispatch", os.path.join(HERE, "..", "mr_pr_dispatch.py"))
md = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(md)


class _FakeNow:
    """Stand-in for datetime.datetime.now() with a controllable strftime."""

    def __init__(self, stamp):
        self._stamp = stamp

    def strftime(self, fmt):
        return self._stamp


def _patch_now(stamps):
    """Patch datetime.datetime.now to yield the given stamps in order."""
    it = iter(stamps)

    class _FakeDT:
        @staticmethod
        def now():
            return _FakeNow(next(it))

    return mock.patch.object(md.datetime, "datetime", _FakeDT)


def test_worker_name_includes_timestamp():
    name = md.worker_name("Update README", "42")
    assert re.match(r"^mr-pr-update-readme-42-\d{20}$", name), name


def test_worker_name_sanitizes_invalid_chars():
    name = md.worker_name("Task A.B!", "probe-n5h")
    # slug portion is lowercased and invalid chars become dashes
    assert name.startswith("mr-pr-task-a-b-probe-n5h-")
    assert not name.startswith("-")


def test_worker_name_falls_back_to_id_only_when_title_empty():
    name = md.worker_name("", "7")
    assert re.match(r"^mr-pr-7-\d{20}$", name), name


def test_worker_name_capped_and_timestamp_always_preserved():
    # A very long title must not cause the timestamp suffix to be truncated away.
    name = md.worker_name("A" * 300, "123")
    assert len(name) <= 120
    assert re.search(r"-\d{20}$", name), name


def test_worker_name_unique_for_same_mr_pr():
    first_stamp = "2026010100000000000" + "1"
    second_stamp = "2026010100000000000" + "2"
    with _patch_now([first_stamp, second_stamp]):
        first = md.worker_name("Update README", "42")
        second = md.worker_name("Update README", "42")

    assert first != second
    assert first.endswith(first_stamp)
    assert second.endswith(second_stamp)


def test_dispatch_mr_pr_worker_dispatches_every_time_no_dedup():
    captured = []

    def fake_dispatch_local(worker, image, env, port, worker_port,
                            restart_policy, mr_pr_id, net=None, labels=None):
        captured.append(worker)
        return 0, "created", ""

    orig = {
        "is_swarm": md.du.is_swarm_manager,
        "dispatch_local": md.du.dispatch_local,
        "find_port": md.du.find_free_host_port,
        "env": md.du.env,
        "owner": md.du.get_workspace_owner,
        "log": md.du.log,
    }
    md.du.is_swarm_manager = lambda: False
    md.du.dispatch_local = fake_dispatch_local
    md.du.find_free_host_port = lambda base: 8100
    md.du.env = lambda name, default=None: default
    md.du.get_workspace_owner = lambda ws: "abc"
    md.du.log = lambda msg: None
    try:
        info = {
            "mr_pr_id": "42",
            "title": "Update README",
            "branch": "feature/x",
            "repo_url": "https://github.com/o/r.git",
            "provider": "github",
        }
        cfg = md.Config()
        self_info = {"image": "img", "env": [], "restart_policy": ""}

        # Dispatch the same MR/PR twice: both must dispatch a new worker
        # (no "already exists" skip), each with a distinct name.
        with _patch_now(["20260101000000000001", "20260101000000000002"]):
            assert md.dispatch_mr_pr_worker(info, cfg, self_info) is True
            assert md.dispatch_mr_pr_worker(info, cfg, self_info) is True

        assert len(captured) == 2
        assert captured[0] != captured[1]
        assert captured[0].endswith("20260101000000000001")
        assert captured[1].endswith("20260101000000000002")
    finally:
        md.du.is_swarm_manager = orig["is_swarm"]
        md.du.dispatch_local = orig["dispatch_local"]
        md.du.find_free_host_port = orig["find_port"]
        md.du.env = orig["env"]
        md.du.get_workspace_owner = orig["owner"]
        md.du.log = orig["log"]


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