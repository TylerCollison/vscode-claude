#!/usr/bin/env python3
"""
Security validation module for build-env tool.
Provides validation functions to ensure Docker container configurations are safe.
"""

import re


class SecurityValidation:
    """Validates Docker container configurations for security."""

    def validate_image_name(self, image_name: str) -> bool:
        """
        Validate that an image name is safe.

        Args:
            image_name: The Docker image name to validate

        Returns:
            bool: True if the image name is safe, False otherwise
        """
        if not image_name:
            return False

        # Reject path traversal attempts
        if ".." in image_name or image_name.startswith("/") or "://" in image_name:
            return False

        # Reject whitespace characters
        if any(c.isspace() for c in image_name):
            return False

        # Basic format validation (repo/image:tag)
        pattern = r'^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9][a-zA-Z0-9._-]*)?(:[a-zA-Z0-9._-]+)?$'
        return bool(re.match(pattern, image_name))

    def validate_command(self, command: list) -> bool:
        """
        Validate that a command is safe to execute.

        Args:
            command: The command list to validate

        Returns:
            bool: True if the command is safe, False otherwise
        """
        if not command:
            return False

        dangerous_patterns = [
            r'rm\s+-rf\s+/',  # Dangerous rm command
            r'dd\s+',  # Disk operations
            r'chmod\s+777',  # Permission changes
            r'\|\s*(sh|bash|zsh)',  # Pipe to shell
            r'wget.*\|',  # Download and pipe
            r'curl.*\|'  # Download and pipe
        ]

        cmd_str = ' '.join(command)
        for pattern in dangerous_patterns:
            if re.search(pattern, cmd_str):
                return False

        return True

    def validate_environment_variables(self, env_vars: dict) -> bool:
        """
        Validate that environment variables are safe.

        Args:
            env_vars: Dictionary of environment variables

        Returns:
            bool: True if environment variables are safe, False otherwise
        """
        dangerous_vars = {
            'LD_PRELOAD',  # Library injection
            'LD_LIBRARY_PATH',  # Library path manipulation
            'PYTHONPATH',  # Python module path manipulation
            'PYTHONSTARTUP',  # Python startup script
            'NODE_PATH',  # Node module path manipulation
            'NODE_OPTIONS',  # Node options injection
            'PERL5LIB',  # Perl module path manipulation
            'RUBYLIB',  # Ruby library path manipulation
            'GOPATH'  # Go path manipulation
        }

        for var_name in env_vars:
            if var_name.upper() in dangerous_vars:
                return False

        return True

    def validate_volumes(self, volumes: dict) -> bool:
        """
        Validate that volume mounts are safe.

        Args:
            volumes: Dictionary mapping container paths to host paths

        Returns:
            bool: True if volume mounts are safe, False otherwise
        """
        dangerous_paths = {
            '/etc',  # System configuration
            '/root',  # Root home directory
            '/proc',  # Process filesystem
            '/sys',  # System filesystem
            '/dev',  # Device files
            '/boot',  # Boot files
            '/var/log',  # System logs
            '/usr/bin',  # System binaries
            '/bin',  # System binaries
            '/sbin',  # System binaries
        }

        for container_path in volumes:
            if container_path in dangerous_paths:
                return False

        return True