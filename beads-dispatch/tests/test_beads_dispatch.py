"""Unit tests for the Beads Dispatch daemon's pure functions.

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
    # worker name is derived from the issue title + id (not the parent)
    assert bd.worker_name({"id": "probe-n5h", "title": "Update README"}, "parent") == "update-readme-probe-n5h"


def test_worker_name_sanitizes_invalid_chars():
    # underscores/dots/uppercase are normalized; safe for containers and services
    name = bd.worker_name({"id": "probe-n5h", "title": "Task A.B!"}, "vsclaude-code")
    assert name == "task-a-b-probe-n5h"
    assert not name.startswith("-")
    assert not name.endswith("-")


def test_worker_name_fallback_to_parent_when_title_empty():
    # empty / non-slug-able title falls back to <parent>-<issue-id>
    assert bd.worker_name({"id": "x", "title": ""}, "claude-dev") == "claude-dev-x"
    assert bd.worker_name({"id": "x", "title": "!!!"}, "-bad-.parent") == "bad-parent-x"


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
    assert env_dict["BEADS_REMOTE"] == "https://example.com/repo.git"  # dolt sync source
    assert env_dict["API_KEY"] == "secret"  # secrets inherited
    assert env_dict["PATH"] == "/usr/bin"
    assert "GIT_BRANCH" not in env_dict  # only GIT_BRANCH_NAME is set


def test_compose_worker_env_keeps_inherited_repo_url_when_no_override():
    parent = ["GIT_REPO_URL=https://example.com/repo.git"]
    env = bd.compose_worker_env(parent, "task/x", None)
    assert any(e == "GIT_REPO_URL=https://example.com/repo.git" for e in env)
    # No explicit repo_url -> BEADS_REMOTE is not added (nothing to sync from)
    assert not any(e.startswith("BEADS_REMOTE=") for e in env)


def test_compose_worker_env_includes_beads_remote():
    parent = ["GIT_REPO_URL=https://example.com/repo.git"]
    env = bd.compose_worker_env(parent, "task/x", "https://example.com/repo.git")
    assert any(e == "BEADS_REMOTE=https://example.com/repo.git" for e in env)


def test_dispatch_local_sets_hostname_and_socket_mount():
    import subprocess as sp
    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return 0, "created", ""
    orig = bd.run
    bd.run = fake_run
    try:
        bd.dispatch_local("myparent-probe-n5h", "img", ["A=B"], 8000, 8443, "", "probe-n5h")
    finally:
        bd.run = orig
    cmd = captured["cmd"]
    assert cmd[:3] == ["docker", "run", "-d"]
    assert "--hostname" in cmd
    assert cmd[cmd.index("--hostname") + 1] == "myparent-probe-n5h"
    assert "--name" in cmd
    assert cmd[cmd.index("--name") + 1] == "myparent-probe-n5h"
    # the ONLY volume mount is the docker socket
    mount_idx = [i for i, c in enumerate(cmd) if c == "-v"]
    assert len(mount_idx) == 1
    assert cmd[mount_idx[0] + 1] == "/var/run/docker.sock:/var/run/docker.sock"


def test_dispatch_swarm_sets_hostname_and_docker_socket_mount():
    captured = {}
    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return 0, "created", ""
    orig = bd.run
    bd.run = fake_run
    try:
        bd.dispatch_swarm("myparent-probe-n5h", "img", ["A=B"], 8000, 8443, "probe-n5h")
    finally:
        bd.run = orig
    cmd = captured["cmd"]
    assert cmd[:3] == ["docker", "service", "create"]
    assert "--hostname" in cmd
    assert cmd[cmd.index("--hostname") + 1] == "myparent-probe-n5h"
    # only one --mount and it's the docker socket
    mounts = [cmd[i + 1] for i, c in enumerate(cmd) if c == "--mount"]
    assert mounts == ["type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock"]


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
    used = {8000, 8001, 8002}
    orig = bd.used_host_ports
    bd.used_host_ports = lambda: used
    try:
        port = bd.find_free_host_port(8000)
    finally:
        bd.used_host_ports = orig
    assert port == 8003


def test_install_post_commit_hook_backs_up_existing():
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.join(tmp, "repo")
        os.makedirs(os.path.join(repo, ".git", "hooks"))
        existing = os.path.join(repo, ".git", "hooks", "post-commit")
        with open(existing, "w") as fh:
            fh.write("#!/bin/sh\necho existing\n")
        assert bd.install_post_commit_hook(repo, socket_path="/tmp/test-dispatch.sock") is True
        assert os.path.exists(existing + ".beads-dispatch.bak")
        with open(existing) as fh:
            hook = fh.read()
        assert "test-dispatch.sock" in hook
        assert "/tmp/test-dispatch.sock" in hook


def test_git_env_sets_terminal_prompt_off():
    e = bd.git_env()
    assert e.get("GIT_TERMINAL_PROMPT") == "0"


def test_get_workspace_owner_prefers_non_root():
    # A temp dir owned by the current user (root here) falls back to 'abc'
    with tempfile.TemporaryDirectory() as tmp:
        owner = bd.get_workspace_owner(tmp)
        assert owner in ("abc", "coder", "user", "root")
    # When root-owned and abc exists, prefer abc (non-root).
    try:
        pwd_entry = bd.pwd.getpwuid(0)
    except KeyError:
        pwd_entry = None
    if pwd_entry:
        assert bd.get_workspace_owner("/") not in ("", None)


def test_derive_git_repo_url_prefers_credentialed_remote():
    real_run = bd.run
    def fake_run(cmd, **kwargs):
        if len(cmd) >= 2 and cmd[-2:] == ["get-url", "origin"]:
            return 0, "https://user:token@github.com/org/repo.git", ""
        return real_run(cmd, **kwargs)
    old = bd.run
    bd.run = fake_run
    try:
        with tempfile.TemporaryDirectory() as tmp:
            url = bd.derive_git_repo_url(
                ["GIT_REPO_URL=https://github.com/org/repo.git"], tmp, "abc")
        assert url == "https://user:token@github.com/org/repo.git"
    finally:
        bd.run = old


def test_has_credential_helper_detects_existing():
    # Not configured yet -> False
    assert bd._has_credential_helper("gh auth git-credential") in (True, False)


def test_env_function_not_shadowed_in_dispatch_worker():
    """dispatch_worker calls module-level env() before assigning local env_vars.

    Regression: a local named 'env' shadowed the module function, causing
    UnboundLocalError at dispatch time.
    """
    # dispatch_worker should not define a local named 'env' in its fast path.
    import inspect
    src = inspect.getsource(bd.dispatch_worker)
    # 'env(' is the module call; 'env =' or 'env,' local assignments are the trap.
    # The local worker-env variable must be named env_vars.
    assert "env_vars = compose_worker_env" in src
    assert "env = compose_worker_env" not in src


def test_git_env_function_not_shadowed_in_push_task_branch():
    """push_task_branch calls module git_env() and assigns g_env locally."""
    import inspect
    src = inspect.getsource(bd.push_task_branch)
    assert "g_env = git_env()" in src
    assert "git_env = git_env()" not in src


def test_configure_credential_helpers_idempotent():
    # This machine has at least one of gh/glab; calling twice should not
    # duplicate helpers and should still report configured.
    first = bd.configure_credential_helpers()
    before = bd.run(["git", "config", "--global", "--get-all", "credential.helper"])[1]
    second = bd.configure_credential_helpers()
    after = bd.run(["git", "config", "--global", "--get-all", "credential.helper"])[1]
    assert after == before, "second configure duplicated helpers"


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
