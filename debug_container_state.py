#!/usr/bin/env python3

import os
import sys
import docker
import time

# Add the build-env directory to the path
sys.path.insert(0, '/workspace/build-env')

from build_env import BuildEnvironmentManager

def debug_container_state():
    """Debug container state changes."""

    # Set environment variables
    os.environ['BUILD_CONTAINER'] = 'python:3.12-slim'
    os.environ['DEFAULT_WORKSPACE'] = '/workspace'

    print("=== Debugging container state ===")

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

        # Get container and check initial state
        container = manager.docker_client.containers.get(container_name)
        print(f"✓ Container status after start: {container.status}")

        # Wait a moment and check again
        time.sleep(2)
        container = manager.docker_client.containers.get(container_name)
        print(f"✓ Container status after 2s: {container.status}")

        # Try to execute a simple command
        print("Attempting exec_run...")
        try:
            result = container.exec_run('python --version', detach=False)
            print(f"✓ exec_run completed - exit code: {result.exit_code}")
            if result.output:
                output = result.output.decode('utf-8') if isinstance(result.output, bytes) else result.output
                print(f"Output: {output}")
        except Exception as e:
            print(f"✗ exec_run failed: {e}")

        # Check container status after exec_run
        time.sleep(1)
        container = manager.docker_client.containers.get(container_name)
        print(f"✓ Container status after exec_run: {container.status}")

        # Check container logs
        print("Container logs:")
        logs = container.logs().decode('utf-8')
        print(logs)

    except Exception as e:
        print(f"✗ Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_container_state()