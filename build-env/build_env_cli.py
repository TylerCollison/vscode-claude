#!/usr/bin/env python3

import argparse
import os
import sys
from typing import List

from build_env import BuildEnvironmentManager, BuildEnvironmentError


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Run commands in persistent build environment containers"
    )

    parser.add_argument(
        '--exit',
        action='store_true',
        help='Shutdown the build environment container'
    )

    # Remaining arguments are the command to execute
    parser.add_argument(
        'command',
        nargs=argparse.REMAINDER,
        help='Command to execute in the build environment'
    )

    args = parser.parse_args()

    # Get environment variables
    env_vars = dict(os.environ)

    try:
        manager = BuildEnvironmentManager()

        if args.exit:
            # Shutdown container
            workspace_path = os.environ.get('DEFAULT_WORKSPACE', os.getcwd())
            container_uuid = manager._get_container_uuid(workspace_path)
            container_name = f"build-env-{container_uuid}"
            manager._shutdown_container(container_name)
            print(f"Build environment container {container_name} shutdown")
            return 0

        # Validate requirements
        manager._validate_requirements(os.environ)

        # Get or create container
        container_name = manager._start_container(
            os.environ["BUILD_CONTAINER"],
            os.environ["DEFAULT_WORKSPACE"],
            os.environ
        )

        if args.command:
            # Execute command
            command = ' '.join(args.command)
            exit_code, output = manager._execute_command(container_name, command, os.environ)

            # Print output if there is any
            if output:
                # Docker exec_run returns bytes, decode to string
                if isinstance(output, bytes):
                    output = output.decode('utf-8')
                print(output.strip())

            return exit_code
        else:
            # No command provided, just ensure container is running
            print(f"Build environment container {container_name} is ready")
            return 0

    except BuildEnvironmentError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())