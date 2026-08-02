"""Unit tests for the Beads Dispatch watcher's pure functions.

Run with: python3 -m pytest beads-dispatch/tests/  (or run directly: python3 beads-dispatch/tests/test_beads_dispatch.py)
"""

import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location("beads_dispatch", os.path.join(HERE, "..", "beads_dispatch.py"))
bd = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bd)


def test_worker_name_basic():
    assert bd.worker_name("claude-dev", "probe-n5h") == "claude-dev-probe-n5h"


def test_worker_name_sanitizes_invalid_chars():
    # underscores/dots/uppercase are normalized; safe for containers and services
    name = bd.worker_name("vsclaude-code_vsclaude-code.1.ABC", "probe-n5h")
    assert name == "vsclaude-code-vsclaude-code-1-abc-probe-n5h"
    assert not name.startswith("-")
    assert not name.endswith("-")


def test_worker_name_fallback():
    assert bd.worker_name("-bad-.name", "x") == "bad-name-x"


def test_slugify():
    assert bd.slugify("Task A") == "task-a"
    assert bd.slugify("HELLO, World!!") == "hello-world"
    assert bd.slugify("") == ""
    assert bd.slugify("foo---bar") == "foo-bar"


def test_derive_branch_name_with_title():
    assert bd.derive_branch_name({"id": "probe-n5h", "title": "Task A"}, "task") == "task/probe-n5h-task-a"


def test_derive_branch_name_falls_back_to_id_only():
    assert bd.derive_branch_name({"id": "probe-n5h", "title": "!@#"}, "task") == "task/probe-n5h"
    assert bd.derive_branch_name({"id": "probe-n5h", "title": ""}, "task") == "task/probe-n5h"


def test_compose_worker_env_overrides_branch_and_disables_recursion():
    parent = [
        "PATH=/usr/bin",
        "GIT_BRANCH_NAME=old-branch",
        "GIT_REPO_URL=https://example.com/repo.git",
        "API_KEY=secret",
        "BEADS_DISPATCH=true",
    ]
    env = bd.compose_worker_env(parent, "task/probe-n5h-task-a", "https://example.com/repo.git")
    env_dict = dict(e.split("=", 1) for e in env)
    assert env_dict["GIT_BRANCH_NAME"] == "task/probe-n5h-task-a"
    assert env_dict["GIT_REPO_URL"] == "https://example.com/repo.git"
    assert env_dict["BEADS_DISPATCH"] == "false"
    assert env_dict["API_KEY"] == "secret"  # secrets inherited
    assert env_dict["PATH"] == "/usr/bin"
    assert "GIT_BRANCH" not in env_dict  # only GIT_BRANCH_NAME is set


def test_compose_worker_env_keeps_inherited_repo_url_when_no_override():
    parent = ["GIT_REPO_URL=https://example.com/repo.git"]
    env = bd.compose_worker_env(parent, "task/x", None)
    assert any(e == "GIT_REPO_URL=https://example.com/repo.git" for e in env)


def test_derive_git_repo_url_from_env():
    env = ["OTHER=1", "GIT_REPO_URL=https://env.git"]
    assert bd.derive_git_repo_url(env, "/tmp") == "https://env.git"


def test_derive_git_repo_url_none_when_missing():
    assert bd.derive_git_repo_url([], "/nonexistent-dir-xyz") is None


def test_load_save_state_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = bd.Config.__new__(bd.Config)
        cfg.state_dir = tmp
        assert bd.load_state(cfg) == set()
        bd.save_state(cfg, {"a", "b"})
        assert bd.load_state(cfg) == {"a", "b"}


def test_find_free_host_port_skips_used():
    # used_host_ports reads the real docker daemon; with no docker it returns empty.
    # Assert the scanner returns a port >= base and skips the injected "used" set.
    used = {8000, 8001, 8002}
    base = 8000
    port = None
    # monkey-patch the underlying collector to a deterministic set
    orig = bd.used_host_ports
    bd.used_host_ports = lambda: used
    try:
        port = bd.find_free_host_port(base)
    finally:
        bd.used_host_ports = orig
    assert port == 8003


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
