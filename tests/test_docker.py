"""Comprehensive tests for Docker client functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock

# Mock docker import at module level to avoid import errors
import sys
from unittest.mock import MagicMock

# Create a mock docker module
docker_mock = MagicMock()
docker_mock.errors = MagicMock()

# Create exception classes that can be used in tests
class DockerExceptionMock(Exception):
    pass

class APIErrorMock(Exception):
    pass

class NotFoundMock(Exception):
    pass

docker_mock.errors.DockerException = DockerExceptionMock
docker_mock.errors.APIError = APIErrorMock
docker_mock.errors.NotFound = NotFoundMock
sys.modules['docker'] = docker_mock
sys.modules['docker.errors'] = docker_mock.errors

# Import error classes first since they don't depend on docker
from vsclaude.vsclaude.docker import (
    DockerSecurityError,
    DockerConnectionError,
    DockerContainerError
)


def test_docker_client_initialization():
    """Test Docker client can be initialized"""
    from vsclaude.vsclaude.docker import DockerClient
    client = DockerClient()
    assert client.client is not None


class TestDockerSecurityError:
    """Test security error handling."""

    def test_security_error_creation(self):
        """Test DockerSecurityError can be created with message."""
        error = DockerSecurityError("Test security error")
        assert str(error) == "Test security error"


class TestDockerConnectionError:
    """Test connection error handling."""

    def test_connection_error_creation(self):
        """Test DockerConnectionError can be created with message."""
        error = DockerConnectionError("Test connection error")
        assert str(error) == "Test connection error"


class TestDockerContainerError:
    """Test container error handling."""

    def test_container_error_creation(self):
        """Test DockerContainerError can be created with message."""
        error = DockerContainerError("Test container error")
        assert str(error) == "Test container error"


class TestMockDockerClient:
    """Test mock Docker client functionality."""

    def test_mock_client_implements_interface(self):
        """Test MockDockerClient implements DockerClientInterface."""
        from vsclaude.vsclaude.docker import MockDockerClient
        from vsclaude.vsclaude.docker import DockerClientInterface
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        assert isinstance(client, DockerClientInterface)

    def test_mock_client_remove_container_success(self):
        """Test mock client can remove a container."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        assert "test-container-1" in client.mock_containers
        result = client.remove_container("test-container-1")
        assert result is True
        assert "test-container-1" not in client.mock_containers

    def test_mock_client_remove_container_not_found(self):
        """Test mock client returns False for non-existent container."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        result = client.remove_container("non-existent-container")
        assert result is False

    def test_mock_client_is_container_running_true(self):
        """Test mock client returns True for running container."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        assert client.is_container_running("test-container-1") is True

    def test_mock_client_is_container_running_false(self):
        """Test mock client returns False for stopped container."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        assert client.is_container_running("test-container-2") is False

    def test_mock_client_is_container_running_not_found(self):
        """Test mock client returns False for non-existent container."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        assert client.is_container_running("non-existent-container") is False

    def test_mock_client_get_container_info_found(self):
        """Test mock client returns container info for existing container."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        info = client.get_container_info("test-container-1")
        assert info is not None
        assert info['name'] == "test-container-1"
        assert info['status'] == "running"

    def test_mock_client_get_container_info_not_found(self):
        """Test mock client returns None for non-existent container."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        info = client.get_container_info("non-existent-container")
        assert info is None

    def test_mock_client_list_containers_running_only(self):
        """Test mock client lists running containers."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        containers = client.list_containers(all_containers=False)
        assert len(containers) == 2  # Only running containers
        assert all(c['status'] == 'running' for c in containers)

    def test_mock_client_list_containers_all(self):
        """Test mock client lists all containers."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        containers = client.list_containers(all_containers=True)
        assert len(containers) == 3  # All containers

    def test_mock_client_start_container_not_running(self):
        """Test mock client can start a stopped container."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        result = client.start_container("test-container-2")
        assert result is True
        assert client.is_container_running("test-container-2") is True

    def test_mock_client_start_container_already_running(self):
        """Test mock client returns False when container already running."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        result = client.start_container("test-container-1")
        assert result is False

    def test_mock_client_stop_container_running(self):
        """Test mock client can stop a running container."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        result = client.stop_container("test-container-1")
        assert result is True
        assert client.is_container_running("test-container-1") is False

    def test_mock_client_stop_container_already_stopped(self):
        """Test mock client returns False when container already stopped."""
        from vsclaude.vsclaude.docker import MockDockerClient
        client = MockDockerClient()
        result = client.stop_container("test-container-2")
        assert result is False


class TestDockerClientSecurity:
    """Test Docker client security features."""

    @patch('docker.from_env')
    def test_docker_client_initialization(self, mock_docker):
        """Test Docker client can be initialized."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        assert client.client is not None

    @patch('docker.from_env')
    def test_docker_client_validation_connection_error(self, mock_docker):
        """Test Docker client initialization fails with connection error."""
        import docker.errors
        mock_docker.side_effect = docker.errors.DockerException("Connection failed")

        from vsclaude.vsclaude.docker import DockerClient
        with pytest.raises(DockerConnectionError) as exc_info:
            DockerClient()
        assert "Connection failed" in str(exc_info.value)

    @patch('docker.from_env')
    def test_container_name_validation_valid_names(self, mock_docker):
        """Test valid container names pass validation."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.containers.get.return_value = Mock(status="running")
        mock_docker.return_value = mock_client

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        # These should not raise DockerSecurityError
        client.is_container_running("valid-container")
        client.is_container_running("container123")
        client.is_container_running("container_name")
        client.is_container_running("container.name")

    @patch('docker.from_env')
    def test_container_name_validation_invalid_names(self, mock_docker):
        """Test invalid container names raise DockerSecurityError."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()

        invalid_names = [
            "",  # Empty
            "../container",  # Path traversal
            ";rm -rf /",  # Command injection
            "container|name",  # Pipe
            "container&name",  # Background
            "container`name",  # Backtick
            "$(rm -rf /)",  # Command substitution
            "container/name",  # Invalid character
            "container\\name",  # Escape character
            "container name",  # Space
            "container\nname",  # Newline
            "a" * 256,  # Too long
        ]

        for invalid_name in invalid_names:
            with pytest.raises(DockerSecurityError):
                client.is_container_running(invalid_name)

    @patch('docker.from_env')
    def test_remove_container_name_validation(self, mock_docker):
        """Test remove_container validates container names."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()

        invalid_names = [
            "",  # Empty
            "../container",  # Path traversal
            ";rm -rf /",  # Command injection
            "container|name",  # Pipe
        ]

        for invalid_name in invalid_names:
            with pytest.raises(DockerSecurityError):
                client.remove_container(invalid_name)


class TestDockerClientFunctionality:
    """Test Docker client functionality with mocking."""

    @patch('docker.from_env')
    def test_is_container_running_true(self, mock_docker):
        """Test is_container_running returns True for running container."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_container = Mock()
        mock_container.status = "running"
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.is_container_running("test-container")
        assert result is True

    @patch('docker.from_env')
    def test_is_container_running_false(self, mock_docker):
        """Test is_container_running returns False for stopped container."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_container = Mock()
        mock_container.status = "stopped"
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.is_container_running("test-container")
        assert result is False

    @patch('docker.from_env')
    def test_is_container_running_not_found(self, mock_docker):
        """Test is_container_running returns False for non-existent container."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        import docker.errors
        mock_client.containers.get.side_effect = docker.errors.NotFound("Container not found")

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.is_container_running("non-existent-container")
        assert result is False

    @patch('docker.from_env')
    def test_get_container_info(self, mock_docker):
        """Test get_container_info returns container details."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_container = Mock()
        mock_container.id = "container-id"
        mock_container.name = "test-container"
        mock_container.status = "running"
        mock_image = Mock()
        mock_image.tags = ["nginx:latest"]
        mock_container.image = mock_image
        mock_container.attrs = {
            'Created': '2024-01-01T00:00:00Z',
            'NetworkSettings': {'Ports': {'80/tcp': [{'HostPort': '8080'}]}}
        }
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        info = client.get_container_info("test-container")

        assert info is not None
        assert info['id'] == "container-id"
        assert info['name'] == "test-container"
        assert info['status'] == "running"
        assert info['image'] == "nginx:latest"

    @patch('docker.from_env')
    def test_list_containers(self, mock_docker):
        """Test list_containers returns container list."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_container = Mock()
        mock_container.id = "container-id"
        mock_container.name = "test-container"
        mock_container.status = "running"
        mock_image = Mock()
        mock_image.tags = ["nginx:latest"]
        mock_container.image = mock_image

        mock_client.containers.list.return_value = [mock_container]

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        containers = client.list_containers()

        assert len(containers) == 1
        assert containers[0]['id'] == "container-id"
        assert containers[0]['name'] == "test-container"
        assert containers[0]['status'] == "running"
        assert containers[0]['image'] == "nginx:latest"

    @patch('docker.from_env')
    def test_start_container(self, mock_docker):
        """Test start_container starts a stopped container."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_container = Mock()
        mock_container.status = "stopped"
        mock_container.start.return_value = None
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.start_container("test-container")

        assert result is True
        mock_container.start.assert_called_once()

    @patch('docker.from_env')
    def test_start_container_already_running(self, mock_docker):
        """Test start_container returns False for running container."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_container = Mock()
        mock_container.status = "running"
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.start_container("test-container")

        assert result is False
        mock_container.start.assert_not_called()

    @patch('docker.from_env')
    def test_stop_container(self, mock_docker):
        """Test stop_container stops a running container."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_container = Mock()
        mock_container.status = "running"
        mock_container.stop.return_value = None
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.stop_container("test-container")

        assert result is True
        mock_container.stop.assert_called_once()

    @patch('docker.from_env')
    def test_stop_container_already_stopped(self, mock_docker):
        """Test stop_container returns False for stopped container."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_container = Mock()
        mock_container.status = "stopped"
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.stop_container("test-container")

        assert result is False
        mock_container.stop.assert_not_called()

    @patch('docker.from_env')
    def test_remove_container_success(self, mock_docker):
        """Test remove_container successfully removes a container."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_container = Mock()
        mock_container.remove.return_value = None
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.remove_container("test-container")

        assert result is True
        mock_container.remove.assert_called_once()

    @patch('docker.from_env')
    def test_remove_container_not_found(self, mock_docker):
        """Test remove_container returns False for non-existent container."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        import docker.errors
        mock_client.containers.get.side_effect = docker.errors.NotFound("Container not found")

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.remove_container("non-existent-container")

        assert result is False

    @patch('docker.from_env')
    def test_remove_container_api_error_retry(self, mock_docker):
        """Test remove_container retries on API errors."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        import docker.errors
        # First call raises API error, second succeeds
        mock_client.containers.get.side_effect = [
            docker.errors.APIError("API error"),
            Mock(remove=lambda: None)
        ]

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        # Set lower retries for faster test
        client._max_retries = 2
        result = client.remove_container("test-container")

        assert result is True
        assert mock_client.containers.get.call_count == 2

    @patch('docker.from_env')
    def test_remove_container_api_error_exhausted(self, mock_docker):
        """Test remove_container raises DockerContainerError when retries exhausted."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        import docker.errors
        mock_client.containers.get.side_effect = docker.errors.APIError("Persistent API error")

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        # Set low retries for faster test
        client._max_retries = 1

        with pytest.raises(DockerContainerError):
            client.remove_container("test-container")

    @patch('docker.from_env')
    def test_remove_container_docker_exception(self, mock_docker):
        """Test remove_container raises DockerConnectionError on DockerException."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        import docker.errors
        mock_client.containers.get.side_effect = docker.errors.DockerException("Connection failed")

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()

        with pytest.raises(DockerConnectionError):
            client.remove_container("test-container")

    @patch('docker.from_env')
    def test_remove_container_unexpected_error(self, mock_docker):
        """Test remove_container raises DockerContainerError on unexpected errors."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_client.containers.get.side_effect = Exception("Unexpected error")

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()

        with pytest.raises(DockerContainerError):
            client.remove_container("test-container")

    @patch('docker.from_env')
    def test_remove_container_not_found_after_get(self, mock_docker):
        """Test remove_container handles NotFound when container disappears after get."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        import docker.errors
        mock_container = Mock()
        # Container exists initially but remove raises NotFound
        mock_container.remove.side_effect = docker.errors.NotFound("Container not found")
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        result = client.remove_container("test-container")

        # Should return False when container disappears during removal
        assert result is False

    @patch('docker.from_env')
    def test_remove_container_exception_during_removal(self, mock_docker):
        """Test remove_container handles exceptions during container.remove() call."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        import docker.errors
        mock_container = Mock()
        # Container exists but removal fails with API error
        mock_container.remove.side_effect = docker.errors.APIError("Removal failed")
        mock_client.containers.get.return_value = mock_container

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        # Set low retries for faster test
        client._max_retries = 1

        with pytest.raises(DockerContainerError):
            client.remove_container("test-container")


class TestDockerClientErrorHandling:
    """Test Docker client error handling."""

    @patch('docker.from_env')
    def test_container_operation_api_error_retry(self, mock_docker):
        """Test API errors are retried."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        import docker.errors
        # First call raises API error, second succeeds
        mock_client.containers.get.side_effect = [
            docker.errors.APIError("API error"),
            Mock(status="running")
        ]

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        # Set lower retries for faster test
        client._max_retries = 2
        result = client.is_container_running("test-container")

        assert result is True
        assert mock_client.containers.get.call_count == 2

    @patch('docker.from_env')
    def test_container_operation_api_error_exhausted(self, mock_docker):
        """Test API errors exhausted raise DockerContainerError."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        mock_client.containers.get.side_effect = Exception("Persistent API error")

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()
        # Set low retries for faster test
        client._max_retries = 1

        with pytest.raises(DockerContainerError):
            client.is_container_running("test-container")

    @patch('docker.from_env')
    def test_container_not_found_error(self, mock_docker):
        """Test container not found handling for different operations."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        import docker.errors
        mock_client.containers.get.side_effect = docker.errors.NotFound("Container not found")

        from vsclaude.vsclaude.docker import DockerClient
        client = DockerClient()

        # start/stop should raise DockerContainerError
        with pytest.raises(DockerContainerError):
            client.start_container("non-existent-container")

        with pytest.raises(DockerContainerError):
            client.stop_container("non-existent-container")

        # remove_container should return False
        result = client.remove_container("non-existent-container")
        assert result is False


class TestFactoryFunction:
    """Test Docker client factory function."""

    @patch('docker.from_env')
    def test_create_docker_client(self, mock_docker):
        """Test factory function creates Docker client."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        from vsclaude.vsclaude.docker import create_docker_client
        client = create_docker_client(max_retries=5)
        assert client._max_retries == 5

    @patch('docker.from_env')
    def test_create_docker_client_default_retries(self, mock_docker):
        """Test factory function uses default retries."""
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        from vsclaude.vsclaude.docker import create_docker_client
        client = create_docker_client()
        assert client._max_retries == 3


def test_remove_container_success():
    """Test successful container removal"""
    from vsclaude.vsclaude.docker import MockDockerClient
    client = MockDockerClient()
    assert client.remove_container("test-container-1") == True
    assert "test-container-1" not in client.mock_containers


@patch('docker.from_env')
def test_network_exists(mock_docker):
    """Test network existence checking"""
    # Mock the Docker client and network operations
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_docker.return_value = mock_client

    from vsclaude.vsclaude.docker import DockerClient
    docker_client = DockerClient()

    # Test with existing network
    mock_network = Mock()
    mock_client.networks.get.return_value = mock_network
    assert docker_client.network_exists("bridge") == True

    # Test with non-existent network
    import docker.errors
    mock_client.networks.get.side_effect = docker.errors.NotFound("Network not found")
    assert docker_client.network_exists("non-existent-network") == False


def test_mock_docker_client_network_exists():
    """Test mock Docker client network existence checking"""
    from vsclaude.vsclaude.docker import MockDockerClient
    mock_client = MockDockerClient()

    # Test with existing mock networks
    assert mock_client.network_exists("bridge") == True
    assert mock_client.network_exists("host") == True
    assert mock_client.network_exists("none") == True

    # Test with non-existent network
    assert mock_client.network_exists("non-existent-network") == False


@patch('docker.from_env')
def test_network_exists_api_error(mock_docker):
    """Test network existence checking with API errors"""
    # Mock the Docker client and network operations
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_docker.return_value = mock_client

    import docker.errors
    from vsclaude.vsclaude.docker import DockerClient, DockerConnectionError
    docker_client = DockerClient()

    # Test API error handling
    mock_client.networks.get.side_effect = docker.errors.APIError("API error")
    with pytest.raises(DockerConnectionError):
        docker_client.network_exists("bridge")


@patch('docker.from_env')
def test_network_exists_docker_connection_error(mock_docker):
    """Test network existence checking with Docker connection errors"""
    # Mock the Docker client and network operations
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_docker.return_value = mock_client

    import docker.errors
    from vsclaude.vsclaude.docker import DockerClient, DockerConnectionError
    docker_client = DockerClient()

    # Test Docker connection error handling
    mock_client.networks.get.side_effect = docker.errors.DockerException("Connection failed")
    with pytest.raises(DockerConnectionError):
        docker_client.network_exists("bridge")


@patch('docker.from_env')
def test_network_exists_unexpected_error(mock_docker):
    """Test network existence checking with unexpected errors"""
    # Mock the Docker client and network operations
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_docker.return_value = mock_client

    from vsclaude.vsclaude.docker import DockerClient, DockerContainerError
    docker_client = DockerClient()

    # Test unexpected error handling
    mock_client.networks.get.side_effect = Exception("Unexpected error")
    with pytest.raises(DockerContainerError):
        docker_client.network_exists("bridge")