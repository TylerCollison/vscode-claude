#!/usr/bin/env python3
"""
Security validation module for build-env tool.
Provides validation functions to ensure Docker container configurations are safe.
"""

import re
import uuid as uuid_lib
from typing import Dict, Set


class SecurityError(Exception):
    """Security validation error."""
    pass


# Safe environment variable whitelist
SAFE_ENV_VARS: Set[str] = {
    'PATH', 'HOME', 'USER', 'PWD', 'SHELL', 'TERM', 'LANG', 'LC_ALL',
    'BUILD_CONTAINER', 'DEFAULT_WORKSPACE', 'BUILD_*'
}

# Dangerous environment variable patterns
DANGEROUS_ENV_PATTERNS: Set[str] = {
    'DOCKER_*', '_*', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
    'GITHUB_TOKEN', 'API_KEY', 'SECRET', 'PASSWORD', 'TOKEN'
}

# Valid image name pattern
IMAGE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_.\-/:]*:[a-zA-Z0-9_.\-]+$')


def validate_image_name(image_name: str) -> bool:
    """Validate Docker image name for security.

    Args:
        image_name: Docker image name to validate

    Returns:
        True if image name is valid

    Raises:
        SecurityError: If image name is invalid or potentially dangerous
    """
    if not image_name or not isinstance(image_name, str):
        raise SecurityError("Image name must be a non-empty string")

    # Check for injection patterns
    injection_patterns = [';', '|', '&', '`', '$', '(', ')', '<', '>', '"', "'", '\\']
    for pattern in injection_patterns:
        if pattern in image_name:
            raise SecurityError(f"Image name contains dangerous pattern: {pattern}")

    # Check for path traversal
    if '..' in image_name or image_name.startswith('/'):
        raise SecurityError("Image name contains path traversal patterns")

    # Validate format
    if not IMAGE_NAME_PATTERN.match(image_name):
        raise SecurityError(
            f"Invalid image name format: {image_name}. "
            "Expected format: repository/image:tag"
        )

    return True

def validate_uuid(uuid_str: str) -> bool:
    """Validate UUID format.

    Args:
        uuid_str: UUID string to validate

    Returns:
        True if UUID is valid

    Raises:
        SecurityError: If UUID format is invalid
    """
    try:
        uuid_lib.UUID(uuid_str)
        return True
    except ValueError:
        raise SecurityError(f"Invalid UUID format: {uuid_str}")


def generate_container_uuid() -> str:
    """Generate cryptographically secure UUID for container naming.

    Returns:
        UUID string
    """
    return str(uuid_lib.uuid4())


def _matches_pattern(var_name: str, pattern: str) -> bool:
    """Check if a variable name matches a pattern (supports * wildcard at end)."""
    if pattern.endswith('*'):
        prefix = pattern[:-1]
        return var_name.startswith(prefix)
    return var_name == pattern


def filter_environment_variables(env_vars: Dict[str, str]) -> Dict[str, str]:
    """Filter environment variables to only allow safe ones.

    Uses a whitelist approach: only variables matching SAFE_ENV_VARS patterns
    are allowed, unless they also match DANGEROUS_ENV_PATTERNS (deny takes precedence).

    Args:
        env_vars: Dictionary of environment variables to filter

    Returns:
        Filtered dictionary containing only safe environment variables
    """
    filtered = {}

    for var_name, var_value in env_vars.items():
        # Check if explicitly dangerous (deny takes precedence)
        is_dangerous = any(
            _matches_pattern(var_name, pattern)
            for pattern in DANGEROUS_ENV_PATTERNS
        )
        if is_dangerous:
            continue

        # Check if explicitly safe (whitelist)
        is_safe = any(
            _matches_pattern(var_name, pattern)
            for pattern in SAFE_ENV_VARS
        )
        if is_safe:
            filtered[var_name] = var_value

    return filtered