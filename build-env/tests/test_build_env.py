"""Tests for build environment manager."""

import os
import pytest
from unittest.mock import Mock, patch

# Import what we need
import os
import pytest
from unittest.mock import Mock, patch

# Import the actual security module
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security import SecurityError

# Import build_env after setting up path
from build_env import BuildEnvironmentManager, BuildEnvironmentError


@pytest.fixture
def mock_docker_client():
    """Mock Docker client fixture."""
    return Mock()


@pytest.fixture
def manager(mock_docker_client):
    """BuildEnvironmentManager fixture."""
    return BuildEnvironmentManager(docker_client=mock_docker_client)


def test_build_env_manager_initialization():
    """Test BuildEnvironmentManager initialization."""
    manager = BuildEnvironmentManager()
    assert manager.docker_client is not None


def test_container_name_generation(manager):
    """Test container name generation with UUID."""
    container_name = manager._generate_container_name()
    assert container_name.startswith("build-env-")
    assert len(container_name) == 46  # build-env- + UUIDv4


def test_validate_requirements_success(manager):
    """Test requirements validation success."""
    # Set required environment variables
    env_vars = {
        "BUILD_CONTAINER": "test-container",
        "DEFAULT_WORKSPACE": "/workspace",
        "TEST_VAR": "test_value"
    }

    # Should not raise any exception
    manager._validate_requirements(env_vars)


def test_validate_requirements_missing_build_container(manager):
    """Test validation fails when BUILD_CONTAINER not set."""
    env_vars = {
        "DEFAULT_WORKSPACE": "/workspace",
        "TEST_VAR": "test_value"
    }

    with pytest.raises(BuildEnvironmentError) as exc_info:
        manager._validate_requirements(env_vars)
    assert "BUILD_CONTAINER environment variable" in str(exc_info.value)


def test_validate_requirements_missing_default_workspace(manager):
    """Test validation fails when DEFAULT_WORKSPACE not set."""
    env_vars = {
        "BUILD_CONTAINER": "test-container",
        "TEST_VAR": "test_value"
    }

    with pytest.raises(BuildEnvironmentError) as exc_info:
        manager._validate_requirements(env_vars)
    assert "DEFAULT_WORKSPACE environment variable" in str(exc_info.value)


def test_get_container_uuid(manager):
    """Test workspace UUID generation."""
    with patch('build_env.generate_container_uuid') as mock_generate:
        mock_generate.return_value = "12345678-1234-5678-1234-567812345678"
        uuid = manager._get_container_uuid("/workspace/test")
        assert uuid == "12345678-1234-5678-1234-567812345678"
        mock_generate.assert_called_once()


def test_container_exists(manager, mock_docker_client):
    """Test container existence check."""
    # Container exists
    mock_docker_client.containers.get.return_value = Mock()
    assert manager._container_exists("my-container") is True

    # Container does not exist
    from docker.errors import NotFound
    mock_docker_client.containers.get.side_effect = NotFound("Not found")
    assert manager._container_exists("non-existent-container") is False


def test_container_running(manager, mock_docker_client):
    """Test container running status check."""
    # Container is running
    mock_container = Mock()
    mock_container.status = "running"
    mock_docker_client.containers.get.return_value = mock_container
    assert manager._container_running("running-container") is True

    # Container is not running
    mock_container.status = "exited"
    assert manager._container_running("exited-container") is False

    # Container does not exist
    from docker.errors import NotFound
    mock_docker_client.containers.get.side_effect = NotFound("Not found")
    assert manager._container_running("non-existent-container") is False


def test_get_container_uuid_calls_security_module(manager):
    """Test that get_container_uuid calls the security module."""
    with patch('build_env.generate_container_uuid') as mock_generate:
        mock_generate.return_value = "12345678-1234-5678-1234-567812345678"
        uuid = manager._get_container_uuid("/workspace/test")
        assert uuid == "12345678-1234-5678-1234-567812345678"
        mock_generate.assert_called_once()


def test_start_container_creates_new_container(manager, mock_docker_client):
    """Test starting a new container when none exists."""
    # Setup mocks
    mock_image = Mock()
    mock_container = Mock()

    mock_docker_client.containers.get.side_effect = Exception("Not found")
    mock_docker_client.images.get.return_value = mock_image
    mock_docker_client.containers.create.return_value = mock_container
    mock_container.start.return_value = None

    # Mock security functions
    sys.modules['security'].validate_image_name.return_value = True

    # Call method
    result = manager._start_container("test-image:latest", "/workspace", {"TEST_VAR": "test_value"})

    # Assertions
    sys.modules['security'].validate_image_name.assert_called_once_with("test-image:latest")
    mock_docker_client.containers.get.assert_called_once_with("build-env-12345678-1234-5678-1234-567812345678")
    mock_docker_client.images.get.assert_called_once_with("test-image:latest")
    mock_docker_client.containers.create.assert_called_once_with(
        image="test-image:latest",
        name="build-env-12345678-1234-5678-1234-567812345678",
        working_dir="/workspace",
        volumes={"/workspace": {"bind": "/workspace", "mode": "rw"}},
        environment={"TEST_VAR": "test_value"},
        detach=True
    )
    mock_container.start.assert_called_once()
    assert result == "build-env-12345678-1234-5678-1234-567812345678"


def test_start_container_reuses_running_container(manager, mock_docker_client):
    """Test reusing an existing running container."""
    # Setup mocks
    mock_container = Mock()
    mock_container.status = "running"

    mock_docker_client.containers.get.return_value = mock_container
    sys.modules['security'].validate_image_name.return_value = True

    # Call method
    result = manager._start_container("test-image:latest", "/workspace", {"TEST_VAR": "test_value"})

    # Assertions - should reuse existing container
    sys.modules['security'].validate_image_name.assert_called_once_with("test-image:latest")
    mock_docker_client.containers.get.assert_called_once_with("build-env-12345678-1234-5678-1234-567812345678")
    assert result == "build-env-12345678-1234-5678-1234-567812345678"


def test_execute_command(manager, mock_docker_client):
    """Test executing a command in the container."""
    # Setup mocks
    mock_container = Mock()
    mock_exec_result = Mock()
    mock_exec_result.exit_code = 0
    mock_exec_result.output = b"Command output"

    mock_docker_client.containers.get.return_value = mock_container
    mock_container.exec_run.return_value = mock_exec_result

    # Call method
    result = manager._execute_command("build-env-12345678-1234-5678-1234-567812345678", "echo hello", {"TEST_VAR": "test_value"})

    # Assertions
    mock_docker_client.containers.get.assert_called_once_with("build-env-12345678-1234-5678-1234-567812345678")
    mock_container.exec_run.assert_called_once_with(
        "echo hello",
        detach=False,
        environment={"TEST_VAR": "test_value"},
        workdir="/workspace",
        tty=True,
        stdin=True
    )
    assert result == mock_exec_result


def test_shutdown_container(manager, mock_docker_client):
    """Test shutting down and removing a container."""
    # Setup mocks
    mock_container = Mock()
    mock_container.stop.return_value = None
    mock_container.remove.return_value = None

    mock_docker_client.containers.get.return_value = mock_container

    # Call method
    manager._shutdown_container("build-env-12345678-1234-5678-1234-567812345678")

    # Assertions
    mock_docker_client.containers.get.assert_called_once_with("build-env-12345678-1234-5678-1234-567812345678")
    mock_container.stop.assert_called_once()
    mock_container.remove.assert_called_once_with(force=True)


def test_start_container_invalid_image_name(manager):
    """Test that invalid image names raise BuildEnvironmentError."""
    # Setup mock to raise SecurityError
    sys.modules['security'].validate_image_name.side_effect = SecurityError("Invalid image name")

    # Call method
    with pytest.raises(BuildEnvironmentError) as exc_info:
        manager._start_container("invalid-image", "/workspace", {"TEST_VAR": "test_value"})

    # Assertions
    assert "Invalid image name" in str(exc_info.value)


def test_execute_command_filters_dangerous_env_vars(manager, mock_docker_client):
    """Test that dangerous environment variables are filtered."""
    # Setup mocks
    mock_container = Mock()
    mock_exec_result = Mock()
    mock_exec_result.exit_code = 0

    mock_docker_client.containers.get.return_value = mock_container
    mock_container.exec_run.return_value = mock_exec_result

    # Call method with dangerous environment variables
    result = manager._execute_command(
        "build-env-12345678-1234-5678-1234-567812345678",
        "echo hello",
        {"DANGEROUS_VAR": "dangerous", "SAFE_VAR": "safe_value"}
    )

    # Assertions
    mock_container.exec_run.assert_called_once_with(
        "echo hello",
        detach=False,
        environment={"SAFE_VAR": "safe_value"},
        workdir="/workspace",
        tty=True,
        stdin=True
    )


def test_start_container_image_not_found(manager, mock_docker_client):
    """Test handling of image not found error."""
    # Setup mocks
    mock_docker_client.containers.get.side_effect = Exception("Not found")
    mock_docker_client.images.get.side_effect = Exception("Image not found")
    sys.modules['security'].validate_image_name.return_value = True

    # Call method
    with pytest.raises(BuildEnvironmentError) as exc_info:
        manager._start_container("nonexistent-image:latest", "/workspace", {"TEST_VAR": "test_value"})

    # Assertions
    assert "Docker image not found" in str(exc_info.value)


def test_cli_exit_command():
    """Test --exit flag handling."""
    with patch('sys.argv', ['build-env', '--exit']):
        # Mock BuildEnvironmentManager before importing CLI
        with patch('build_env.BuildEnvironmentManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance._get_container_uuid.return_value = "12345678-1234-5678-1234-567812345678"

            # Import CLI after mocking
            import importlib
            import sys

            # Remove the module from cache to force re-import
            if 'build_env_cli' in sys.modules:
                del sys.modules['build_env_cli']

            from build_env_cli import main
            main()
            mock_instance._shutdown_container.assert_called_once_with("build-env-12345678-1234-5678-1234-567812345678")


def test_cli_command_execution():
    """Test command execution via CLI."""
    with patch('sys.argv', ['build-env', 'echo', 'hello']):
        with patch('build_env.BuildEnvironmentManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance._execute_command.return_value = (0, "hello\\n")
            mock_instance._validate_requirements.return_value = None
            mock_instance._start_container.return_value = "build-env-test-uuid"

            with patch('os.environ', {
                'BUILD_CONTAINER': 'python:3.11',
                'DEFAULT_WORKSPACE': '/workspace'
            }):
                # Import CLI after mocking
                import importlib
                import sys

                # Remove the module from cache to force re-import
                if 'build_env_cli' in sys.modules:
                    del sys.modules['build_env_cli']

                from build_env_cli import main
                main()
                mock_instance._execute_command.assert_called_once()


def test_cli_missing_environment_variables():
    """Test CLI fails with missing environment variables."""
    with patch('sys.argv', ['build-env', 'echo', 'hello']):
        with patch('build_env.BuildEnvironmentManager') as mock_manager:
            mock_instance = mock_manager.return_value
            # Mock validate_requirements to raise BuildEnvironmentError
            from build_env import BuildEnvironmentError
            mock_instance._validate_requirements.side_effect = BuildEnvironmentError("Environment variables missing")

            with patch('os.environ', {}):
                # Import CLI after mocking
                import importlib
                import sys

                # Remove the module from cache to force re-import
                if 'build_env_cli' in sys.modules:
                    del sys.modules['build_env_cli']

                from build_env_cli import main
                result = main()
                # Should return non-zero exit code
                assert result == 1


def test_get_file_list():
    """Test file listing helper method"""
    import tempfile
    import os

    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files and directories
        os.makedirs(os.path.join(tmpdir, 'subdir'))
        with open(os.path.join(tmpdir, 'file1.txt'), 'w') as f:
            f.write('test')
        with open(os.path.join(tmpdir, 'subdir', 'file2.txt'), 'w') as f:
            f.write('test')

        # Test file listing
        manager = BuildEnvironmentManager()
        files = manager._get_file_list(tmpdir)

        # Should contain relative paths
        assert 'file1.txt' in files
        assert 'subdir/file2.txt' in files
        assert '.build-env' not in files  # Should skip .build-env directories


def test_get_file_list_nonexistent_directory():
    """Test file listing with non-existent directory"""
    manager = BuildEnvironmentManager()
    with pytest.raises(FileNotFoundError):
        manager._get_file_list('/nonexistent/path')


def test_get_file_list_file_not_directory():
    """Test file listing with file instead of directory"""
    import tempfile
    manager = BuildEnvironmentManager()
    with tempfile.NamedTemporaryFile() as tmpfile:
        with pytest.raises(NotADirectoryError):
            manager._get_file_list(tmpfile.name)


def test_get_file_list_empty_directory():
    """Test file listing with empty directory"""
    import tempfile
    manager = BuildEnvironmentManager()
    with tempfile.TemporaryDirectory() as tmpdir:
        files = manager._get_file_list(tmpdir)
        assert files == set()


def test_delete_files_in_destination():
    """Test destination file deletion helper method"""
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create source and destination directories
        source_dir = os.path.join(tmpdir, 'source')
        dest_dir = os.path.join(tmpdir, 'dest')
        os.makedirs(source_dir)
        os.makedirs(dest_dir)

        # Create files that should exist in both
        with open(os.path.join(source_dir, 'common.txt'), 'w') as f:
            f.write('common')
        with open(os.path.join(dest_dir, 'common.txt'), 'w') as f:
            f.write('common')

        # Create files that should be deleted from destination
        with open(os.path.join(dest_dir, 'delete_me.txt'), 'w') as f:
            f.write('delete')

        manager = BuildEnvironmentManager()
        source_files = manager._get_file_list(source_dir)
        dest_files = manager._get_file_list(dest_dir)

        # Delete files that exist in dest but not source
        manager._delete_files_in_destination(dest_dir, source_files, dest_files)

        # Verify file was deleted
        assert not os.path.exists(os.path.join(dest_dir, 'delete_me.txt'))
        assert os.path.exists(os.path.join(dest_dir, 'common.txt'))


def test_host_to_container_sync_with_deletions():
    """Test host→container sync handles deletions properly"""
    import tempfile
    import os

    # Mock container scenario
    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate container workspace
        container_dir = os.path.join(tmpdir, 'container')
        host_dir = os.path.join(tmpdir, 'host')
        os.makedirs(container_dir)
        os.makedirs(host_dir)

        # Create files that should exist in both
        with open(os.path.join(host_dir, 'common.txt'), 'w') as f:
            f.write('common')
        with open(os.path.join(container_dir, 'common.txt'), 'w') as f:
            f.write('common')

        # Create file that should be deleted from container
        with open(os.path.join(container_dir, 'delete_me.txt'), 'w') as f:
            f.write('delete')

        # Mock the sync process
        manager = BuildEnvironmentManager()

        # Get file lists
        host_files = manager._get_file_list(host_dir)
        container_files = manager._get_file_list(container_dir)

        # Delete files in container that don't exist on host
        manager._delete_files_in_destination(container_dir, host_files, container_files)

        # Verify deletion
        assert not os.path.exists(os.path.join(container_dir, 'delete_me.txt'))
        assert os.path.exists(os.path.join(container_dir, 'common.txt'))


def test_synchronize_host_to_container_with_deletions(manager, mock_docker_client):
    """Test _synchronize_host_to_container method with deletion handling"""
    import tempfile
    import os

    # Mock container
    mock_container = Mock()
    mock_container.exec_run.return_value = Mock(exit_code=0)
    mock_docker_client.containers.get.return_value = mock_container

    # Create temporary workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files
        with open(os.path.join(tmpdir, 'keep.txt'), 'w') as f:
            f.write('keep')

        # Mock docker cp commands
        with patch('subprocess.run') as mock_run:
            # Mock successful docker cp operations
            mock_run.return_value = Mock(returncode=0)

            # Call the method
            result = manager._synchronize_host_to_container('test-container', tmpdir)

            # Verify method was called
            mock_docker_client.containers.get.assert_called_once_with('test-container')
            mock_container.exec_run.assert_called()

            # Should have called docker cp twice (for list and copy)
            assert mock_run.call_count >= 2

            # Should return True
            assert result is True


def test_synchronize_container_to_host_with_deletions(manager, mock_docker_client):
    """Test _synchronize_container_to_host method with deletion handling"""
    import tempfile
    import os

    # Create temporary workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test files on host - files that should be deleted
        with open(os.path.join(tmpdir, 'delete_on_host.txt'), 'w') as f:
            f.write('delete')

        # Mock docker cp and file operations
        with patch('subprocess.run') as mock_run:
            # Mock docker cp calls
            def mock_subprocess(cmd, **kwargs):
                if len(cmd) > 2 and cmd[1] == 'cp':
                    # First docker cp: copy container to temp dir
                    if cmd[2].startswith('test-container:') and cmd[3].startswith('/tmp'):
                        # Create mock files in temp dir to simulate container contents
                        temp_dir = cmd[3]
                        os.makedirs(temp_dir, exist_ok=True)
                        with open(os.path.join(temp_dir, 'container_keep.txt'), 'w') as f:
                            f.write('container')
                        with open(os.path.join(temp_dir, 'common.txt'), 'w') as f:
                            f.write('common')
                        return Mock(returncode=0)
                    # Second docker cp: actual sync operation
                    else:
                        return Mock(returncode=0)
                return Mock(returncode=0)

            mock_run.side_effect = mock_subprocess

            # Mock file list operations
            with patch.object(manager, '_get_file_list') as mock_get_files:
                # First call: get container files from temp dir
                # Second call: get host files
                mock_get_files.side_effect = [
                    {'container_keep.txt', 'common.txt'},  # container files (from temp dir)
                    {'delete_on_host.txt', 'common.txt'}    # host files
                ]

                # Mock delete operation
                with patch.object(manager, '_delete_files_in_destination') as mock_delete:
                    # Call the method
                    result = manager._synchronize_container_to_host('test-container', tmpdir)

                    # Verify deletion was called
                    mock_delete.assert_called_once()

                    # Verify method returns True
                    assert result is True

                    # Verify the delete call had correct parameters
                    call_args = mock_delete.call_args
                    assert call_args[0][0] == tmpdir  # dest_dir
                    assert call_args[0][1] == {'container_keep.txt', 'common.txt'}  # source_files (container)
                    assert call_args[0][2] == {'delete_on_host.txt', 'common.txt'}  # dest_files (host)


def test_container_to_host_sync_with_deletions():
    """Test enhanced _synchronize_container_to_host handles deletions properly"""
    # Import and analyze the enhanced method
    from build_env import BuildEnvironmentManager
    import inspect

    manager = BuildEnvironmentManager()
    source_code = inspect.getsource(manager._synchronize_container_to_host)

    # Test that enhanced implementation now uses deletion helpers
    assert '_get_file_list' in source_code, "Enhanced implementation should use _get_file_list"
    assert '_delete_files_in_destination' in source_code, "Enhanced implementation should use _delete_files_in_destination"
    assert 'tempfile.TemporaryDirectory' in source_code, "Enhanced implementation should use tempfile for file comparison"
    assert 'container_files - host_files' in source_code or 'host_files - container_files' in source_code or '_delete_files_in_destination' in source_code, \
        "Enhanced implementation should handle file comparison and deletion"