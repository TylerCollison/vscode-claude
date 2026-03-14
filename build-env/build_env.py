"""Build environment manager core logic."""

import os
import re
import uuid
from typing import Dict, Any, Optional, List
import docker
from docker.errors import NotFound

from build_env.security import (
    validate_image_name, filter_environment_variables,
    generate_container_uuid, SecurityError
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
            Unique container name with format: build-{uuid}
        """
        return f"build-{generate_container_uuid()}"

    def _validate_requirements(self, requirements: Dict[str, Any]) -> bool:
        """Validate build environment requirements.

        Args:
            requirements: Dictionary containing build environment requirements

        Returns:
            True if requirements are valid

        Raises:
            BuildEnvironmentError: If requirements are invalid
        """
        if "image" not in requirements:
            raise BuildEnvironmentError("Docker image is required")

        # Validate image name using security module
        try:
            validate_image_name(requirements["image"])
        except Exception as e:
            raise BuildEnvironmentError(f"Invalid image name: {e}")

        # Check for BUILD_CONTAINER environment variable
        if not os.environ.get("BUILD_CONTAINER"):
            raise BuildEnvironmentError("BUILD_CONTAINER environment variable is required")

        # Check for DEFAULT_WORKSPACE environment variable
        if not os.environ.get("DEFAULT_WORKSPACE"):
            raise BuildEnvironmentError("DEFAULT_WORKSPACE environment variable is required")

        # Filter environment variables
        if "environment" in requirements:
            requirements["environment"] = filter_environment_variables(
                requirements["environment"]
            )

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
            BuildEnvironmentError: If container doesn't exist
        """
        try:
            container = self.docker_client.containers.get(container_name)
            return container.id
        except NotFound:
            raise BuildEnvironmentError(f"Container '{container_name}' does not exist")