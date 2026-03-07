import argparse

def main():
    parser = argparse.ArgumentParser(description="VS Code + Claude Docker Management")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start a new instance")
    start_parser.add_argument("name", help="Instance name")
    start_parser.add_argument("--port-auto", action="store_true", help="Auto-allocate port")
    start_parser.add_argument("--port", type=int, help="Specific port number")

    args = parser.parse_args()

    if args.command == "start":
        print(f"Starting instance {args.name}")