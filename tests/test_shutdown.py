"""Integration tests for the shutdown script's machine revocation path.

These tests run shutdown.sh against a local mock Happier server with a
sandboxed config directory (config paths redirected onto a copy of the
script via sed, container kill stubbed). They cover the failure modes
observed in beads issue workspace-1fe:

- trailing-slash server-URL normalization: the revoke endpoint is not
  route-normalized and 404s on //v1/... paths, so a trailing slash in
  HAPPIER_SERVER_URL silently prevented machine revocation,
- the E2BIG fix: the machine-list body must not be passed to python as an
  environment variable — the kernel caps a single env/arg string at ~128KB
  ("Argument list too long"), which silently broke the lookup,
- only the settings.json machine ID is ever revoked: the server machine list
  carries no hostname field, and the old "most recently created machine"
  fallback could revoke another running container's machine,
- settings.json cleanup after a successful revoke or a 404.
"""

import http.server
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

SHUTDOWN_SH = Path(__file__).resolve().parent.parent / "shutdown.sh"

ACCESS_TOKEN = "test-access-token"
SETTINGS_MACHINE_ID = "11111111-2222-4333-8444-555555555555"
OTHER_MACHINE_ID = "aaaaaaaa-bbbb-4cccc-8dddd-eeeeeeeeeeee"
UNKNOWN_MACHINE_ID = "00000000-0000-4000-8000-000000000000"


def machine_entry(machine_id, active=True):
    """Build a machine-list entry shaped like the real server's response."""
    return {
        "id": machine_id,
        "active": active,
        "activeAt": 1790000000000,
        "createdAt": 1790000000000,
        "revokedAt": None,
        "metadata": "x" * 32,
    }


class _MockHappierHandler(http.server.BaseHTTPRequestHandler):
    """Mimics the real Happier server: 200 machine list, idempotent revoke,
    and 404s for double-slash paths (the revoke route is not normalized)."""

    def do_GET(self):
        if self.path.rstrip("/") == "/v1/machines" and "//" not in self.path:
            body = json.dumps(self.server.machine_list).encode()
            self._record("GET", self.path)
            self._send(200, body)
        else:
            self._record("GET", self.path)
            self._send(404, b'{"error":"Not found"}')

    def do_POST(self):
        self._record("POST", self.path)
        clean = self.path.lstrip("/")
        if "//" in self.path:
            # The real server's revoke route does not match double slashes
            self._send(404, b'{"error":"Not found"}')
        elif clean.startswith("v1/machines/") and clean.endswith("/revoke"):
            machine_id = clean[len("v1/machines/"):-len("/revoke")]
            if machine_id in {m["id"] for m in self.server.machine_list}:
                # Idempotent: 200 even for already-revoked machines
                entry = machine_entry(machine_id, active=False)
                self._send(200, json.dumps({"machine": entry}).encode())
            else:
                self._send(404, b'{"error":"Not found"}')
        else:
            self._send(404, b'{"error":"Not found"}')

    def _record(self, method, path):
        self.server.requests.append((method, path))

    def _send(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Keep test output clean


class ShutdownRevocationTest(unittest.TestCase):
    """Integration tests for shutdown.sh machine revocation."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        sandbox = Path(self.temp_dir.name)

        # Server ID derived from the base URL (FNV-1a 32-bit, "env_" prefix) —
        # same scheme as the script's get_server_id
        self.server_url = f"http://127.0.0.1:{self._port}/"
        self.server_id = "env_" + format(self._fnv1a(self.server_url.rstrip("/")), "x")

        # Sandboxed config: settings.json + access key for this server
        happier = sandbox / "config" / ".happier"
        key_dir = happier / "servers" / self.server_id
        key_dir.mkdir(parents=True)
        (key_dir / "access.key").write_text(json.dumps({"token": ACCESS_TOKEN}))
        self.settings_file = happier / "settings.json"
        self._write_settings(SETTINGS_MACHINE_ID)

        # Copy the script with config paths redirected to the sandbox and the
        # container kill stubbed out (PID 1 here is not the s6 init process)
        script = SHUTDOWN_SH.read_text()
        script = script.replace("/config/.happier", str(happier))
        script = script.replace("kill -TERM 1", 'echo "STUBBED: kill -TERM 1"')
        script = script.replace("kill -KILL 1", 'echo "STUBBED: kill -KILL 1"')
        script = script.replace("if kill -0 1 2>/dev/null; then", "if false; then")
        script = script.replace("sleep 2", "sleep 0.1")
        self.script_copy = sandbox / "shutdown-test.sh"
        self.script_copy.write_text(script)
        self.script_copy.chmod(0o755)

    @property
    def _port(self):
        if not hasattr(self, "_mock_server"):
            self._start_mock_server()
        return self._mock_server.server_address[1]

    def _start_mock_server(self):
        self._mock_server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MockHappierHandler)
        self._mock_server.requests = []
        self._mock_server.machine_list = [machine_entry(SETTINGS_MACHINE_ID)]
        thread = threading.Thread(target=self._mock_server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self._mock_server.shutdown)
        self.addCleanup(self._mock_server.server_close)

    @staticmethod
    def _fnv1a(value):
        h = 2166136261
        for ch in value:
            h ^= ord(ch)
            h = (h * 16777619) & 0xFFFFFFFF
        return h

    def _write_settings(self, machine_id):
        settings = {"machineIdByServerId": {self.server_id: machine_id}} if machine_id else {}
        self.settings_file.write_text(json.dumps(settings, indent=2))

    def _run_shutdown(self):
        env = dict(os.environ)
        env["HAPPIER_MODE"] = "agent"
        env["HAPPIER_SERVER_URL"] = self.server_url  # intentionally has a trailing slash
        return subprocess.run(
            ["bash", str(self.script_copy)],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _revoke_calls(self):
        return [path for method, path in self._mock_server.requests
                if method == "POST" and "revoke" in path]

    def test_revoke_success_with_trailing_slash_url(self):
        """A trailing slash in HAPPIER_SERVER_URL must not break the revoke.

        Regression for the workspace-1fe root cause: the revoke endpoint 404s
        on //v1/... paths, so the URL must be normalized before use.
        """
        result = self._run_shutdown()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Successfully revoked machine", result.stdout)
        revoke_paths = self._revoke_calls()
        self.assertEqual(revoke_paths, [f"/v1/machines/{SETTINGS_MACHINE_ID}/revoke"])
        self.assertNotIn("//", "".join(revoke_paths))
        # settings.json cleaned up after the successful revoke
        self._assert_settings_cleaned()

    def test_stale_machine_id_returns_404_and_cleans_up(self):
        """A settings machine ID absent from the server 404s and is cleaned."""
        self._mock_server.machine_list = [machine_entry(OTHER_MACHINE_ID)]

        result = self._run_shutdown()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not found on server", result.stdout)
        self.assertEqual(self._revoke_calls(), [f"/v1/machines/{SETTINGS_MACHINE_ID}/revoke"])
        self._assert_settings_cleaned()

    def test_never_revoques_other_machines(self):
        """Only the settings machine ID may be revoked — never another machine.

        The old "most recently created active machine" fallback could revoke
        another running container's machine; it must stay gone.
        """
        self._mock_server.machine_list = [
            machine_entry(OTHER_MACHINE_ID, active=True),
            machine_entry(UNKNOWN_MACHINE_ID, active=True),
        ]

        result = self._run_shutdown()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self._revoke_calls(), [f"/v1/machines/{SETTINGS_MACHINE_ID}/revoke"])
        self.assertNotIn(OTHER_MACHINE_ID, result.stdout)
        self.assertNotIn(UNKNOWN_MACHINE_ID, result.stdout)

    def test_large_machine_list_is_parsed(self):
        """A machine list larger than the ~128KB env-var limit must still parse.

        Regression for the E2BIG failure: the body must not travel through an
        environment variable ("Argument list too long").
        """
        big_list = []
        for i in range(160):
            entry = machine_entry(f"{i:08x}-0000-4000-8000-000000000000")
            entry["metadata"] = "x" * 1024  # ~1KB per entry, like the real server
            big_list.append(entry)
        big_list.append(machine_entry(SETTINGS_MACHINE_ID))
        self.assertGreater(len(json.dumps(big_list)), 128 * 1024)
        self._mock_server.machine_list = big_list

        result = self._run_shutdown()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Successfully revoked machine", result.stdout)
        self.assertIn(SETTINGS_MACHINE_ID, result.stdout)
        self._assert_settings_cleaned()

    def test_no_machine_id_skips_revocation(self):
        """With no machine ID in settings.json, nothing is revoked."""
        self._write_settings(None)
        self._mock_server.machine_list = [machine_entry(OTHER_MACHINE_ID)]

        result = self._run_shutdown()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skipping machine revocation", result.stdout)
        self.assertEqual(self._revoke_calls(), [])

    def _assert_settings_cleaned(self):
        settings = json.loads(self.settings_file.read_text())
        self.assertNotIn(self.server_id, settings.get("machineIdByServerId", {}))


if __name__ == "__main__":
    unittest.main()
