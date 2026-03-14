"""Tests for build environment manager."""

import os
import pytest
from unittest.mock import Mock

# Mock docker before imports
import sys
sys.modules['docker'] = Mock()
sys.modules['docker'].DockerClient = Mock
sys.modules['docker'].from_env = Mock
sys.modules['docker.errors'] = Mock()
sys.modules['docker.errors'].NotFound = Exception

# Mock security module with proper mocking
sys.modules['build_env.security'] = Mock()
sys.modules['build_env.security'].generate_container_uuid = Mock()

# Set default behavior for mocks
sys.modules['build_env.security'].generate_container_uuid.return_value = "12345678-1234-5678-1234-567812345678"

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
    os.environ["BUILD_CONTAINER"] = "test-container"
    os.environ["DEFAULT_WORKSPACE"] = "/workspace"

    # Should not raise any exception
    env_vars = {"TEST_VAR": "test_value"}
    manager._validate_requirements(env_vars)

    # Clean up
    del os.environ["BUILD_CONTAINER"]
    del os.environ["DEFAULT_WORKSPACE"]


def test_validate_requirements_missing_build_container(manager):
    """Test validation fails when BUILD_CONTAINER not set."""
    # Ensure BUILD_CONTAINER is not set
    if "BUILD_CONTAINER" in os.environ:
        del os.environ["BUILD_CONTAINER"]

    # Set DEFAULT_WORKSPACE
    os.environ["DEFAULT_WORKSPACE"] = "/workspace"

    env_vars = {"TEST_VAR": "test_value"}

    with pytest.raises(BuildEnvironmentError) as exc_info:
        manager._validate_requirements(env_vars)
    assert "BUILD_CONTAINER environment variable is required" in str(exc_info.value)

    # Clean up
    del os.environ["DEFAULT_WORKSPACE"]


def test_validate_requirements_missing_default_workspace(manager):
    """Test validation fails when DEFAULT_WORKSPACE not set."""
    # Set BUILD_CONTAINER
    os.environ["BUILD_CONTAINER"] = "test-container"

    # Ensure DEFAULT_WORKSPACE is not set
    if "DEFAULT_WORKSPACE" in os.environ:
        del os.environ["DEFAULT_WORKSPACE"]

    env_vars = {"TEST_VAR": "test_value"}

    with pytest.raises(BuildEnvironmentError) as exc_info:
        manager._validate_requirements(env_vars)
    assert "DEFAULT_WORKSPACE environment variable is required" in str(exc_info.value)

    # Clean up
    del os.environ["BUILD_CONTAINER"]


def test_get_container_uuid(manager):
    """Test workspace UUID generation."""
    uuid = manager._get_container_uuid("/workspace/test")
    assert uuid == "12345678-1234-5678-1234-567812345678"


def test_container_exists(manager, mock_docker_client):
    """Test container existence check."""
    # Container exists
    mock_docker_client.containers.get.return_value = Mock()
    assert manager._container_exists("my-container") is True

    # Container does not exist
    mock_docker_client.containers.get.side_effect = Exception("Not found")
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
    mock_docker_client.containers.get.side_effect = Exception("Not found")
    assert manager._container_running("non-existent-container") is False


def test_get_container_uuid_calls_security_module(manager):
    """Test that get_container_uuid calls the security module."""
    # Reset the mock call count
    sys.modules['build_env.security'].generate_container_uuid.reset_mock()
    uuid = manager._get_container_uuid("/workspace/test")
    assert uuid == "12345678-1234-5678-1234-567812345678"
    sys.modules['build_env.security'].generate_container_uuid.assert_called_once()


def test_start_container_creates_new_container(manager, mock_docker_client):
    """Test starting a new container when none exists."""
    # Setup mocks
    mock_image = Mock()
    mock_container = Mock()

    mock_docker_client.containers.get.side_effect = Exception("Not found")
    mock_docker_client.images.get.return_value = mock_image
    mock_docker_client.containers.create.return_value = mock_container
    mock_container.start.return_value = None

    # Call method
    result = manager._start_container("test-image", "/workspace", {"TEST_VAR": "test_value"})

    # Assertions
    mock_docker_client.containers.get.assert_called_once_with("build-env-12345678-1234-5678-1234-567812345678")
    mock_docker_client.images.get.assert_called_once_with("test-image")
    mock_docker_client.containers.create.assert_called_once_with(
        image="test-image",
        name="build-env-12345678-1234-5678-1234-567812345678",
        working_dir="/workspace",
        volumes={"/workspace": {"bind": "/workspace", "mode": "rw"}},
        environment={"TEST_VAR": "test_value"},
        detach=True
    )
    mock_container.start.assert_called_once()
    assert result == mock_container


def test_start_container_reuses_running_container(manager, mock_docker_client):
    """Test reusing an existing running container."""
    # Setup mocks
    mock_container = Mock()
    mock_container.status = "running"

    mock_docker_client.containers.get.return_value = mock_container

    # Call method
    result = manager._start_container("test-image", "/workspace", {"TEST_VAR": "test_value"})

    # Assertions - should reuse existing container
    mock_docker_client.containers.get.assert_called_once_with("build-env-12345678-1234-5678-1234-567812345678")
    assert result == mock_container


def test_execute_command(manager, mock_docker_client):
    """Test executing a command in the container."""
    # Setup mocks
    mock_container = Mock()
    mock_exec_result = Mock()
    mock_exec_result.exit_code = 0
    mock_exec_result.output = b"Command output"

    mock_container.exec_run.return_value = mock_exec_result

    # Call method
    result = manager._execute_command(mock_container, "echo hello")

    # Assertions
    mock_container.exec_run.assert_called_once_with("echo hello", detach=False)
    assert result.exit_code == 0
    assert result.output == b"Command output"


def test_shutdown_container(manager, mock_docker_client):
    """Test shutting down and removing a container."""
    # Setup mocks
    mock_container = Mock()
    mock_container.stop.return_value = None
    mock_container.remove.return_value = None

    # Call method
    manager._shutdown_container(mock_container)

    # Assertions
    mock_container.stop.assert_called_once()
    mock_container.remove.assert_called_once_with(force=True)