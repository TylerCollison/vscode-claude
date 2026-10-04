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
