"""Build environment manager core logic."""

import re
import uuid
from typing import Dict, Any, Optional
import docker
from docker.errors import NotFound


class BuildEnvironmentManager:
    """Manages persistent Docker container environments for build commands."""

    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        """Initialize the build environment manager.

        Args:
            docker_client: Docker client instance. If None, creates a new one.
        """
        self.docker_client = docker_client or docker.from_env()

    def _generate_container_name(self, project_name: str) -> str:
        """Generate a unique container name for the project.

        Args:
            project_name: Name of the project

        Returns:
            Unique container name with format: {project}-{uuid8}
        """
        # Clean project name - replace non-alphanumeric characters with hyphens
        clean_name = re.sub(r'[^a-zA-Z0-9]', '-', project_name)
        clean_name = re.sub(r'-+', '-', clean_name).strip('-')

        # Generate unique identifier
        uuid_short = str(uuid.uuid4())[:8]

        return f"{clean_name}-{uuid_short}"

    def _validate_requirements(self, requirements: Dict[str, Any]) -> bool:
        """Validate build environment requirements.

        Args:
            requirements: Dictionary containing build environment requirements

        Returns:
            True if requirements are valid

        Raises:
            ValueError: If requirements are invalid
        """
        if "image" not in requirements:
            raise ValueError("Docker image is required")

        if not isinstance(requirements["image"], str):
            raise ValueError("Docker image must be a string")

        # Optional validation for working directory
        if "working_dir" in requirements:
            if not isinstance(requirements["working_dir"], str):
                raise ValueError("Working directory must be a string")

        # Optional validation for command
        if "command" in requirements:
            if not isinstance(requirements["command"], (list, tuple)):
                raise ValueError("Command must be a list or tuple")

        return True

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

    def _get_container_uuid(self, container_name: str) -> str:
        """Get the unique identifier for a container.

        Args:
            container_name: Name of the container

        Returns:
            Container UUID (ID)

        Raises:
            ValueError: If container doesn't exist
        """
        try:
            container = self.docker_client.containers.get(container_name)
            return container.id
        except NotFound:
            raise ValueError(f"Container '{container_name}' does not exist")