"""Build environment manager core logic."""

import os
from typing import Dict, Optional, Any
import docker
from docker.errors import NotFound

from build_env.security import (
    filter_environment_variables,
    generate_container_uuid,
    validate_image_name,
    SecurityError
)


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

    def _start_container(self, image_name: str, workspace_path: str, env_vars: Dict[str, str]) -> str:
        """Start or create build container.

        Args:
            image_name: Docker image name
            workspace_path: Path to the workspace
            env_vars: Environment variables

        Returns:
            Container name
        """
        # Validate image name
        try:
            validate_image_name(image_name)
        except SecurityError as e:
            raise BuildEnvironmentError(f"Invalid image name: {e}")

        # Filter environment variables
        filtered_env_vars = filter_environment_variables(env_vars)

        container_name = self._generate_container_name()

        # Check if container exists and is running
        try:
            container = self.docker_client.containers.get(container_name)
            if container.status == "running":
                return container_name
            else:
                # Container exists but is not running, remove it
                container.stop()
                container.remove(force=True)
        except NotFound:
            # Container doesn't exist, proceed to create new one
            pass

        # Create and start new container
        try:
            self.docker_client.images.get(image_name)
        except NotFound:
            raise BuildEnvironmentError(f"Docker image not found: {image_name}")

        container = self.docker_client.containers.create(
            image=image_name,
            name=container_name,
            working_dir=workspace_path,
            volumes={workspace_path: {"bind": workspace_path, "mode": "rw"}},
            environment=filtered_env_vars,
            detach=True
        )

        container.start()
        return container_name

    def _execute_command(self, container_name: str, command: str, env_vars: Dict[str, str]) -> Any:
        """Execute command in container.

        Args:
            container_name: Name of the container
            command: Command to execute
            env_vars: Environment variables

        Returns:
            Execution result
        """
        # Filter environment variables
        filtered_env_vars = filter_environment_variables(env_vars)

        # Get container
        container = self.docker_client.containers.get(container_name)

        return container.exec_run(
            command,
            detach=False,
            environment=filtered_env_vars,
            workdir="/workspace",
            tty=True,
            stdin=True
        )

    def _shutdown_container(self, container_name: str) -> None:
        """Shutdown and remove container.

        Args:
            container_name: Name of the container to shutdown
        """
        container = self.docker_client.containers.get(container_name)
        container.stop()
        container.remove(force=True)