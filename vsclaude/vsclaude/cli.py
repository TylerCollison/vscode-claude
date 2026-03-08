import argparse
import json
import docker.errors

def start_command(args):
    from vsclaude.config import ConfigManager
    from vsclaude.ports import PortManager
    from vsclaude.instances import InstanceManager
    from vsclaude.compose import generate

    config_manager = ConfigManager()
    global_config = config_manager.load_global_config()

    port_manager = PortManager(
        min_port=global_config["port_range"]["min"],
        max_port=global_config["port_range"]["max"]
    )

    if args.port_auto:
        port = port_manager.find_available_port()
    elif args.port:
        port = args.port
    else:
        port = global_config["port_range"]["min"]

    # Collect environment variables from command line
    environment_vars = {}
    if hasattr(args, 'env') and args.env:
        for env_var in args.env:
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                environment_vars[key] = value

    # Merge global environment with instance-specific environment
    global_environment = config_manager.get_global_environment()
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

    compose_config = generate(args.name, port, merged_environment)

    # Get IDE address using template
    ide_address = config_manager.format_ide_address(port)

    print(f"Instance '{args.name}' configured on port {port}")
    print(f"Access at: {ide_address}")

    return instance_config


def status_command(args):
    from vsclaude.instances import InstanceManager
    from vsclaude.docker import DockerClient
    from vsclaude.config import ConfigManager
    import json

    instance_manager = InstanceManager()
    docker_client = DockerClient()
    config_manager = ConfigManager()

    instances_dir = instance_manager.instances_dir

    if not instances_dir.exists():
        print("No instances configured")
        return

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
    from vsclaude.docker import DockerClient

    docker_client = DockerClient()
    container_name = f"vsclaude-{args.name}"

    try:
        container = docker_client.client.containers.get(container_name)
        container.stop()
        print(f"Stopped instance '{args.name}'")
    except docker.errors.NotFound:
        print(f"Instance '{args.name}' not found")


def main():
    parser = argparse.ArgumentParser(description="VS Code + Claude Docker Management")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start a new instance")
    start_parser.add_argument("name", help="Instance name")
    start_parser.add_argument("--port-auto", action="store_true", help="Auto-allocate port")
    start_parser.add_argument("--port", type=int, help="Specific port number")
    start_parser.add_argument("--env", action="append", help="Environment variable (key=value)")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show instance status")

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop an instance")
    stop_parser.add_argument("name", help="Instance name")

    args = parser.parse_args()

    if args.command == "start":
        start_command(args)
    elif args.command == "status":
        status_command(args)
    elif args.command == "stop":
        stop_command(args)
    else:
        parser.print_help()