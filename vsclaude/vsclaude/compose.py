from typing import Dict, Any, Optional, List
import re


def generate(
    instance_name: str,
    port: int,
    environment_vars: Optional[Dict[str, str]] = None,
    image_tag: str = "latest",
    container_port: int = 8443,
    additional_ports: Optional[List[str]] = None,
    restart_policy: str = "unless-stopped",
    include_docker_sock: bool = True
) -> Dict[str, Any]:
    """
    Generate Docker Compose configuration for VSClaude instance.

    Args:
        instance_name: Unique identifier for the instance (alphanumeric, hyphens, underscores)
        port: Host port to bind the container to (must be a valid port number 1-65535)
        environment_vars: Optional dictionary of environment variables to set
        image_tag: Docker image tag (default: "latest")
        container_port: Container port to expose (default: 8443)
        additional_ports: Optional list of additional port mappings
        restart_policy: Container restart policy (default: "unless-stopped")
        include_docker_sock: Whether to mount Docker socket (default: True)

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

    # Normalize inputs
    environment_vars = environment_vars or {}
    additional_ports = additional_ports or []

    # Build environment variables
    environment = {
        "IDE_ADDRESS": f"http://localhost:{port}",
        "PASSWORD": "password",  # Default, can be overridden
        "CCR_PROFILE": "default"  # Default, can be overridden
    }
    environment.update(environment_vars)

    # Build port mappings
    ports = [f"{port}:{container_port}"]
    ports.extend(additional_ports)

    # Build volumes
    volumes = [
        f"{instance_name}-config:/config",
        f"{instance_name}-workspace:/workspace"
    ]
    if include_docker_sock:
        volumes.insert(0, "/var/run/docker.sock:/var/run/docker.sock")

    compose_config = {
        "services": {
            "vscode-claude": {
                "image": f"tylercollison2089/vscode-claude:{image_tag}",
                "container_name": f"vsclaude-{instance_name}",
                "ports": ports,
                "environment": [f"{k}={v}" for k, v in environment.items()],
                "volumes": volumes,
                "restart": restart_policy
            }
        },
        "volumes": {
            f"{instance_name}-config": {},
            f"{instance_name}-workspace": {}
        }
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