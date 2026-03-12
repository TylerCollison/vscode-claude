from typing import Dict, Any, Optional, List
import re


def generate(
    instance_name: str,
    port: int,
    environment_vars: Optional[Dict[str, str]] = None,
    image_name: str = "tylercollison2089/vscode-claude",
    image_tag: str = "latest",
    container_port: int = 8443,
    additional_ports: Optional[List[str]] = None,
    restart_policy: str = "unless-stopped",
    include_docker_sock: bool = True,
    enabled_volumes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Generate Docker Compose configuration for ClaudeConX instance.

    Args:
        instance_name: Unique identifier for the instance (alphanumeric, hyphens, underscores)
        port: Host port to bind the container to (must be a valid port number 1-65535)
        environment_vars: Optional dictionary of environment variables to set
        image_name: Docker image name (default: "tylercollison2089/vscode-claude")
        image_tag: Docker image tag (default: "latest")
        container_port: Container port to expose (default: 8443)
        additional_ports: Optional list of additional port mappings
        restart_policy: Container restart policy (default: "unless-stopped")
        include_docker_sock: Whether to mount Docker socket (default: True)
        enabled_volumes: Optional list of container volume paths to mount (default: None)

    Returns:
        Dictionary containing the Docker Compose configuration

    Raises:
        ValueError: If input parameters are invalid
    """
    # Input validation
    _validate_instance_name(instance_name)
    _validate_port(port)
    _validate_port(container_port)
    _validate_restart_policy(restart_policy)
    _validate_image_name(image_name)

    # Normalize inputs
    environment_vars = environment_vars or {}
    additional_ports = additional_ports or []

    # Build environment variables
    environment = {
        "IDE_ADDRESS": f"http://localhost:{port}",
        "CCR_PROFILE": "default"  # Default, can be overridden
    }
    environment.update(environment_vars)

    # Build port mappings
    ports = [f"{port}:{container_port}"]
    ports.extend(additional_ports)

    # Build volumes dynamically
    volumes = []
    if enabled_volumes is None:
        enabled_volumes = ["/config", "/workspace"]  # Default volumes for backward compatibility

    for volume_path in enabled_volumes:
        volume_name = f"{instance_name}-{volume_path.split('/')[-1]}"
        volumes.append(f"{volume_name}:{volume_path}")

    if include_docker_sock:
        volumes.insert(0, "/var/run/docker.sock:/var/run/docker.sock")

    # Build volume definitions
    volume_definitions = {}
    for volume_path in enabled_volumes:
        volume_name = f"{instance_name}-{volume_path.split('/')[-1]}"
        volume_definitions[volume_name] = {}

    # Build image string
    image_str = f"{image_name}:{image_tag}" if image_tag else image_name

    compose_config = {
        "services": {
            "vscode-claude": {
                "image": image_str,
                "container_name": f"cconx-{instance_name}",
                "ports": ports,
                "environment": [f"{k}={v}" for k, v in environment.items()],
                "volumes": volumes,
                "restart": restart_policy
            }
        },
        "volumes": volume_definitions
    }

    return compose_config


def _validate_instance_name(name: str) -> None:
    """Validate instance name format."""
    if not isinstance(name, str):
        raise ValueError(f"instance_name must be a string, got {type(name)}")

    if not name:
        raise ValueError("instance_name cannot be empty")

    # Allow alphanumeric, hyphens, underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise ValueError("instance_name can only contain alphanumeric characters, hyphens, and underscores")

    # Avoid names that could cause volume conflicts
    if name.startswith("-") or name.endswith("-"):
        raise ValueError("instance_name cannot start or end with a hyphen")


def _validate_port(port: int) -> None:
    """Validate port number."""
    if not isinstance(port, int):
        raise ValueError(f"port must be an integer, got {type(port)}")

    if port < 1 or port > 65535:
        raise ValueError(f"port must be between 1 and 65535, got {port}")


def _validate_restart_policy(policy: str) -> None:
    """Validate restart policy."""
    valid_policies = {"no", "always", "on-failure", "unless-stopped"}
    if policy not in valid_policies:
        raise ValueError(f"restart_policy must be one of {sorted(valid_policies)}, got '{policy}'")


def _validate_image_name(image_name: str) -> None:
    """Validate Docker image name format."""
    if not isinstance(image_name, str):
        raise ValueError(f"image_name must be a string, got {type(image_name)}")

    if not image_name:
        raise ValueError("image_name cannot be empty")

    # Docker image name validation rules:
    # - Can contain lowercase letters, digits, hyphens, underscores, dots, and slashes
    # - Must start and end with alphanumeric characters or underscores
    # - Can include registry prefix (registry/namespace/image)
    # - Cannot contain uppercase letters
    # - Maximum length is 255 characters

    if len(image_name) > 255:
        raise ValueError("image_name cannot exceed 255 characters")

    # Check for uppercase letters
    if any(c.isupper() for c in image_name):
        raise ValueError("image_name cannot contain uppercase letters")

    # Valid characters: lowercase letters, digits, hyphens, underscores, dots, slashes
    pattern = r'^[a-z0-9._/-]+$'
    if not re.match(pattern, image_name):
        raise ValueError("image_name can only contain lowercase letters, digits, hyphens, underscores, dots, and slashes")

    # Check for valid start and end characters
    if image_name[0] in './-':
        raise ValueError("image_name cannot start with '.', '/', or '-'")
    if image_name[-1] in './-':
        raise ValueError("image_name cannot end with '.', '/', or '-'")

    # Validate registry format if present
    if '/' in image_name:
        parts = image_name.split('/')
        if len(parts) > 3:
            raise ValueError("image_name with registry cannot have more than 3 components (registry/namespace/image)")

        # Check each part
        for part in parts:
            if not part:
                raise ValueError("image_name components cannot be empty")
            if part.startswith('-') or part.endswith('-'):
                raise ValueError("image_name components cannot start or end with hyphens")
            if not re.match(r'^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$', part):
                raise ValueError("image_name components must start and end with alphanumeric characters")

    # Check for consecutive special characters
    if re.search(r'[./-]{2,}', image_name):
        raise ValueError("image_name cannot contain consecutive '.', '/', or '-' characters")