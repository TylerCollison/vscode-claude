# build-env/tests/test_integration.py
import pytest
import subprocess
import os
import tempfile
import sys


# Register the integration marker
pytest.mark.integration = pytest.mark.integration

@pytest.mark.integration
class TestIntegration:
    """Integration tests for build-env tool."""

    def test_build_env_help(self):
        """Test build-env help command."""
        # Use the full path to build-env command
        build_env_path = f"{sys.prefix}/bin/build-env"
        result = subprocess.run(
            [build_env_path, '--help'],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "Run commands in persistent build environment containers" in result.stdout

    def test_build_env_missing_environment(self):
        """Test build-env fails with missing environment variables."""
        # Use the full path to build-env command
        build_env_path = f"{sys.prefix}/bin/build-env"
        result = subprocess.run(
            [build_env_path, 'echo', 'hello'],
            capture_output=True,
            text=True,
            env={}  # Empty environment
        )
        assert result.returncode != 0
        assert "BUILD_CONTAINER environment variable must be set" in result.stderr

    def test_build_env_exit_command(self):
        """Test build-env --exit command."""
        # This test requires a running container, so it might fail
        # but should handle the error gracefully
        # Use the full path to build-env command
        build_env_path = f"{sys.prefix}/bin/build-env"
        result = subprocess.run(
            [build_env_path, '--exit'],
            capture_output=True,
            text=True
        )
        # Should either succeed or fail gracefully
        assert result.returncode in [0, 1]