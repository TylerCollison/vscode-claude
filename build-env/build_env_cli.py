#!/usr/bin/env python3

import argparse
import os
import sys
from typing import List, Optional, Dict, List as ListType, Tuple

from build_env import BuildEnvironmentManager, BuildEnvironmentError, parse_port_mappings


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

    parser.add_argument(
        '--ports',
        type=str,
        help='Port mappings in format "8000:8000,3000:3000" (container_port:host_port). '
             'Can also be set via BUILD_PORTS environment variable.'
    )

    # Remaining arguments are the command to execute
    parser.add_argument(
        'command',
        nargs=argparse.REMAINDER,
        help='Command to execute in the build environment'
    )

    args = parser.parse_args()

    # Get environment variables and convert to regular dict to avoid Docker SDK issues
    env_vars = dict(os.environ)

    # Parse port mappings from CLI argument or environment variable
    port_spec = args.ports or os.environ.get('BUILD_PORTS', '')
    port_mappings = parse_port_mappings(port_spec) if port_spec else None

    try:
        manager = BuildEnvironmentManager()

        if args.exit:
            # Shutdown container using stored UUID
            workspace_path = os.environ.get('DEFAULT_WORKSPACE', os.getcwd())
            container_uuid = manager._get_stored_container_uuid(workspace_path)

            if container_uuid is None:
                print("Error: No build environment container found for this workspace", file=sys.stderr)
                return 1

            container_name = f"build-env-{container_uuid}"
            manager._shutdown_container(container_name)
            print(f"Build environment container {container_name} shutdown")
            return 0

        # Validate requirements
        manager._validate_requirements(env_vars)

        # Get or create container
        container_name = manager._start_container(
            env_vars["BUILD_CONTAINER"],
            env_vars["DEFAULT_WORKSPACE"],
            env_vars,
            port_mappings
        )

        if port_mappings and port_mappings.get('ports'):
            port_strs = []
            for container_port, host_port in port_mappings['ports']:
                if host_port:
                    port_strs.append(f"{container_port}:{host_port}")
                else:
                    port_strs.append(container_port)
            print(f"Published ports: {', '.join(port_strs)}")

        if args.command:
            # Execute command
            command = ' '.join(args.command)
            exit_code, output = manager._execute_command(container_name, command, env_vars)

            # Print output if there is any
            if output:
                # Docker exec_run returns bytes, decode to string with error handling
                if isinstance(output, bytes):
                    output = output.decode('utf-8', errors='replace')
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