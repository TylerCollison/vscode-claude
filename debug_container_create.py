#!/usr/bin/env python3

import os
import sys
import docker
import time

# Add the build-env directory to the path
sys.path.insert(0, '/workspace/build-env')

from build_env import BuildEnvironmentManager

def debug_container_create():
    """Debug container creation process."""

    # Set environment variables
    os.environ['BUILD_CONTAINER'] = 'python:3.12-slim'
    os.environ['DEFAULT_WORKSPACE'] = '/workspace'

    print("=== Debugging container creation ===")

    try:
        # Initialize manager
        manager = BuildEnvironmentManager()
        print("✓ Docker client initialized")

        # Check the image
        image_name = os.environ["BUILD_CONTAINER"]
        print(f"Image: {image_name}")

        image = manager.docker_client.images.get(image_name)
        print(f"✓ Image found")
        print(f"Image config: {image.attrs['Config']}")

        # Create container manually to see what happens
        print("\nCreating container manually...")
        container = manager.docker_client.containers.create(
            image=image_name,
            name="test-container-debug",
            working_dir="/workspace",
            volumes={"/workspace": {"bind": "/workspace", "mode": "rw"}},
            detach=True
        )
        print(f"✓ Container created: {container.name}")

        # Start container
        print("Starting container...")
        container.start()

        # Check status immediately
        time.sleep(1)
        container = manager.docker_client.containers.get("test-container-debug")
        print(f"✓ Container status after start: {container.status}")

        # Check logs
        print("Container logs:")
        logs = container.logs().decode('utf-8')
        print(logs)

        # Try exec_run
        print("Attempting exec_run...")
        try:
            result = container.exec_run('python --version', detach=False)
            print(f"✓ exec_run completed - exit code: {result.exit_code}")
            if result.output:
                output = result.output.decode('utf-8') if isinstance(result.output, bytes) else result.output
                print(f"Output: {output}")
        except Exception as e:
            print(f"✗ exec_run failed: {e}")

        # Clean up
        container.stop()
        container.remove()
        print("✓ Cleaned up test container")

    except Exception as e:
        print(f"✗ Error occurred: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_container_create()