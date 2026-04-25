#!/usr/bin/env python3

import os
import sys
import docker

# Add the build-env directory to the path
sys.path.insert(0, '/workspace/build-env')

from build_env import BuildEnvironmentManager, BuildEnvironmentError

def debug_build_env():
    """Debug the build-env tool step by step."""

    # Set environment variables
    os.environ['BUILD_CONTAINER'] = 'python:3.12-slim'
    os.environ['DEFAULT_WORKSPACE'] = '/workspace'

    print("=== Starting debug session ===")
    print(f"BUILD_CONTAINER: {os.environ['BUILD_CONTAINER']}")
    print(f"DEFAULT_WORKSPACE: {os.environ['DEFAULT_WORKSPACE']}")

    try:
        # Initialize manager
        manager = BuildEnvironmentManager()
        print("✓ Docker client initialized")

        # Validate requirements
        manager._validate_requirements(os.environ)
        print("✓ Requirements validated")

        # Try to start container
        print("Attempting to start container...")
        container_name = manager._start_container(
            os.environ["BUILD_CONTAINER"],
            os.environ["DEFAULT_WORKSPACE"],
            os.environ
        )
        print(f"✓ Container started: {container_name}")

        # Check if container is running
        if manager._container_running(container_name):
            print("✓ Container is running")
        else:
            print("✗ Container is not running")

        # Try to execute command
        print("Attempting to execute command...")
        exit_code, output = manager._execute_command(container_name, 'python --version', os.environ)
        print(f"✓ Command executed - exit code: {exit_code}")
        if output:
            if isinstance(output, bytes):
                output = output.decode('utf-8')
            print(f"Output: {output}")

    except Exception as e:
        print(f"✗ Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_build_env()