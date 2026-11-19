"""Unit tests for dispatch_utils, focused on container self-identification.

The regression covered here: when the dispatcher container is deployed as a
Docker Swarm service (dispatch_swarm sets --hostname to the service name),
no container answers to the bare hostname — swarm task containers are named
<service>.<slot>.<task-id> — and cgroups v2 with a private cgroupns exposes
no container ID either ("0::/"). self_container_id() must still resolve the
real container ID (via /proc/self/mountinfo or the swarm task label) so the
deployment succeeds.

Run with: python3 -m pytest tests/test_dispatch_utils.py
"""

import errno
import io
import os
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))

# Make dispatch_utils importable (the dispatchers do `import dispatch_utils`).
sys.path.insert(0, os.path.join(HERE, "..", "beads-dispatch"))

import dispatch_utils as du  # noqa: E402

CID = "0123456789abcdef" * 4  # realistic 64-char hex container ID
OTHER_CID = "fedcba9876543210" * 4

CGROUP_V1 = "12:devices:/docker/%s\n" % CID
CGROUP_NAMESPACED = "0::/\n"  # cgroups v2 with private cgroupns: no container ID

MOUNTINFO = (
    "605 595 259:2 /var/lib/docker/containers/%(cid)s/hostname /etc/hostname"
    " rw,relatime - ext4 /dev/nvme0n1p2 rw,errors=remount-ro\n"
    "606 595 259:2 /var/lib/docker/containers/%(cid)s/hosts /etc/hosts"
    " rw,relatime - ext4 /dev/nvme0n1p2 rw,errors=remount-ro\n"
    "607 595 259:2 /var/lib/docker/containers/%(cid)s/resolv.conf /etc/resolv.conf"
    " rw,relatime - ext4 /dev/nvme0n1p2 rw,errors=remount-ro\n"
    # Noise: a bind mount whose mount point is not a per-container config file
    "640 605 259:2 /docker/swarm /var/run/docker.sock rw - ext4 /dev/nvme0n1p2 rw\n"
) % {"cid": CID}

MOUNTINFO_OTHER = MOUNTINFO.replace(CID, OTHER_CID)


def _fake_open(files):
    """Patch builtins.open to serve the given paths and ENOENT everything else."""
    def fake(path, *args, **kwargs):
        if path in files:
            return io.StringIO(files[path])
        raise OSError(errno.ENOENT, "no such file", path)
    return mock.patch("builtins.open", side_effect=fake)


def test_self_container_id_from_cgroup_v1():
    files = {"/proc/self/cgroup": CGROUP_V1, "/proc/self/mountinfo": MOUNTINFO_OTHER}
    with _fake_open(files):
        assert du.self_container_id() == CID


def test_self_container_id_from_mountinfo_when_cgroup_namespaced():
    # The swarm failure: cgroups expose no ID ("0::/"), but /etc/hostname and
    # /etc/hosts are bind-mounted from /var/lib/docker/containers/<cid>/...
    files = {"/proc/self/cgroup": CGROUP_NAMESPACED, "/proc/self/mountinfo": MOUNTINFO}
    with _fake_open(files):
        assert du.self_container_id() == CID


def test_self_container_id_hostname_inspect_fallback():
    files = {
        "/proc/self/cgroup": CGROUP_NAMESPACED,
        "/proc/self/mountinfo": "",
        "/etc/hostname": "mycontainer\n",
    }
    with _fake_open(files), mock.patch.object(
            du, "run", return_value=(0, CID, "")) as run_mock:
        assert du.self_container_id() == CID
    cmd = run_mock.call_args[0][0]
    # --type container keeps a swarm *service* sharing the hostname's name from
    # being inspected by mistake (its .Id is a service ID, not a container ID)
    assert cmd[:4] == ["docker", "inspect", "--type", "container"], cmd
    assert "mycontainer" in cmd


def test_self_container_id_swarm_task_label_lookup():
    # No ID from cgroup/mountinfo and no container answers to the bare hostname
    # ("no such object") — resolve via the swarm service-name label instead.
    files = {
        "/proc/self/cgroup": CGROUP_NAMESPACED,
        "/proc/self/mountinfo": "",
        "/etc/hostname": "dispatch-test\n",
    }

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "inspect"]:
            return (1, "", "Error: No such object: dispatch-test")
        if cmd[:2] == ["docker", "ps"]:
            return (0, "%s\n%s" % (CID, OTHER_CID), "")
        raise AssertionError("unexpected command: %r" % (cmd,))

    with _fake_open(files), mock.patch.object(du, "run", side_effect=fake_run) as run_mock:
        assert du.self_container_id() == CID

    ps_cmd = run_mock.call_args_list[1][0][0]
    assert ps_cmd[:2] == ["docker", "ps"], ps_cmd
    assert "label=com.docker.swarm.service.name=dispatch-test" in ps_cmd, ps_cmd


def test_self_container_id_returns_none_when_unresolvable():
    files = {
        "/proc/self/cgroup": CGROUP_NAMESPACED,
        "/proc/self/mountinfo": "",
        "/etc/hostname": "dispatch-test\n",
    }

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["docker", "inspect"]:
            return (1, "", "Error: No such object: dispatch-test")
        return (1, "", "")  # docker ps also fails (no socket, etc.)

    # Must degrade gracefully (deployment falls back to the worker image
    # override), not raise
    with _fake_open(files), mock.patch.object(du, "run", side_effect=fake_run):
        assert du.self_container_id() is None


def test_self_container_id_keeps_original_log_for_unexpected_errors():
    files = {
        "/proc/self/cgroup": CGROUP_NAMESPACED,
        "/proc/self/mountinfo": "",
        "/etc/hostname": "mycontainer\n",
    }

    def fake_run(cmd, **kwargs):
        return (126, "", "permission denied while trying to connect")

    with _fake_open(files), mock.patch.object(du, "run", side_effect=fake_run), \
            mock.patch.object(du, "log") as log_mock:
        assert du.self_container_id() is None
    logged = " ".join(str(c.args[0]) for c in log_mock.call_args_list)
    # Only the "no such object" case gets the swarm-specific message
    assert "swarm" not in logged, logged
    assert "docker inspect mycontainer failed (rc=126)" in logged, logged


def test_inspect_self_returns_none_when_inspect_fails():
    with mock.patch.object(du, "run", return_value=(1, "", "Error: No such object")):
        assert du.inspect_self(CID) is None


def test_dispatch_swarm_sets_hostname_to_service_name():
    # Documents why /etc/hostname equals the service name inside swarm task
    # containers: dispatch_swarm passes --hostname <service-name>.
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443, "workspace-l0b")
    cmd = run_mock.call_args[0][0]
    assert cmd[cmd.index("--hostname") + 1] == "dispatch-test", cmd


def test_dispatch_swarm_passes_registry_auth():
    # Workers inherit the parent's image via inspect_self() -> Config.Image.
    # That image may be published to a private registry, so a swarm node
    # that has not logged in cannot pull it and the worker fails to start
    # with an image-pull error. --with-registry-auth forwards the caller's
    # Docker credential config to the pulling node. It is a no-op when no
    # credentials exist, and `docker run` (local dispatch) does not accept
    # the flag - it already authenticates on pull.
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443, "workspace-c4u")
    cmd = run_mock.call_args[0][0]
    assert cmd[:3] == ["docker", "service", "create"], cmd
    assert "--with-registry-auth" in cmd, cmd


def test_dispatch_local_does_not_pass_registry_auth():
    # `docker run` has no --with-registry-auth flag and fails with "unknown
    # flag" if it is passed. Local pulls use the local credential config
    # automatically, so the flag must never reach the local path.
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_local("dispatch-test", "img:1", [], 8000, 8443, "workspace-c4u")
    cmd = run_mock.call_args[0][0]
    assert cmd[:3] == ["docker", "run", "-d"], cmd
    assert "--with-registry-auth" not in cmd, cmd


def test_dispatch_swarm_stamps_container_labels():
    # `docker service create --label` stamps the SERVICE object only; the
    # task containers never see it, so the worker killer's container-label
    # gate (docker inspect .Config.Labels) always read label='' on swarm
    # workers and refused to kill. --container-label puts the same labels
    # on the containers; --label stays for the reaper's service lookup.
    labels = {"beads.issue": "workspace-kts", "dispatch.worker": "true"}
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443,
                          "workspace-kts", labels=labels)
    cmd = run_mock.call_args[0][0]
    # Every --label has a matching --container-label, in the same order.
    service_labels = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--label"]
    container_labels = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--container-label"]
    assert service_labels == container_labels == ["beads.issue=workspace-kts", "dispatch.worker=true"], cmd


# --- Swarm worker reservations and node filtering (2026-11-18 dockerblade) ---

def _clear_placement_env(monkeypatch):
    for name in ("WORKER_RESERVE_MEMORY", "WORKER_RESERVE_CPU",
                 "WORKER_NODE_ALLOWLIST", "WORKER_NODE_DENYLIST"):
        monkeypatch.delenv(name, raising=False)


def _constraints(cmd):
    return [cmd[i + 1] for i, a in enumerate(cmd) if a == "--constraint"]


def test_dispatch_swarm_reserves_memory_and_cpu_by_default(monkeypatch):
    # A worker runs ~0.5-1GB of RAM; with no reservation Swarm counted it
    # as costing nothing and kept piling workers onto 8GB dockerblade.
    _clear_placement_env(monkeypatch)
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443, "workspace-c4u")
    cmd = run_mock.call_args[0][0]
    assert cmd[cmd.index("--reserve-memory") + 1] == "1g", cmd
    assert cmd[cmd.index("--reserve-cpu") + 1] == "0.5", cmd


def test_dispatch_swarm_reserves_are_configurable(monkeypatch):
    _clear_placement_env(monkeypatch)
    monkeypatch.setenv("WORKER_RESERVE_MEMORY", "2g")
    monkeypatch.setenv("WORKER_RESERVE_CPU", "1")
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443, "workspace-c4u")
    cmd = run_mock.call_args[0][0]
    assert cmd[cmd.index("--reserve-memory") + 1] == "2g", cmd
    assert cmd[cmd.index("--reserve-cpu") + 1] == "1", cmd


def test_dispatch_swarm_no_node_constraints_by_default(monkeypatch):
    _clear_placement_env(monkeypatch)
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443, "workspace-c4u")
    assert _constraints(run_mock.call_args[0][0]) == []


def test_dispatch_swarm_denylist_excludes_nodes(monkeypatch):
    _clear_placement_env(monkeypatch)
    monkeypatch.setenv("WORKER_NODE_DENYLIST", "dockerblade, leviathan")
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443, "workspace-c4u")
    cmd = run_mock.call_args[0][0]
    assert _constraints(cmd) == ["node.hostname!=dockerblade",
                                 "node.hostname!=leviathan"], cmd


def test_dispatch_swarm_single_node_allowlist(monkeypatch):
    _clear_placement_env(monkeypatch)
    monkeypatch.setenv("WORKER_NODE_ALLOWLIST", "dockerblade2")
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443, "workspace-c4u")
    cmd = run_mock.call_args[0][0]
    assert _constraints(cmd) == ["node.hostname==dockerblade2"], cmd
    # A single-node allowlist needs no `docker node ls` call.
    assert run_mock.call_count == 1


def test_dispatch_swarm_multi_node_allowlist_excludes_other_nodes(monkeypatch):
    # Constraints are ANDed, so several `node.hostname==` constraints could
    # never be satisfied; a multi-node allowlist is enforced by excluding
    # every node outside it.
    _clear_placement_env(monkeypatch)
    monkeypatch.setenv("WORKER_NODE_ALLOWLIST", "dockerblade2, leviathan")
    captured = {}

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["docker", "node", "ls"]:
            return 0, "dockerblade\ndockerblade2\nleviathan\npower-tower-envy-1\n", ""
        captured["cmd"] = cmd
        return 0, "", ""

    with mock.patch.object(du, "run", side_effect=fake_run):
        rc, _, _ = du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443,
                                     "workspace-c4u")
    assert rc == 0
    assert _constraints(captured["cmd"]) == ["node.hostname!=dockerblade",
                                             "node.hostname!=power-tower-envy-1"], captured["cmd"]


def test_dispatch_swarm_denylist_subtracts_from_allowlist(monkeypatch):
    _clear_placement_env(monkeypatch)
    monkeypatch.setenv("WORKER_NODE_ALLOWLIST", "dockerblade2, leviathan")
    monkeypatch.setenv("WORKER_NODE_DENYLIST", "leviathan")
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443, "workspace-c4u")
    assert _constraints(run_mock.call_args[0][0]) == ["node.hostname==dockerblade2"]


def test_dispatch_swarm_fails_closed_when_allowlist_cannot_be_enforced(monkeypatch):
    # If the node list cannot be read, a multi-node allowlist cannot be
    # enforced — dispatch nothing rather than dispatch unconstrained.
    _clear_placement_env(monkeypatch)
    monkeypatch.setenv("WORKER_NODE_ALLOWLIST", "dockerblade2, leviathan")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ["docker", "node", "ls"]:
            return 1, "", "daemon unavailable"
        return 0, "", ""

    with mock.patch.object(du, "run", side_effect=fake_run):
        rc, _, err = du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443,
                                       "workspace-c4u")
    assert rc == 1
    assert "WORKER_NODE_ALLOWLIST" in err
    assert all(c[:3] != ["docker", "service", "create"] for c in calls)


def test_dispatch_swarm_fails_closed_when_allowlist_emptied_by_denylist(monkeypatch):
    _clear_placement_env(monkeypatch)
    monkeypatch.setenv("WORKER_NODE_ALLOWLIST", "dockerblade")
    monkeypatch.setenv("WORKER_NODE_DENYLIST", "dockerblade")
    with mock.patch.object(du, "run", return_value=(0, "", "")) as run_mock:
        rc, _, err = du.dispatch_swarm("dispatch-test", "img:1", [], 8000, 8443,
                                       "workspace-c4u")
    assert rc == 1
    assert "no eligible nodes" in err
    run_mock.assert_not_called()
