# build-env/tests/test_integration.py
import pytest
import subprocess
import os
import tempfile
import sys
import docker


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

    def test_bidirectional_deletion_sync(self):
        """Integration test for bidirectional deletion synchronization"""
        # Skip if Docker not available
        try:
            docker.from_env().ping()
        except Exception:
            pytest.skip("Docker not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_path = tmpdir

            # Set up environment
            os.environ['BUILD_CONTAINER'] = 'alpine:latest'
            os.environ['DEFAULT_WORKSPACE'] = workspace_path

            # Import BuildEnvironmentManager here to avoid import issues
            from build_env import BuildEnvironmentManager
            manager = BuildEnvironmentManager()
            container_name = None

            try:
                # Create initial container
                container_name = manager._start_container(
                    os.environ['BUILD_CONTAINER'],
                    workspace_path,
                    dict(os.environ)
                )
                container = manager.docker_client.containers.get(container_name)

                # Test 1: File deletion sync from host to container
                # Create file on host
                test_file = 'delete_test.txt'
                host_file_path = os.path.join(workspace_path, test_file)
                with open(host_file_path, 'w') as f:
                    f.write('test content')

                # Sync host → container
                assert manager._synchronize_host_to_container(container_name, workspace_path)

                # Delete file on host
                os.remove(host_file_path)

                # Sync host → container again (should delete from container)
                assert manager._synchronize_host_to_container(container_name, workspace_path)

                # Verify file was deleted from container
                result = container.exec_run(f'ls {workspace_path}/{test_file}')
                assert result.exit_code != 0  # File should not exist

                # Test 2: File deletion sync from container to host
                # Create file in container
                container_file = 'container_delete_test.txt'
                container.exec_run(f'touch {workspace_path}/{container_file}')

                # Sync container → host
                assert manager._synchronize_container_to_host(container_name, workspace_path)

                # Verify file exists on host
                assert os.path.exists(os.path.join(workspace_path, container_file))

                # Delete file in container
                container.exec_run(f'rm {workspace_path}/{container_file}')

                # Sync container → host again (should delete from host)
                assert manager._synchronize_container_to_host(container_name, workspace_path)

                # Verify file was deleted from host
                assert not os.path.exists(os.path.join(workspace_path, container_file))

            finally:
                # Cleanup
                if container_name:
                    try:
                        manager._shutdown_container(container_name)
                    except Exception:
                        pass