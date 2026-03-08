import argparse
import json

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

    instance_manager = InstanceManager()
    instance_config = instance_manager.create_instance_config(
        args.name, port, environment={}
    )

    compose_config = generate(args.name, port, {})

    print(f"Instance '{args.name}' configured on port {port}")
    print(f"Access at: http://localhost:{port}")

    return instance_config


def status_command(args):
    from vsclaude.instances import InstanceManager
    from vsclaude.docker import DockerClient
    import json

    instance_manager = InstanceManager()
    docker_client = DockerClient()

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
                print(f"{config['name']}: {status} - http://localhost:{config['port']}")


def main():
    parser = argparse.ArgumentParser(description="VS Code + Claude Docker Management")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start a new instance")
    start_parser.add_argument("name", help="Instance name")
    start_parser.add_argument("--port-auto", action="store_true", help="Auto-allocate port")
    start_parser.add_argument("--port", type=int, help="Specific port number")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show instance status")

    args = parser.parse_args()

    if args.command == "start":
        start_command(args)
    elif args.command == "status":
        status_command(args)
    else:
        parser.print_help()