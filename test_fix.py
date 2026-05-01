#!/usr/bin/env python3
"""Test fix for bidirectional sync"""

import os
import subprocess

def simple_bidirectional_sync(container_name: str, workspace_path: str) -> bool:
    """Simple bidirectional sync that actually works"""
    try:
        # Step 1: Copy host files to container
        result = subprocess.run(
            ['docker', 'cp', f'{workspace_path}/.', f'{container_name}:{workspace_path}'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Host→Container copy failed: {result.stderr}")
            return False

        # Step 2: Copy container files back to host
        result = subprocess.run(
            ['docker', 'cp', f'{container_name}:{workspace_path}/.', workspace_path],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Container→Host copy failed: {result.stderr}")
            return False

        return True
    except Exception as e:
        print(f"Sync error: {e}")
        return False

# Test the fix
if __name__ == "__main__":
    container_name = "build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a"
    workspace_path = "/workspace"

    print("Testing simple bidirectional sync...")

    # Create a test file
    test_file = "test_fix_file.txt"
    with open(test_file, 'w') as f:
        f.write("Test content from host\n")

    print(f"Created {test_file} on host")

    # Run sync
    success = simple_bidirectional_sync(container_name, workspace_path)

    if success:
        print("Sync completed successfully")

        # Check if file exists in container
        result = subprocess.run(
            ['docker', 'exec', container_name, 'cat', f'{workspace_path}/{test_file}'],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            print(f"File exists in container with content: {result.stdout.strip()}")
        else:
            print("File not found in container")

        # Create file in container
        result = subprocess.run(
            ['docker', 'exec', container_name, 'sh', '-c', f'echo "Container content" > {workspace_path}/container_test.txt'],
            capture_output=True, text=True
        )

        # Sync back
        simple_bidirectional_sync(container_name, workspace_path)

        # Check if container file exists on host
        if os.path.exists('container_test.txt'):
            with open('container_test.txt', 'r') as f:
                print(f"Container file synced to host: {f.read().strip()}")
        else:
            print("Container file not synced to host")
    else:
        print("Sync failed")