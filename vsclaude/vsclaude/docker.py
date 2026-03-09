import docker
import re
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class DockerSecurityError(Exception):
    """Security-related error for Docker operations."""
    pass


class DockerConnectionError(Exception):
    """Error indicating Docker daemon connectivity issues."""
    pass


class DockerContainerError(Exception):
    """Error related to container operations."""
    pass


class DockerClientInterface(ABC):
    """Abstract interface for Docker client operations.

    This interface defines the contract for Docker client implementations,
    promoting loose coupling and dependency injection.
    """

    @abstractmethod
    def is_container_running(self, container_name: str) -> bool:
        """Check if a Docker container is running.

        Args:
            container_name: The name of the container to check

        Returns:
            bool: True if container exists and is running, False otherwise
        """
        pass

    @abstractmethod
    def get_container_info(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a container.

        Args:
            container_name: The name of the container to inspect

        Returns:
            dict: Container information dictionary, or None if container not found
        """
        pass

    @abstractmethod
    def list_containers(self, all_containers: bool = False) -> List[Dict[str, Any]]:
        """List containers with optional filtering.

        Args:
            all_containers: Whether to include stopped containers

        Returns:
            list: List of container information dictionaries
        """
        pass

    @abstractmethod
    def start_container(self, container_name: str) -> bool:
        """Start a Docker container.

        Args:
            container_name: The name of the container to start

        Returns:
            bool: True if container was started successfully, False if already running
        """
        pass

    @abstractmethod
    def stop_container(self, container_name: str) -> bool:
        """Stop a Docker container.

        Args:
            container_name: The name of the container to stop

        Returns:
            bool: True if container was stopped successfully, False if already stopped
        """
        pass


class DockerClient(DockerClientInterface):
    """A secure Docker client for managing container operations.

    This class provides a secure interface to the Docker API with proper
    input validation, error handling, and security best practices.

    Attributes:
        client: The underlying Docker client instance
        _max_retries: Maximum number of retry attempts for operations
    """

    # Valid container name pattern: alphanumeric, underscore, hyphen, dot
    # Must not start with hyphen or dot
    CONTAINER_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$')
    MAX_CONTAINER_NAME_LENGTH = 255
    MAX_RETRY_ATTEMPTS = 3

    def __init__(self):
        """Initialize the Docker client with security validation.

        Raises:
            DockerConnectionError: If Docker daemon is not available
            DockerSecurityError: If security constraints cannot be verified
        """
        self._max_retries = self.MAX_RETRY_ATTEMPTS

        if docker is None:
            raise DockerConnectionError("Docker module not available - cannot initialize Docker client")

        try:
            self.client = docker.from_env()
            # Verify Docker daemon is running and accessible
            self._validate_docker_environment()
        except docker.errors.DockerException as e:
            raise DockerConnectionError(f"Docker daemon not available: {e}") from e

    def _validate_docker_environment(self) -> None:
        """Validate Docker environment security constraints.

        Raises:
            DockerSecurityError: If Docker environment has security issues
        """
        try:
            # Verify Docker daemon is running
            self.client.ping()
        except docker.errors.APIError as e:
            raise DockerSecurityError(f"Docker API security issue: {e}") from e
        except Exception as e:
            raise DockerConnectionError(f"Docker environment validation failed: {e}") from e

    def _validate_container_name(self, container_name: str) -> None:
        """Validate container name for security and Docker compliance.

        Args:
            container_name: The container name to validate

        Raises:
            DockerSecurityError: If container name is invalid or insecure
        """
        if not container_name or not isinstance(container_name, str):
            raise DockerSecurityError("Container name must be a non-empty string")

        if len(container_name) > self.MAX_CONTAINER_NAME_LENGTH:
            raise DockerSecurityError(
                f"Container name exceeds maximum length of {self.MAX_CONTAINER_NAME_LENGTH}"
            )

        if not self.CONTAINER_NAME_PATTERN.match(container_name):
            raise DockerSecurityError(
                "Container name must contain only alphanumeric characters, underscores, "
                "hyphens, and dots, and cannot start with a hyphen or dot"
            )

        # Additional security checks
        self._check_for_potential_injections(container_name)

    def _check_for_potential_injections(self, container_name: str) -> None:
        """Check container name for potential injection patterns.

        Args:
            container_name: The container name to check

        Raises:
            DockerSecurityError: If potential injection pattern detected
        """
        # Check for command injection patterns
        injection_patterns = [
            ';', '|', '&', '`', '$', '(', ')', '<', '>', '"', "'", '\\',
            '..', '../', './'
        ]

        for pattern in injection_patterns:
            if pattern in container_name:
                raise DockerSecurityError(
                    f"Container name contains potentially dangerous pattern: {pattern}"
                )

    def is_container_running(self, container_name: str) -> bool:
        """Check if a Docker container is running with security validation.

        Args:
            container_name: The name of the container to check

        Returns:
            bool: True if container exists and is running, False otherwise

        Raises:
            DockerSecurityError: If container name validation fails
            DockerConnectionError: If Docker daemon communication fails
            DockerContainerError: If container operation encounters an error
        """
        # Validate input first
        self._validate_container_name(container_name)

        for attempt in range(self._max_retries):
            try:
                container = self.client.containers.get(container_name)
                return container.status == "running"
            except docker.errors.NotFound:
                return False
            except docker.errors.APIError as e:
                if attempt == self._max_retries - 1:
                    raise DockerContainerError(
                        f"Failed to check container status after {self._max_retries} attempts: {e}"
                    ) from e
                # Retry on transient API errors
                continue
            except docker.errors.DockerException as e:
                raise DockerConnectionError(f"Docker communication error: {e}") from e
            except Exception as e:
                raise DockerContainerError(f"Unexpected error checking container: {e}") from e

    def get_container_info(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a container with security validation.

        Args:
            container_name: The name of the container to inspect

        Returns:
            dict: Container information dictionary, or None if container not found

        Raises:
            DockerSecurityError: If container name validation fails
            DockerConnectionError: If Docker daemon communication fails
            DockerContainerError: If container operation encounters an error
        """
        self._validate_container_name(container_name)

        for attempt in range(self._max_retries):
            try:
                container = self.client.containers.get(container_name)
                return {
                    'id': container.id,
                    'name': container.name,
                    'status': container.status,
                    'image': container.image.tags[0] if container.image.tags else str(container.image),
                    'created': container.attrs['Created'],
                    'ports': container.attrs.get('NetworkSettings', {}).get('Ports', {})
                }
            except docker.errors.NotFound:
                return None
            except docker.errors.APIError as e:
                if attempt == self._max_retries - 1:
                    raise DockerContainerError(
                        f"Failed to get container info after {self._max_retries} attempts: {e}"
                    ) from e
                continue
            except docker.errors.DockerException as e:
                raise DockerConnectionError(f"Docker communication error: {e}") from e
            except Exception as e:
                raise DockerContainerError(f"Unexpected error getting container info: {e}") from e

    def list_containers(self, all_containers: bool = False) -> List[Dict[str, Any]]:
        """List containers with optional filtering.

        Args:
            all_containers: Whether to include stopped containers

        Returns:
            list: List of container information dictionaries

        Raises:
            DockerConnectionError: If Docker daemon communication fails
            DockerContainerError: If container operation encounters an error
        """
        for attempt in range(self._max_retries):
            try:
                containers = self.client.containers.list(all=all_containers)
                return [
                    {
                        'id': container.id,
                        'name': container.name,
                        'status': container.status,
                        'image': container.image.tags[0] if container.image.tags else str(container.image)
                    }
                    for container in containers
                ]
            except docker.errors.APIError as e:
                if attempt == self._max_retries - 1:
                    raise DockerContainerError(
                        f"Failed to list containers after {self._max_retries} attempts: {e}"
                    ) from e
                continue
            except docker.errors.DockerException as e:
                raise DockerConnectionError(f"Docker communication error: {e}") from e
            except Exception as e:
                raise DockerContainerError(f"Unexpected error listing containers: {e}") from e

    def start_container(self, container_name: str) -> bool:
        """Start a Docker container.

        Args:
            container_name: The name of the container to start

        Returns:
            bool: True if container was started successfully, False if already running

        Raises:
            DockerSecurityError: If container name validation fails
            DockerConnectionError: If Docker daemon communication fails
            DockerContainerError: If container operation encounters an error
        """
        self._validate_container_name(container_name)

        for attempt in range(self._max_retries):
            try:
                container = self.client.containers.get(container_name)
                if container.status == "running":
                    return False
                container.start()
                return True
            except docker.errors.NotFound:
                raise DockerContainerError(f"Container '{container_name}' not found")
            except docker.errors.APIError as e:
                if attempt == self._max_retries - 1:
                    raise DockerContainerError(
                        f"Failed to start container after {self._max_retries} attempts: {e}"
                    ) from e
                continue
            except docker.errors.DockerException as e:
                raise DockerConnectionError(f"Docker communication error: {e}") from e
            except Exception as e:
                raise DockerContainerError(f"Unexpected error starting container: {e}") from e

    def stop_container(self, container_name: str) -> bool:
        """Stop a Docker container.

        Args:
            container_name: The name of the container to stop

        Returns:
            bool: True if container was stopped successfully, False if already stopped

        Raises:
            DockerSecurityError: If container name validation fails
            DockerConnectionError: If Docker daemon communication fails
            DockerContainerError: If container operation encounters an error
        """
        self._validate_container_name(container_name)

        for attempt in range(self._max_retries):
            try:
                container = self.client.containers.get(container_name)
                if container.status != "running":
                    return False
                container.stop()
                return True
            except docker.errors.NotFound:
                raise DockerContainerError(f"Container '{container_name}' not found")
            except docker.errors.APIError as e:
                if attempt == self._max_retries - 1:
                    raise DockerContainerError(
                        f"Failed to stop container after {self._max_retries} attempts: {e}"
                    ) from e
                continue
            except docker.errors.DockerException as e:
                raise DockerConnectionError(f"Docker communication error: {e}") from e
            except Exception as e:
                raise DockerContainerError(f"Unexpected error stopping container: {e}") from e


def create_docker_client(max_retries: int = 3) -> DockerClient:
    """Factory function to create a Docker client with configurable retries.

    Args:
        max_retries: Maximum number of retry attempts for operations

    Returns:
        DockerClient: A configured Docker client instance
    """
    client = DockerClient()
    client._max_retries = max_retries
    return client


class MockDockerClient(DockerClientInterface):
    """Mock Docker client for testing purposes.

    This implementation simulates Docker operations without requiring
    an actual Docker daemon, making it ideal for unit testing.
    """

    def __init__(self):
        """Initialize mock Docker client with test data."""
        self.mock_containers = {
            'test-container-1': {'status': 'running', 'image': 'nginx:latest'},
            'test-container-2': {'status': 'stopped', 'image': 'redis:latest'},
            'valid-container': {'status': 'running', 'image': 'python:3.9'}
        }

    def is_container_running(self, container_name: str) -> bool:
        """Mock implementation of container running check.

        Args:
            container_name: The name of the container to check

        Returns:
            bool: True if mock container exists and is running
        """
        if container_name not in self.mock_containers:
            return False
        return self.mock_containers[container_name]['status'] == 'running'

    def get_container_info(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Mock implementation of container info retrieval.

        Args:
            container_name: The name of the container to inspect

        Returns:
            dict: Mock container information
        """
        if container_name not in self.mock_containers:
            return None

        container = self.mock_containers[container_name]
        return {
            'id': f'mock-{container_name}',
            'name': container_name,
            'status': container['status'],
            'image': container['image'],
            'created': '2024-01-01T00:00:00Z',
            'ports': {'80/tcp': [{'HostPort': '8080'}]}
        }

    def list_containers(self, all_containers: bool = False) -> List[Dict[str, Any]]:
        """Mock implementation of container listing.

        Args:
            all_containers: Whether to include stopped containers

        Returns:
            list: List of mock container information
        """
        result = []
        for name, container in self.mock_containers.items():
            if all_containers or container['status'] == 'running':
                result.append({
                    'id': f'mock-{name}',
                    'name': name,
                    'status': container['status'],
                    'image': container['image']
                })
        return result

    def start_container(self, container_name: str) -> bool:
        """Mock implementation of container start.

        Args:
            container_name: The name of the container to start

        Returns:
            bool: True if container state was changed
        """
        if container_name not in self.mock_containers:
            return False

        if self.mock_containers[container_name]['status'] != 'running':
            self.mock_containers[container_name]['status'] = 'running'
            return True
        return False

    def stop_container(self, container_name: str) -> bool:
        """Mock implementation of container stop.

        Args:
            container_name: The name of the container to stop

        Returns:
            bool: True if container state was changed
        """
        if container_name not in self.mock_containers:
            return False

        if self.mock_containers[container_name]['status'] == 'running':
            self.mock_containers[container_name]['status'] = 'stopped'
            return True
        return False