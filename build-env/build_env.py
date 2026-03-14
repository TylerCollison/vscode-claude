"""Build environment manager core logic."""

import os
from typing import Dict, Optional, Any
import docker
from docker.errors import NotFound

from build_env.security import generate_container_uuid


class BuildEnvironmentError(Exception):
    """Build environment error."""
    pass


class BuildEnvironmentManager:
    """Manages persistent Docker container environments for build commands."""

    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        """Initialize the build environment manager.

        Args:
            docker_client: Docker client instance. If None, creates a new one.
        """
        self.docker_client = docker_client or docker.from_env()

    def _generate_container_name(self) -> str:
        """Generate a unique container name.

        Returns:
            Unique container name with format: build-env-{uuid}
        """
        return f"build-env-{generate_container_uuid()}"

    def _validate_requirements(self, env_vars: Dict[str, str]) -> None:
        """Validate build environment requirements.

        Args:
            env_vars: Dictionary of environment variables

        Raises:
            BuildEnvironmentError: If requirements are invalid
        """
        # Check for BUILD_CONTAINER environment variable
        if not os.environ.get("BUILD_CONTAINER"):
            raise BuildEnvironmentError("BUILD_CONTAINER environment variable is required")

        # Check for DEFAULT_WORKSPACE environment variable
        if not os.environ.get("DEFAULT_WORKSPACE"):
            raise BuildEnvironmentError("DEFAULT_WORKSPACE environment variable is required")

    def _container_exists(self, container_name: str) -> bool:
        """Check if a container exists.

        Args:
            container_name: Name of the container to check

        Returns:
            True if container exists, False otherwise
        """
        try:
            self.docker_client.containers.get(container_name)
            return True
        except NotFound:
            return False

    def _container_running(self, container_name: str) -> bool:
        """Check if a container is running.

        Args:
            container_name: Name of the container to check

        Returns:
            True if container is running, False otherwise
        """
        try:
            container = self.docker_client.containers.get(container_name)
            return container.status == "running"
        except NotFound:
            return False

    def _get_container_uuid(self, workspace_path: str) -> str:
        """Get the unique identifier for a workspace.

        Args:
            workspace_path: Path to the workspace

        Returns:
            UUID string
        """
        return generate_container_uuid()

    def _start_container(self, image_name: str, workspace_path: str, env_vars: Dict[str, str]) -> Any:
        """Start or create build container.

        Args:
            image_name: Docker image name
            workspace_path: Path to the workspace
            env_vars: Environment variables

        Returns:
            Container instance
        """
        container_name = self._generate_container_name()

        # Try to get existing container
        try:
            container = self.docker_client.containers.get(container_name)
            # If container exists and is running, return it
            if container.status == "running":
                return container
            # If container exists but is not running, remove it
            else:
                container.remove(force=True)
        except NotFound:
            # Container doesn't exist, proceed to create new one
            pass

        # Create new container
        container = self.docker_client.containers.create(
            image=image_name,
            name=container_name,
            working_dir=workspace_path,
            volumes={workspace_path: {"bind": workspace_path, "mode": "rw"}},
            environment=env_vars,
            detach=True
        )

        # Start the container
        container.start()
        return container

    def _execute_command(self, container: Any, command: str) -> Any:
        """Execute command in container.

        Args:
            container: Container instance
            command: Command to execute

        Returns:
            Execution result
        """
        return container.exec_run(command, detach=False)

    def _shutdown_container(self, container: Any) -> None:
        """Shutdown and remove container.

        Args:
            container: Container instance to shutdown
        """
        container.stop()
        container.remove(force=True)