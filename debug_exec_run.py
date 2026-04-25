#!/usr/bin/env python3

import os
import sys
import docker

# Add the build-env directory to the path
sys.path.insert(0, '/workspace/build-env')

from build_env import BuildEnvironmentManager
from security import filter_environment_variables

def debug_exec_run():
    """Debug the exec_run call specifically."""

    # Set environment variables
    os.environ['BUILD_CONTAINER'] = 'python:3.12-slim'
    os.environ['DEFAULT_WORKSPACE'] = '/workspace'

    print("=== Debugging exec_run ===")

    try:
        # Initialize manager
        manager = BuildEnvironmentManager()
        print("✓ Docker client initialized")

        # Start container
        container_name = manager._start_container(
            os.environ["BUILD_CONTAINER"],
            os.environ["DEFAULT_WORKSPACE"],
            os.environ
        )
        print(f"✓ Container started: {container_name}")

        # Get container
        container = manager.docker_client.containers.get(container_name)
        print(f"✓ Container status: {container.status}")

        # Test different exec_run parameters
        command = 'python --version'
        filtered_env_vars = filter_environment_variables(os.environ)

        print(f"Command: {command}")
        print(f"Filtered env vars: {filtered_env_vars}")

        # Test 1: Simple exec_run without tty/stdin
        print("\nTest 1: exec_run without tty/stdin")
        try:
            result = container.exec_run(
                command,
                detach=False,
                environment=filtered_env_vars,
                workdir="/workspace"
            )
            print(f"✓ Success - exit code: {result.exit_code}")
            if result.output:
                output = result.output.decode('utf-8') if isinstance(result.output, bytes) else result.output
                print(f"Output: {output}")
        except Exception as e:
            print(f"✗ Failed: {e}")

        # Test 2: With tty=True
        print("\nTest 2: exec_run with tty=True")
        try:
            result = container.exec_run(
                command,
                detach=False,
                environment=filtered_env_vars,
                workdir="/workspace",
                tty=True
            )
            print(f"✓ Success - exit code: {result.exit_code}")
            if result.output:
                output = result.output.decode('utf-8') if isinstance(result.output, bytes) else result.output
                print(f"Output: {output}")
        except Exception as e:
            print(f"✗ Failed: {e}")

        # Test 3: With stdin=True
        print("\nTest 3: exec_run with stdin=True")
        try:
            result = container.exec_run(
                command,
                detach=False,
                environment=filtered_env_vars,
                workdir="/workspace",
                stdin=True
            )
            print(f"✓ Success - exit code: {result.exit_code}")
            if result.output:
                output = result.output.decode('utf-8') if isinstance(result.output, bytes) else result.output
                print(f"Output: {output}")
        except Exception as e:
            print(f"✗ Failed: {e}")

        # Test 4: With both tty=True and stdin=True (current implementation)
        print("\nTest 4: exec_run with tty=True and stdin=True")
        try:
            result = container.exec_run(
                command,
                detach=False,
                environment=filtered_env_vars,
                workdir="/workspace",
                tty=True,
                stdin=True
            )
            print(f"✓ Success - exit code: {result.exit_code}")
            if result.output:
                output = result.output.decode('utf-8') if isinstance(result.output, bytes) else result.output
                print(f"Output: {output}")
        except Exception as e:
            print(f"✗ Failed: {e}")

    except Exception as e:
        print(f"✗ Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_exec_run()