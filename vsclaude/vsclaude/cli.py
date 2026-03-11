import argparse
import json
import docker.errors
import sys

def start_command(args):
    """
    Start a new VS Code + Claude Docker instance.

    This command handles instance creation with optional custom Docker image support.
    Image handling flow:
    1. If --image flag is provided, parse and validate the image name
    2. If no --image flag, use default image from ConfigManager
    3. Validate image name format using _validate_image_name()
    4. Pass validated image parameters to compose generation

    Args:
        args: Command line arguments including:
            - name: Instance name
            - port: Port number
            - env/env_append: Environment variables
            - image: Custom Docker image (optional)
    """
    from .config import ConfigManager
    from .ports import PortManager
    from .instances import InstanceManager
    from .compose import generate, _validate_image_name

    config_manager = ConfigManager()
    global_config = config_manager.load_global_config()

    port_manager = PortManager(
        min_port=global_config["port_range"]["min"],
        max_port=global_config["port_range"]["max"]
    )

    if args.port:
        port = args.port
    else:
        port = port_manager.find_available_port()

    # Collect environment variables from command line
    environment_vars = {}
    if hasattr(args, 'env') and args.env:
        for env_var in args.env:
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                environment_vars[key] = value

    # Process --env-append variables
    append_environment_vars = {}
    if hasattr(args, 'env_append') and args.env_append:
        for env_var in args.env_append:
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                append_environment_vars[key] = value

    # Get global environment
    global_environment = config_manager.get_global_environment()

    # Apply append logic
    for key, append_value in append_environment_vars.items():
        if key in global_environment:
            # Append to existing global value
            global_environment[key] = global_environment[key] + append_value
        else:
            # Set as new variable if not in global config
            global_environment[key] = append_value

    # Then apply override logic (existing behavior)
    merged_environment = {**global_environment, **environment_vars}

    # Auto-populate MM_CHANNEL with instance name, respecting priority
    if 'MM_CHANNEL' not in environment_vars:  # Not overridden by user
        if 'MM_CHANNEL' not in global_environment:  # Not set globally
            merged_environment['MM_CHANNEL'] = args.name  # Auto-populate
        # Else: use global config value (already merged)

    instance_manager = InstanceManager()
    instance_config = instance_manager.create_instance_config(
        args.name, port, environment=merged_environment
    )

    # Get volume configuration from global config
    enabled_volumes = config_manager.get_enabled_volumes()
    include_docker_sock = config_manager.get_include_docker_sock()

    # Docker image handling: Support for custom images via --image flag
    # Priority: --image flag > ConfigManager default image
    image_name = None
    image_tag = None

    if args.image:
        # Parse custom image provided via --image flag
        # Expected format: "repository/image:tag" or "image:tag" or "image"
        if ':' in args.image:
            image_name, image_tag = args.image.rsplit(':', 1)
        else:
            image_name = args.image
            image_tag = "latest"

        # Validate the image name format before using it
        _validate_image_name(image_name)
    else:
        # Use default image from ConfigManager when --image flag is not provided
        default_image = config_manager.get_default_image()
        if ':' in default_image:
            image_name, image_tag = default_image.rsplit(':', 1)
        else:
            image_name = default_image
            image_tag = "latest"

    compose_config = generate(
        args.name,
        port,
        merged_environment,
        image_name=image_name if image_name else None,
        image_tag=image_tag if image_tag else "latest",
        enabled_volumes=enabled_volumes,
        include_docker_sock=include_docker_sock
    )

    # Start the container using Docker SDK
    from .docker import DockerClient

    docker_client = DockerClient()
    container_name = f"vsclaude-{args.name}"

    # NEW: Validate Docker network if specified in configuration
    docker_network = config_manager.get_docker_network()
    if docker_network:
        if not docker_client.network_exists(docker_network):
            print(f"Error: Docker network '{docker_network}' not found")
            print("Please create the network first or remove the 'docker_network' configuration")
            sys.exit(1)

    # Create container from compose configuration
    try:
        # Extract service configuration
        service_config = compose_config["services"]["vscode-claude"]

        # Create container
        container = docker_client.client.containers.create(
            image=service_config["image"],
            name=container_name,
            ports={service_config["ports"][0].split(":")[1]: service_config["ports"][0].split(":")[0]},
            environment={env.split("=", 1)[0]: env.split("=", 1)[1] for env in service_config["environment"]},
            volumes=service_config["volumes"],
            network=docker_network if docker_network else None,  # NEW: Pass network parameter
            detach=True
        )

        # Start container
        container.start()
        print(f"Container '{container_name}' started successfully")

    except Exception as e:
        print(f"Failed to start container: {e}")

    # Get IDE address using template
    ide_address = config_manager.format_ide_address(port)

    print(f"Instance '{args.name}' configured on port {port}")
    print(f"Access at: {ide_address}")

    return instance_config


def status_command(args):
    """
    Show status of all VS Code + Claude Docker instances.

    This command lists all configured instances, their running status,
    and IDE access URLs.

    Args:
        args: Command line arguments (no specific args needed)
    """
    from .instances import InstanceManager
    from .docker import DockerClient
    from .config import ConfigManager
    import json

    instance_manager = InstanceManager()
    docker_client = DockerClient()
    config_manager = ConfigManager()

    instances_dir = instance_manager.instances_dir

    if not instances_dir.exists():
        print("No instances configured")
        return

    # Iterate through all instance directories
    for instance_dir in instances_dir.iterdir():
        if instance_dir.is_dir():
            config_file = instance_dir / "config.json"
            if config_file.exists():
                with open(config_file) as f:
                    config = json.load(f)

                container_name = f"vsclaude-{config['name']}"
                status = "RUNNING" if docker_client.is_container_running(container_name) else "STOPPED"

                # Get IDE address using template
                ide_address = config_manager.format_ide_address(config['port'])
                print(f"{config['name']}: {status} - {ide_address}")


def stop_command(args):
    """
    Stop a running VS Code + Claude Docker instance.

    Args:
        args: Command line arguments including:
            - name: Instance name to stop
    """
    from .docker import DockerClient

    docker_client = DockerClient()
    container_name = f"vsclaude-{args.name}"

    try:
        container = docker_client.client.containers.get(container_name)
        container.stop()
        print(f"Stopped instance '{args.name}'")
    except docker.errors.NotFound:
        print(f"Instance '{args.name}' not found")


def delete_command(args):
    """
    Delete a VS Code + Claude Docker instance and its configuration.

    This command stops the container (if running), removes the container,
    and deletes the instance configuration.

    Args:
        args: Command line arguments including:
            - name: Instance name to delete
    """
    from .instances import InstanceManager

    instance_manager = InstanceManager()

    try:
        result = instance_manager.delete_instance(args.name)

        # Build status message
        messages = []
        if result["container_stopped"]:
            messages.append("stopped container")
        if result["container_removed"]:
            messages.append("removed container")
        if result["config_deleted"]:
            messages.append("deleted configuration")

        if messages:
            status = " and ".join(messages)
            print(f"Deleted instance '{args.name}': {status}")
        else:
            print(f"Instance '{args.name}' not found or already deleted")

    except Exception as e:
        print(f"Error deleting instance '{args.name}': {e}")


def main():
    """
    Main CLI entry point for VS Code + Claude Docker Management.

    This function handles command line argument parsing and dispatches
    to the appropriate command functions.

    Available commands:
    - start: Create and start a new instance
    - status: Show status of all instances
    - stop: Stop a running instance
    - delete: Delete an instance and its configuration
    """
    parser = argparse.ArgumentParser(description="VS Code + Claude Docker Management")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start a new instance")
    start_parser.add_argument("name", help="Instance name")
    start_parser.add_argument("--port", type=int, help="Specific port number")
    start_parser.add_argument("--env", action="append", help="Environment variable (key=value)")
    start_parser.add_argument("--env-append", action="append", help="Environment variable to append to global config (key=value)")
    start_parser.add_argument("--image", help="Custom Docker image name (e.g., 'custom-image:v1.0')")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show instance status")

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop an instance")
    stop_parser.add_argument("name", help="Instance name")

    # Delete command
    delete_parser = subparsers.add_parser("delete", help="Delete an instance (container and config)")
    delete_parser.add_argument("name", help="Instance name")

    args = parser.parse_args()

    # Dispatch to appropriate command function
    if args.command == "start":
        start_command(args)
    elif args.command == "status":
        status_command(args)
    elif args.command == "stop":
        stop_command(args)
    elif args.command == "delete":
        delete_command(args)
    else:
        # No valid command provided, show help
        parser.print_help()