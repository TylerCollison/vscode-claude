"""Unit tests for the MR/PR sync daemon's provider detection and redaction.

These tests run start-mr-pr-sync.sh with the daemon start stubbed out, so
only the provider-detection + redaction preamble executes (no state dirs,
PID files, or sync loop). They cover the failure modes observed in beads
issue workspace-5dr:

- self-hosted GitLab hosts (e.g. gitlab.home.com) fail substring
  auto-detection (only github.com / gitlab.com are known), so the daemon
  must honor an MR_PR_PROVIDER override (github/gitlab) for arbitrary hosts,
- credentials embedded in GIT_REPO_URL (https://user:token@host/...) must
  never reach log or error output,
- invalid override values must fail with a remediation message listing the
  valid values, and unmatched hosts must mention the override variable,
- owner/repo extraction works for arbitrary hosts (strip scheme and
  userinfo, drop the host, take the path minus trailing .git).

Also covers the matching redaction in git-repo-setup.sh, which echoes
GIT_REPO_URL in its log/error output (tokens would land in container boot
logs when the URL carries embedded credentials).

And guards the glab mr list invocation flags against the installed glab
(beads issue workspace-4zz): the Dockerfile pins glab, and its mr list
flags drift between releases (--state and --json vanished in v1.110.0),
so the script's flags are checked against the real binary, and the
-F json output shape is verified end-to-end against a mock GitLab API.
"""

import json
import os
import shlex
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYNC_SH = HERE.parent / "start-mr-pr-sync.sh"
GIT_REPO_SETUP_SH = HERE.parent / "git-repo-setup.sh"

# Log line emitted once the detection preamble succeeds; tests stub the
# script to stop right after it (before state dirs / daemon start).
ENABLED_LOG_LINE = (
    'log "MR/PR sync enabled for $PROVIDER '
    '(user: $RESPONDER_USER, repo: $REPO_OWNER_REPO)"'
)

TOKEN = "glpat-secret-token-1234"
GH_TOKEN_VALUE = "ghp-secret-token-5678"


class MrPrSyncProviderTest(unittest.TestCase):
    """Provider detection + credential redaction in start-mr-pr-sync.sh."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        sandbox = Path(self.temp_dir.name)

        # Stub gh/glab/docker onto PATH so the prerequisite check passes
        # hermetically (python3 is expected to exist in the test env).
        self.bin_dir = sandbox / "bin"
        self.bin_dir.mkdir()
        for name in ("gh", "glab", "docker"):
            stub = self.bin_dir / name
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)

    def _make_script(self, tail="\nexit 0"):
        """Copy the sync script, stopping it right after the enabled log.

        The stub logs the enabled line (asserting detection succeeded), then
        exits before state dirs, PID files, and the daemon loop start. `tail`
        replaces the plain exit for tests that need to observe exports.
        """
        script = SYNC_SH.read_text()
        self.assertEqual(script.count(ENABLED_LOG_LINE), 1)
        script = script.replace(ENABLED_LOG_LINE, ENABLED_LOG_LINE + tail)
        script_copy = Path(self.temp_dir.name) / "sync-test.sh"
        script_copy.write_text(script)
        script_copy.chmod(0o755)
        return script_copy

    def _run_sync(self, url, provider=None, script_copy=None):
        env = dict(os.environ)
        env["MR_PR_DISPATCH"] = "true"
        env["MR_PR_USER"] = "test-user"
        env["GIT_REPO_URL"] = url
        env["PATH"] = "%s%s%s" % (self.bin_dir, os.pathsep, env.get("PATH", ""))
        if provider is not None:
            env["MR_PR_PROVIDER"] = provider
        else:
            env.pop("MR_PR_PROVIDER", None)
        return subprocess.run(
            ["bash", str(script_copy or self._make_script())],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_override_gitlab_with_embedded_credentials_starts(self):
        """MR_PR_PROVIDER=gitlab starts on a self-hosted host with creds."""
        url = "https://tylerc:%s@gitlab.home.com/tylerc/dispatchtest.git" % TOKEN
        result = self._run_sync(url, provider="gitlab")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MR/PR sync enabled for gitlab", result.stdout)
        self.assertIn("repo: tylerc/dispatchtest", result.stdout)
        self.assertNotIn(TOKEN, result.stdout)
        self.assertNotIn(TOKEN, result.stderr)

    def test_override_github_with_embedded_credentials_starts(self):
        """MR_PR_PROVIDER=github forces GitHub on a non-github.com host."""
        url = "https://tylerc:%s@git.corp.example/o/r.git" % GH_TOKEN_VALUE
        result = self._run_sync(url, provider="github")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MR/PR sync enabled for github", result.stdout)
        self.assertIn("repo: o/r", result.stdout)
        self.assertNotIn(GH_TOKEN_VALUE, result.stdout)
        self.assertNotIn(GH_TOKEN_VALUE, result.stderr)

    def test_no_override_autodetects_github_without_credentials(self):
        result = self._run_sync("https://github.com/o/r.git")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MR/PR sync enabled for github", result.stdout)
        self.assertIn("repo: o/r", result.stdout)

    def test_no_override_autodetects_github_with_credentials(self):
        url = "https://user:%s@github.com/o/r.git" % GH_TOKEN_VALUE
        result = self._run_sync(url)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MR/PR sync enabled for github", result.stdout)
        self.assertNotIn(GH_TOKEN_VALUE, result.stdout)
        self.assertNotIn(GH_TOKEN_VALUE, result.stderr)

    def test_no_override_autodetects_gitlab_without_credentials(self):
        result = self._run_sync("https://gitlab.com/o/r.git")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MR/PR sync enabled for gitlab", result.stdout)
        self.assertIn("repo: o/r", result.stdout)

    def test_no_override_autodetects_gitlab_with_credentials(self):
        url = "https://user:%s@gitlab.com/o/r.git" % TOKEN
        result = self._run_sync(url)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("MR/PR sync enabled for gitlab", result.stdout)
        self.assertNotIn(TOKEN, result.stdout)
        self.assertNotIn(TOKEN, result.stderr)

    def test_invalid_override_fails_with_remediation(self):
        """An override other than github/gitlab fails, listing valid values."""
        result = self._run_sync(
            "https://gitlab.home.com/o/r.git", provider="sourcehut")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Invalid MR_PR_PROVIDER 'sourcehut'", result.stdout)
        self.assertIn("github", result.stdout)
        self.assertIn("gitlab", result.stdout)
        self.assertNotIn("MR/PR sync enabled", result.stdout)

    def test_self_hosted_gitlab_without_credentials_requires_override(self):
        """No override + unmatched host fails with a message naming the fix."""
        result = self._run_sync("https://gitlab.home.com/o/r.git")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Could not determine provider", result.stdout)
        self.assertIn("MR_PR_PROVIDER", result.stdout)
        self.assertNotIn("MR/PR sync enabled", result.stdout)

    def test_self_hosted_gitlab_with_credentials_redacts_token(self):
        """The undetermined-provider error must not leak embedded creds."""
        url = "https://tylerc:%s@gitlab.home.com/tylerc/dispatchtest.git" % TOKEN
        result = self._run_sync(url)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Could not determine provider", result.stdout)
        # The host is shown, but never the token or userinfo
        self.assertIn("https://gitlab.home.com/tylerc/dispatchtest.git",
                      result.stdout)
        self.assertNotIn(TOKEN, result.stdout)
        self.assertNotIn("tylerc:", result.stdout)
        self.assertNotIn(TOKEN, result.stderr)

    def test_owner_repo_extraction_for_arbitrary_hosts(self):
        """Subgroup paths survive extraction on arbitrary hosts."""
        url = "https://tylerc:%s@gitlab.home.com/group/subgroup/repo.git" % TOKEN
        result = self._run_sync(url, provider="gitlab")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("repo: group/subgroup/repo", result.stdout)
        self.assertNotIn(TOKEN, result.stdout)

    def test_gitlab_host_exported_for_self_hosted_instance(self):
        """glab must be pointed at the self-hosted instance (GITLAB_HOST)."""
        url = "https://tylerc:%s@gitlab.home.com/tylerc/dispatchtest.git" % TOKEN
        script_copy = self._make_script(
            tail="\nprintenv GITLAB_HOST || true\nexit 0")
        result = self._run_sync(url, provider="gitlab",
                                script_copy=script_copy)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("gitlab.home.com", result.stdout.splitlines()[-1])

    def test_gitlab_host_not_set_for_gitlab_com(self):
        """gitlab.com repos must not get a GITLAB_HOST override."""
        script_copy = self._make_script(
            tail="\nprintenv GITLAB_HOST || true\nexit 0")
        result = self._run_sync("https://gitlab.com/o/r.git",
                                script_copy=script_copy)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("gitlab.com", result.stdout.splitlines()[-1])

    def test_gh_host_exported_for_self_hosted_github(self):
        """gh must be pointed at the self-hosted instance (GH_HOST)."""
        url = "https://tylerc:%s@git.corp.example/o/r.git" % GH_TOKEN_VALUE
        script_copy = self._make_script(
            tail="\nprintenv GH_HOST || true\nexit 0")
        result = self._run_sync(url, provider="github",
                                script_copy=script_copy)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("git.corp.example", result.stdout.splitlines()[-1])

    def test_gh_host_not_set_for_github_com(self):
        """github.com repos must not get a GH_HOST override."""
        script_copy = self._make_script(
            tail="\nprintenv GH_HOST || true\nexit 0")
        result = self._run_sync("https://github.com/o/r.git",
                                script_copy=script_copy)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("github.com", result.stdout.splitlines()[-1])


def _glab_mlist_invocation(test):
    """Extract the glab_cmd block from start-mr-pr-sync.sh.

    Returns (env, args): the env assignments the sync daemon hands to glab
    and the `glab mr list ...` args, with the shell substitutions applied,
    so the real glab binary can be run against the same invocation. Unknown
    shell substitutions are left literal (glab ignores unrelated vars).
    """
    script = SYNC_SH.read_text()
    lines = script.splitlines()
    start = next((i for i, ln in enumerate(lines) if "local glab_cmd=(" in ln),
                 None)
    test.assertIsNotNone(start, "glab_cmd block not found in start-mr-pr-sync.sh")
    block = []
    for ln in lines[start + 1:]:
        if ln.strip() == ")":
            break
        block.append(ln.strip().rstrip("\\").strip())
    test.assertEqual(len(block), 3,
                     "unexpected glab_cmd block shape: %r" % block)
    test.assertTrue(block[0].startswith("setpriv"), block)
    test.assertTrue(block[1].startswith("env "), block)
    test.assertTrue(block[2].startswith("glab mr list"), block)

    env_line = block[1][len("env "):]
    env_line = env_line.replace('"$SYNC_HOME"', '"/tmp/sync-home"')
    env_line = env_line.replace('"${GITLAB_TOKEN:-}"', '"test-token"')
    env_line = env_line.replace('"${GLAB_SEND_TELEMETRY:-false}"', '"false"')
    env = {}
    for assignment in shlex.split(env_line):
        key, _, value = assignment.partition("=")
        env[key] = value

    args_line = block[2]
    args_line = args_line.replace('"$RESPONDER_USER"', '"testuser"')
    args_line = args_line.replace('"$REPO_OWNER_REPO"', '"o/r"')
    return env, shlex.split(args_line[len("glab "):])  # ["mr", "list", ...]


@unittest.skipUnless(shutil.which("glab"), "glab not installed")
class GlabFlagsRegressionTest(unittest.TestCase):
    """glab mr list flags in start-mr-pr-sync.sh vs the installed glab.

    Regression for beads issue workspace-4zz: the Dockerfile pins glab, but
    mr list flags drift between releases (--state and --json are unknown in
    v1.110.0, where JSON output is -F json). An unknown flag fails before
    any API call, so running the script's exact invocation against a dead
    endpoint proves the installed glab parses it.
    """

    def test_flags_accepted_by_installed_glab(self):
        invocation_env, args = _glab_mlist_invocation(self)

        env = dict(os.environ)
        env.update(invocation_env)
        # Dead local port: with valid flags glab gets past flag parsing and
        # fails fast at the API layer; with an unknown flag it errors with
        # "Unknown flag" without touching the network.
        env["GITLAB_HOST"] = "127.0.0.1:1"
        result = subprocess.run(
            ["glab"] + args,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

        combined = result.stdout + result.stderr
        self.assertNotIn(
            "Unknown flag", combined,
            "installed glab rejected flags from start-mr-pr-sync.sh "
            "(%s): %s" % (" ".join(args), combined))

    def test_glab_invocation_disables_telemetry(self):
        """Regression: glab 1.110's telemetry goroutine panics on a failed
        send (exit 2) — a successful fetch would print the MR list and then
        crash, and the sync's retry loop discards it. The sync must hand
        glab a telemetry opt-out (GLAB_SEND_TELEMETRY, default false)."""
        invocation_env, _ = _glab_mlist_invocation(self)

        self.assertIn("GLAB_SEND_TELEMETRY", invocation_env,
                      "glab_cmd env must set GLAB_SEND_TELEMETRY")
        self.assertEqual(invocation_env["GLAB_SEND_TELEMETRY"], "false",
                         "GLAB_SEND_TELEMETRY must default to false")


# Minimal GitLab API v4 responses for the output-shape test. The sync
# script's Python parser reads iid/title/source_branch/web_url from the
# merge_requests array; the assignee lookup happens first (glab resolves
# the --assignee username to an ID before listing).
MOCK_USER = {
    "id": 42, "username": "testuser", "name": "Test User", "state": "active",
}
MOCK_MR = {
    "id": 9001, "iid": 33, "project_id": 7, "title": "Add feature X",
    "state": "opened", "target_branch": "main", "source_branch": "feature-x",
    "assignee": dict(MOCK_USER),
    "web_url": "https://gitlab.test/o/r/-/merge_requests/33",
}


class _MockGitLabHandler(BaseHTTPRequestHandler):
    """Serves the endpoints glab hits for `mr list --assignee ... -F json`."""

    def _send(self, payload, code=200):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/v4/users":
            self._send([dict(MOCK_USER)])
        elif path.startswith("/api/v4/projects/") and path.endswith("/merge_requests"):
            self._send([dict(MOCK_MR)])
        elif path.startswith("/api/v4/projects/"):
            # Some glab versions resolve the project before listing
            self._send({"id": 7, "path": "r", "path_with_namespace": "o/r"})
        elif path == "/api/v4/version":
            self._send({"version": "17.0.0", "revision": "mock"})
        else:
            self._send({"message": "404 not found"}, 404)

    def log_message(self, *args):
        pass


@unittest.skipUnless(shutil.which("glab"), "glab not installed")
class GlabJsonOutputShapeTest(unittest.TestCase):
    """End-to-end: glab -F json output matches the script's parser (workspace-4zz).

    Runs the script's exact glab invocation against a TLS mock GitLab API
    (glab forces HTTPS; SSL_CERT_FILE trusts the mock's self-signed cert)
    and asserts the JSON output is an array whose objects carry the
    iid/title/source_branch/web_url fields the parser reads.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        # Mint a self-signed cert for the mock and trust it via SSL_CERT_FILE
        cert = Path(self.temp_dir.name) / "mock_cert.pem"
        key = Path(self.temp_dir.name) / "mock_key.pem"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048",
             "-keyout", str(key), "-out", str(cert), "-days", "2",
             "-nodes", "-subj", "/CN=127.0.0.1",
             "-addext", "subjectAltName=IP:127.0.0.1"],
            capture_output=True, text=True, timeout=60, check=True)

        self.httpd = HTTPServer(("127.0.0.1", 0), _MockGitLabHandler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(cert), str(key))
        self.httpd.socket = ctx.wrap_socket(self.httpd.socket, server_side=True)
        self.port = self.httpd.server_address[1]
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def _run_glab(self):
        invocation_env, args = _glab_mlist_invocation(self)
        env = dict(os.environ)
        env.update(invocation_env)
        env["GITLAB_HOST"] = "127.0.0.1:%d" % self.port
        env["SSL_CERT_FILE"] = str(Path(self.temp_dir.name) / "mock_cert.pem")
        return subprocess.run(
            ["glab"] + args,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_json_output_is_parser_compatible(self):
        result = self._run_glab()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Unknown flag", result.stdout + result.stderr)

        # The script's parser slices from the first '[' then json.loads
        start = result.stdout.find("[")
        self.assertNotEqual(start, -1,
                            "no JSON array in glab output: %r" % result.stdout[:200])
        data = json.loads(result.stdout[start:])
        self.assertIsInstance(data, list)
        self.assertTrue(data, "glab returned an empty MR list from the mock")
        for item in data:
            for field in ("iid", "title", "source_branch", "web_url"):
                self.assertIn(field, item,
                              "glab output object missing %r: %r" % (field, item))


class GitRepoSetupRedactionTest(unittest.TestCase):
    """Credential redaction in git-repo-setup.sh log/error output."""

    def _run_setup(self, url):
        env = dict(os.environ)
        env["GIT_REPO_URL"] = url
        env["DEFAULT_WORKSPACE"] = os.path.join(self.temp_dir.name, "ws")
        return subprocess.run(
            ["bash", str(GIT_REPO_SETUP_SH)],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def test_bad_scheme_error_redacts_token(self):
        """The URL-format error must not echo embedded credentials."""
        url = "ftp://tylerc:%s@gitlab.home.com/repo.git" % TOKEN
        result = self._run_setup(url)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Repository URL must start with http:// or https://",
                      result.stderr)
        # Host is shown, token and userinfo are not
        self.assertIn("ftp://gitlab.home.com/repo.git", result.stderr)
        self.assertNotIn(TOKEN, result.stderr)
        self.assertNotIn("tylerc:", result.stderr)

    def test_clone_failure_error_redacts_token(self):
        """The clone-failure error must not echo embedded credentials."""
        url = "https://tylerc:%s@127.0.0.1:1/repo.git" % TOKEN
        result = self._run_setup(url)

        self.assertEqual(result.returncode, 1, result.stderr)
        setup_lines = [line for line in result.stderr.splitlines()
                       if "Failed to clone git repository" in line]
        self.assertTrue(setup_lines, result.stderr)
        self.assertIn("https://127.0.0.1:1/repo.git", setup_lines[0])
        self.assertNotIn(TOKEN, setup_lines[0])
        self.assertNotIn("tylerc:", setup_lines[0])


if __name__ == "__main__":
    unittest.main()
