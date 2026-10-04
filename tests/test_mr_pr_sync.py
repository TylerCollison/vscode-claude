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
"""

import os
import subprocess
import tempfile
import unittest
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
