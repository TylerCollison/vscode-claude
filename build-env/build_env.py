"""Build environment manager core logic."""

import os
from typing import Dict, Optional, Any
import docker
from docker.errors import NotFound

from security import (
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
        if not env_vars.get("BUILD_CONTAINER"):
            raise BuildEnvironmentError("BUILD_CONTAINER environment variable must be set")

        # Check for DEFAULT_WORKSPACE environment variable
        if not env_vars.get("DEFAULT_WORKSPACE"):
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

    def _is_docker_in_docker(self) -> bool:
        """Check if running in Docker-in-Docker scenario.

        Returns:
            True if running Docker-in-Docker, False otherwise
        """
        # Check if we're inside a container by looking for .dockerenv
        return os.path.exists('/.dockerenv') and os.path.exists('/var/run/docker.sock')

    def _synchronize_workspace_bidirectional(self, container_name: str, workspace_path: str) -> bool:
        """Bidirectional synchronization that handles file deletions properly.

        Args:
            container_name: Name of the container
            workspace_path: Path to the workspace

        Returns:
            True if successful, False otherwise
        """
        try:
            import subprocess
            import tempfile

            # Get container
            container = self.docker_client.containers.get(container_name)

            # Create workspace directory in container if it doesn't exist
            exec_result = container.exec_run(f'mkdir -p {workspace_path}')
            if exec_result.exit_code != 0:
                return False

            # Create temporary directory for comparison
            with tempfile.TemporaryDirectory() as temp_dir:
                # Step 1: Copy container files to temp directory
                container_temp = os.path.join(temp_dir, 'container')
                host_temp = os.path.join(temp_dir, 'host')

                os.makedirs(container_temp)
                os.makedirs(host_temp)

                # Copy container files to temp directory
                result = subprocess.run(
                    ['docker', 'cp', f'{container_name}:{workspace_path}/.', container_temp],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    return False

                # Copy host files to temp directory
                result = subprocess.run(
                    ['cp', '-r', f'{workspace_path}/.', host_temp],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    return False

                # Step 2: Compare and sync deletions
                # Get list of files in both locations
                def get_file_list(directory):
                    file_list = set()
                    for root, dirs, files in os.walk(directory):
                        for file in files:
                            rel_path = os.path.relpath(os.path.join(root, file), directory)
                            file_list.add(rel_path)
                    return file_list

                container_files = get_file_list(container_temp)
                host_files = get_file_list(host_temp)

                # Files that exist in container but not in host (should be copied to host)
                files_to_copy_to_host = container_files - host_files

                # Files that exist in host but not in container (should be copied to container)
                files_to_copy_to_container = host_files - container_files

                # Step 3: Copy files from container to host
                for file_path in files_to_copy_to_host:
                    # Copy from container temp to host
                    source_path = os.path.join(container_temp, file_path)
                    dest_path = os.path.join(workspace_path, file_path)

                    # Ensure destination directory exists
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                    result = subprocess.run(
                        ['cp', '-r', source_path, dest_path],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode != 0:
                        return False

                # Step 4: Copy files from host to container
                for file_path in files_to_copy_to_container:
                    # Copy from host temp to container
                    source_path = os.path.join(host_temp, file_path)

                    # Use docker cp to copy to container
                    result = subprocess.run(
                        ['docker', 'cp', source_path, f'{container_name}:{workspace_path}/{file_path}'],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode != 0:
                        return False

                # Step 5: Handle deletions
                # For files that exist in both locations, check if they're different
                common_files = container_files & host_files
                for file_path in common_files:
                    container_file = os.path.join(container_temp, file_path)
                    host_file = os.path.join(host_temp, file_path)

                    # Compare file contents
                    result = subprocess.run(
                        ['cmp', '-s', container_file, host_file],
                        capture_output=True
                    )

                    # If files differ, copy the newer version
                    if result.returncode != 0:
                        # Get modification times
                        container_mtime = os.path.getmtime(container_file)
                        host_mtime = os.path.getmtime(host_file)

                        if container_mtime > host_mtime:
                            # Container version is newer, copy to host
                            result = subprocess.run(
                                ['cp', '-r', container_file, os.path.join(workspace_path, file_path)],
                                capture_output=True,
                                text=True
                            )
                        else:
                            # Host version is newer, copy to container
                            result = subprocess.run(
                                ['docker', 'cp', host_file, f'{container_name}:{workspace_path}/{file_path}'],
                                capture_output=True,
                                text=True
                            )

                        if result.returncode != 0:
                            return False

            return True

        except Exception:
            return False

    def _copy_workspace_to_container(self, container_name: str, workspace_path: str) -> bool:
        """Copy workspace files to container using docker cp command.
        Maintained for backward compatibility.

        Args:
            container_name: Name of the container
            workspace_path: Path to the workspace

        Returns:
            True if successful, False otherwise
        """
        try:
            # Use docker cp to copy files from current container to build container
            import subprocess

            # First, create the workspace directory in the container
            container = self.docker_client.containers.get(container_name)
            exec_result = container.exec_run(f'mkdir -p {workspace_path}')

            if exec_result.exit_code != 0:
                return False

            # Copy all files from workspace to container
            result = subprocess.run(
                ['docker', 'cp', workspace_path + '/.', f'{container_name}:{workspace_path}'],
                capture_output=True,
                text=True
            )

            return result.returncode == 0
        except Exception:
            return False

    def _copy_workspace_from_container(self, container_name: str, workspace_path: str) -> bool:
        """Copy workspace files from container back to host using docker cp command.
        Maintained for backward compatibility.

        Args:
            container_name: Name of the container
            workspace_path: Path to the workspace

        Returns:
            True if successful, False otherwise
        """
        try:
            # Use docker cp to copy files from build container back to host
            import subprocess

            # Ensure the host workspace directory exists
            os.makedirs(workspace_path, exist_ok=True)

            # Copy all files from container workspace back to host
            result = subprocess.run(
                ['docker', 'cp', f'{container_name}:{workspace_path}/.', workspace_path],
                capture_output=True,
                text=True
            )

            return result.returncode == 0
        except Exception:
            return False

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

        # First check if we have a stored UUID for this workspace
        stored_uuid = self._get_stored_container_uuid(workspace_path)
        if stored_uuid:
            container_name = f"build-env-{stored_uuid}"
            # Check if stored container exists and is running
            try:
                container = self.docker_client.containers.get(container_name)
                if container.status == "running":
                    return container_name
                else:
                    # Container exists but is not running, remove it
                    container.stop()
                    container.remove(force=True)
                    # Remove the stale UUID file
                    self._remove_stored_uuid(workspace_path)
            except NotFound:
                # Stored container doesn't exist, remove stale UUID file
                self._remove_stored_uuid(workspace_path)

        # Generate new container name
        container_name = self._generate_container_name()

        # Create and start new container
        try:
            self.docker_client.images.get(image_name)
        except NotFound:
            raise BuildEnvironmentError(f"Docker image not found: {image_name}")

        # Create container without volume mount
        # We'll copy files on each command execution for Docker-in-Docker scenarios
        container = self.docker_client.containers.create(
            image=image_name,
            name=container_name,
            working_dir=workspace_path,
            environment=env_vars,
            command=["tail", "-f", "/dev/null"],  # Keep container running
            detach=True
        )
        container.start()

        # Synchronize workspace files for Docker-in-Docker scenarios
        if self._is_docker_in_docker():
            self._synchronize_workspace_bidirectional(container_name, workspace_path)

        container.start()

        # Synchronize workspace files after container startup
        # This ensures any initial container setup is reflected back to host
        if self._is_docker_in_docker():
            self._synchronize_workspace_bidirectional(container_name, workspace_path)

        # Store container UUID in file for later shutdown
        self._store_container_uuid(container_name, workspace_path)

        return container_name

    def _execute_command(self, container_name: str, command: str, env_vars: Dict[str, str]) -> tuple:
        """Execute command in container.

        Args:
            container_name: Name of the container
            command: Command to execute
            env_vars: Environment variables

        Returns:
            Tuple of (exit_code, output)
        """
        # Get container
        container = self.docker_client.containers.get(container_name)

        # If running Docker-in-Docker, synchronize workspace files before executing command
        if self._is_docker_in_docker():
            workspace_path = env_vars.get('DEFAULT_WORKSPACE', '/workspace')
            self._synchronize_workspace_bidirectional(container_name, workspace_path)

        # Execute command
        exec_result = container.exec_run(
            command,
            detach=False,
            environment=env_vars,
            workdir=env_vars.get('DEFAULT_WORKSPACE', '/workspace'),
            tty=True,
            stdin=True
        )

        # Synchronize workspace files back from container to host after command execution
        if self._is_docker_in_docker():
            workspace_path = env_vars.get('DEFAULT_WORKSPACE', '/workspace')
            self._synchronize_workspace_bidirectional(container_name, workspace_path)

        # Return exit code and output
        return exec_result.exit_code, exec_result.output

    def _store_container_uuid(self, container_name: str, workspace_path: str) -> None:
        """Store container UUID in a file for later shutdown.

        Args:
            container_name: Name of the container
            workspace_path: Path to the workspace
        """
        # Extract UUID from container name (format: build-env-{uuid})
        uuid = container_name.replace("build-env-", "")

        # Create .build-env directory in workspace
        build_env_dir = os.path.join(workspace_path, ".build-env")
        os.makedirs(build_env_dir, exist_ok=True)

        # Write UUID to file
        uuid_file = os.path.join(build_env_dir, "container.uuid")
        with open(uuid_file, 'w') as f:
            f.write(uuid)

    def _get_stored_container_uuid(self, workspace_path: str) -> Optional[str]:
        """Get stored container UUID for workspace.

        Args:
            workspace_path: Path to the workspace

        Returns:
            UUID string if found, None otherwise
        """
        uuid_file = os.path.join(workspace_path, ".build-env", "container.uuid")

        if os.path.exists(uuid_file):
            with open(uuid_file, 'r') as f:
                return f.read().strip()
        return None

    def _remove_stored_uuid(self, workspace_path: str) -> None:
        """Remove stored container UUID for workspace.

        Args:
            workspace_path: Path to the workspace
        """
        uuid_file = os.path.join(workspace_path, ".build-env", "container.uuid")
        if os.path.exists(uuid_file):
            os.remove(uuid_file)

    def _shutdown_container(self, container_name: str) -> None:
        """Shutdown and remove container.

        Args:
            container_name: Name of the container to shutdown
        """
        container = self.docker_client.containers.get(container_name)
        container.stop()
        container.remove(force=True)

        # Clean up UUID file if it exists
        try:
            # Try to find workspace path from container
            workspace_path = container.attrs['Config']['WorkingDir']
            uuid_file = os.path.join(workspace_path, ".build-env", "container.uuid")
            if os.path.exists(uuid_file):
                os.remove(uuid_file)
        except (KeyError, Exception):
            # If we can't clean up, continue anyway
            pass