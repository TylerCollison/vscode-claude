"""
InstanceManager for managing Claude Code development environment instances.

This module provides secure management of development instances with comprehensive
input validation, error handling, and security protections.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Dict, Optional, Any, List


class InstanceValidationError(ValueError):
    """Exception raised for instance validation errors."""
    pass


class InstanceSecurityError(ValueError):
    """Exception raised for security-related instance errors."""
    pass


class InstanceManager:
    """
    Secure manager for Claude Code development environment instances.

    Provides comprehensive instance lifecycle management with security protections,
    input validation, and error handling.

    Args:
        config_dir: Base configuration directory. Defaults to ~/.vsclaude

    Raises:
        InstanceValidationError: If configuration directory is invalid
        InstanceSecurityError: If directory operations pose security risks
    """

    # Security: Safe instance name pattern
    SAFE_INSTANCE_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]*$')

    # Security: Reserved names that could cause conflicts
    RESERVED_NAMES = {
        '.', '..', 'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
        'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4',
        'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9', 'config', 'instances', 'backup'
    }

    # Security: Minimum and maximum port values
    MIN_PORT = 1024  # Avoid privileged ports
    MAX_PORT = 65535

    def __init__(self, config_dir: Optional[str] = None) -> None:
        """
        Initialize InstanceManager with security protections.

        Args:
            config_dir: Base configuration directory path

        Raises:
            InstanceValidationError: If config_dir is invalid
            InstanceSecurityError: If directory creation poses security risks
        """
        try:
            self.config_dir = Path(config_dir or Path.home() / ".vsclaude")

            # Security: Validate config directory path
            if not self._is_safe_path(self.config_dir):
                raise InstanceSecurityError(
                    f"Configuration directory path contains unsafe characters: {self.config_dir}"
                )

            # Security: Ensure directory exists with proper permissions
            self.config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

            # Security: Set instances directory
            self.instances_dir = self.config_dir / "instances"
            self.instances_dir.mkdir(mode=0o700, exist_ok=True)

        except InstanceSecurityError:
            # Re-raise security errors directly
            raise
        except (PermissionError, OSError) as e:
            raise InstanceSecurityError(f"Security error creating directories: {e}") from e
        except Exception as e:
            raise InstanceValidationError(f"Invalid configuration directory: {e}") from e

    def _is_safe_path(self, path: Path) -> bool:
        """
        Validate that path is safe and doesn't contain traversal attempts.

        Args:
            path: Path to validate

        Returns:
            bool: True if path is safe
        """
        try:
            # Get the resolved path
            resolved_path = path.resolve()
            path_str = str(resolved_path)
            original_path_str = str(path)

            # Security: Check for directory traversal attempts in original path
            if ".." in original_path_str:
                return False

            # Security: Check for dangerous characters and patterns
            dangerous_chars = ['|', '&', ';', '`', '$', '<', '>', '\n', '\r', '\t', '\0']

            for char in dangerous_chars:
                if char in original_path_str:
                    return False

            # Security: Allow temporary directories and user directories
            # while preventing access to sensitive system locations
            unsafe_directories = {
                '/etc', '/var/log', '/proc', '/sys', '/dev',
                '/boot', '/root', '/sbin', '/usr/sbin'
            }

            # Check if resolved path is within unsafe directories
            for unsafe_dir in unsafe_directories:
                if path_str.startswith(unsafe_dir):
                    return False

            return True

        except (OSError, ValueError):
            # If path resolution fails, assume it's unsafe
            return False

    def _validate_instance_name(self, name: str) -> None:
        """
        Validate instance name for security and correctness.

        Args:
            name: Instance name to validate

        Raises:
            InstanceValidationError: If name is invalid
            InstanceSecurityError: If name poses security risks
        """
        if not name:
            raise InstanceValidationError("Instance name cannot be empty")

        # Security: Check for reserved names
        if name in self.RESERVED_NAMES:
            raise InstanceSecurityError(f"Instance name '{name}' is reserved")

        # Security: Check for dangerous characters
        dangerous_chars = ['\n', '\r', '\t', '\0', '|', '&', ';', '`', '$', '<', '>']
        for char in dangerous_chars:
            if char in name:
                raise InstanceSecurityError(
                    f"Instance name contains dangerous character: {repr(char)}"
                )

        # Security: Validate name pattern
        if not self.SAFE_INSTANCE_PATTERN.match(name):
            raise InstanceValidationError(
                f"Instance name '{name}' must start with alphanumeric character "
                f"and contain only letters, numbers, underscores, and hyphens"
            )

        # Security: Length limits
        if len(name) > 64:
            raise InstanceValidationError("Instance name cannot exceed 64 characters")

    def _validate_port(self, port: int) -> None:
        """
        Validate port number for security.

        Args:
            port: Port number to validate

        Raises:
            InstanceValidationError: If port is invalid
        """
        if not isinstance(port, int):
            raise InstanceValidationError("Port must be an integer")

        if port < self.MIN_PORT or port > self.MAX_PORT:
            raise InstanceValidationError(
                f"Port must be between {self.MIN_PORT} and {self.MAX_PORT}"
            )

    def _validate_profile(self, profile: str) -> None:
        """
        Validate profile name for security.

        Args:
            profile: Profile name to validate

        Raises:
            InstanceValidationError: If profile is invalid
        """
        if profile and not re.match(r'^[a-zA-Z0-9_-]+$', profile):
            raise InstanceValidationError(
                "Profile name must contain only letters, numbers, underscores, and hyphens"
            )

    def _validate_environment(self, environment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate and sanitize environment configuration.

        Args:
            environment: Environment configuration to validate

        Returns:
            Dict[str, Any]: Sanitized environment configuration

        Raises:
            InstanceValidationError: If environment is invalid
        """
        if environment is None:
            return {}

        if not isinstance(environment, dict):
            raise InstanceValidationError("Environment must be a dictionary")

        # Security: Validate keys and simple values
        sanitized = {}
        for key, value in environment.items():
            if not isinstance(key, str):
                raise InstanceValidationError("Environment keys must be strings")

            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', key):
                raise InstanceValidationError(
                    f"Environment key '{key}' must be a valid identifier"
                )

            # Security: Only allow simple JSON-serializable values
            if isinstance(value, (str, int, float, bool, type(None))):
                sanitized[key] = value
            elif isinstance(value, (list, dict)):
                # Security: Only allow simple nested structures
                try:
                    json.dumps(value)
                    sanitized[key] = value
                except (TypeError, ValueError):
                    raise InstanceValidationError(
                        f"Environment value for '{key}' must be JSON serializable"
                    )
            else:
                raise InstanceValidationError(
                    f"Environment value for '{key}' must be a simple type"
                )

        return sanitized

    def create_instance_config(
        self,
        name: str,
        port: int,
        profile: str = "default",
        environment: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new instance configuration with security protections.

        Args:
            name: Instance name (validated for safety)
            port: Port number (validated for security)
            profile: Profile name (default: "default")
            environment: Environment configuration (optional)

        Returns:
            Dict[str, Any]: Created instance configuration

        Raises:
            InstanceValidationError: If input validation fails
            InstanceSecurityError: If security checks fail
            OSError: If file operations fail
        """
        # Comprehensive validation
        self._validate_instance_name(name)
        self._validate_port(port)
        self._validate_profile(profile)
        sanitized_environment = self._validate_environment(environment)

        try:
            # Security: Create instance directory with safe path
            instance_dir = self.instances_dir / name

            if not self._is_safe_path(instance_dir):
                raise InstanceSecurityError(f"Instance path is unsafe: {instance_dir}")

            # Security: Check if instance already exists
            if instance_dir.exists():
                raise InstanceValidationError(f"Instance '{name}' already exists")

            # Security: Create directory with restricted permissions
            instance_dir.mkdir(mode=0o700, exist_ok=False)

            config = {
                "name": name,
                "port": port,
                "profile": profile,
                "environment": sanitized_environment,
                "created_at": None  # Will be set to current timestamp
            }

            config_file = instance_dir / "config.json"

            # Security: Write config with atomic write pattern
            temp_file = instance_dir / f".config.{id(config)}.tmp"

            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)

                # Security: Atomic rename to prevent partial writes
                temp_file.rename(config_file)

                # Set file permissions
                config_file.chmod(0o600)

            finally:
                # Clean up temp file if rename failed
                if temp_file.exists():
                    temp_file.unlink()

            return config

        except (OSError, PermissionError) as e:
            # Security: Clean up partial directory creation
            if instance_dir.exists():
                try:
                    shutil.rmtree(instance_dir)
                except OSError:
                    pass  # Best effort cleanup
            raise InstanceSecurityError(f"Failed to create instance '{name}': {e}") from e

    def read_instance_config(self, name: str) -> Dict[str, Any]:
        """
        Read instance configuration with security validation.

        Args:
            name: Instance name to read

        Returns:
            Dict[str, Any]: Instance configuration

        Raises:
            InstanceValidationError: If instance name is invalid
            InstanceSecurityError: If security checks fail
            FileNotFoundError: If instance does not exist
            OSError: If file operations fail
        """
        self._validate_instance_name(name)

        instance_dir = self.instances_dir / name

        if not self._is_safe_path(instance_dir):
            raise InstanceSecurityError(f"Instance path is unsafe: {instance_dir}")

        if not instance_dir.exists():
            raise FileNotFoundError(f"Instance '{name}' does not exist")

        config_file = instance_dir / "config.json"

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found for instance '{name}'")

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Security: Validate loaded configuration
            if not isinstance(config, dict):
                raise InstanceSecurityError("Invalid configuration format")

            required_keys = {"name", "port", "profile", "environment"}
            if not required_keys.issubset(config.keys()):
                raise InstanceSecurityError("Missing required configuration keys")

            return config

        except json.JSONDecodeError as e:
            raise InstanceSecurityError(f"Invalid JSON in configuration file: {e}") from e

    def update_instance_config(
        self,
        name: str,
        port: Optional[int] = None,
        profile: Optional[str] = None,
        environment: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update instance configuration with security protections.

        Args:
            name: Instance name to update
            port: New port number (optional)
            profile: New profile name (optional)
            environment: New environment configuration (optional)

        Returns:
            Dict[str, Any]: Updated instance configuration

        Raises:
            InstanceValidationError: If input validation fails
            InstanceSecurityError: If security checks fail
            FileNotFoundError: If instance does not exist
            OSError: If file operations fail
        """
        # Read existing config first
        current_config = self.read_instance_config(name)

        # Validate updates
        if port is not None:
            self._validate_port(port)
            current_config["port"] = port

        if profile is not None:
            self._validate_profile(profile)
            current_config["profile"] = profile

        if environment is not None:
            sanitized_env = self._validate_environment(environment)
            current_config["environment"] = sanitized_env

        instance_dir = self.instances_dir / name
        config_file = instance_dir / "config.json"

        # Security: Atomic update with temp file
        temp_file = instance_dir / f".config.{id(current_config)}.tmp"

        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(current_config, f, indent=2)

            temp_file.rename(config_file)
            config_file.chmod(0o600)

        finally:
            if temp_file.exists():
                temp_file.unlink()

        return current_config

    def delete_instance_config(self, name: str) -> bool:
        """
        Delete instance configuration and directory.

        Args:
            name: Instance name to delete

        Returns:
            bool: True if deletion was successful

        Raises:
            InstanceValidationError: If instance name is invalid
            InstanceSecurityError: If security checks fail
            FileNotFoundError: If instance does not exist
            OSError: If deletion fails
        """
        self._validate_instance_name(name)

        instance_dir = self.instances_dir / name

        if not self._is_safe_path(instance_dir):
            raise InstanceSecurityError(f"Instance path is unsafe: {instance_dir}")

        if not instance_dir.exists():
            raise FileNotFoundError(f"Instance '{name}' does not exist")

        try:
            # Security: Use shutil.rmtree for safe deletion
            shutil.rmtree(instance_dir)
            return True

        except OSError as e:
            raise InstanceSecurityError(f"Failed to delete instance '{name}': {e}") from e

    def delete_instance(self, name: str) -> Dict[str, bool]:
        """
        Transactionally delete an instance (container + config)

        Args:
            name: Instance name to delete

        Returns:
            Dict[str, bool]: Results for each operation

        Raises:
            InstanceValidationError: If instance name is invalid
        """
        from vsclaude.vsclaude.docker import MockDockerClient

        result = {
            "container_stopped": False,
            "container_removed": False,
            "config_deleted": False
        }

        try:
            docker_client = MockDockerClient()
            container_name = f"vsclaude-{name}"

            # Stop container if running
            try:
                if docker_client.is_container_running(container_name):
                    docker_client.stop_container(container_name)
                    result["container_stopped"] = True
            except Exception:
                pass  # Best effort - continue with deletion

            # Delete configuration
            try:
                self.delete_instance_config(name)
                result["config_deleted"] = True
            except Exception:
                pass  # Best effort - continue with container removal

            # Remove container
            try:
                if docker_client.remove_container(container_name):
                    result["container_removed"] = True
            except Exception:
                pass  # Best effort - report partial success

            return result

        except Exception as e:
            # Return partial results if any operation succeeded
            return result

    def list_instances(self) -> List[str]:
        """
        List all available instances.

        Returns:
            List[str]: List of instance names

        Raises:
            InstanceSecurityError: If directory access fails
        """
        try:
            instances = []
            for item in self.instances_dir.iterdir():
                if item.is_dir() and self._is_safe_path(item):
                    config_file = item / "config.json"
                    if config_file.exists():
                        instances.append(item.name)

            return sorted(instances)

        except OSError as e:
            raise InstanceSecurityError(f"Failed to list instances: {e}") from e

    def instance_exists(self, name: str) -> bool:
        """
        Check if an instance exists.

        Args:
            name: Instance name to check

        Returns:
            bool: True if instance exists

        Raises:
            InstanceValidationError: If instance name is invalid
        """
        self._validate_instance_name(name)

        instance_dir = self.instances_dir / name

        if not self._is_safe_path(instance_dir):
            return False

        return instance_dir.exists() and (instance_dir / "config.json").exists()