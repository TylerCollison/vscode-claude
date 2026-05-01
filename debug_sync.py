#!/usr/bin/env python3
"""Debug script to understand bidirectional sync issues"""

import os
import sys
import subprocess
import tempfile

def debug_sync_algorithm():
    """Debug the sync algorithm step by step"""

    print("=== Debugging Bidirectional Sync ===")
    print("Current working directory:", os.getcwd())
    print("Files in workspace:", os.listdir('.'))

    # Check if we're in Docker-in-Docker
    docker_in_docker = os.path.exists('/.dockerenv') and os.path.exists('/var/run/docker.sock')
    print("Docker-in-Docker scenario:", docker_in_docker)

    # Check if container exists
    container_name = "build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a"

    try:
        result = subprocess.run(['docker', 'ps', '-f', f'name={container_name}'],
                             capture_output=True, text=True)
        print("Container status:", "Running" if container_name in result.stdout else "Not running")

        # Check files in container workspace
        result = subprocess.run(['docker', 'exec', container_name, 'ls', '-la', '/workspace'],
                              capture_output=True, text=True)
        print("Container workspace files:", result.stdout.strip())

    except Exception as e:
        print("Error checking container:", e)

    # Test the sync algorithm logic
    print("\n=== Testing Sync Logic ===")

    # Create test files
    test_files = ['test1.txt', 'test2.txt', 'test3.txt']
    for filename in test_files:
        with open(filename, 'w') as f:
            f.write(f"Host content for {filename}\n")

    print("Created test files:", test_files)

    # Try manual sync
    try:
        # Copy to container
        result = subprocess.run(['docker', 'cp', '.', f'{container_name}:/workspace'],
                              capture_output=True, text=True)
        print("Copy to container result:", result.returncode, result.stderr)

        # Check container files again
        result = subprocess.run(['docker', 'exec', container_name, 'ls', '-la', '/workspace'],
                              capture_output=True, text=True)
        print("Container files after sync:", result.stdout.strip())

        # Create file in container
        result = subprocess.run(['docker', 'exec', container_name, 'sh', '-c', 'echo "Container content" > /workspace/container_file.txt'],
                              capture_output=True, text=True)

        # Copy back from container
        result = subprocess.run(['docker', 'cp', f'{container_name}:/workspace/.', '.'],
                              capture_output=True, text=True)
        print("Copy from container result:", result.returncode, result.stderr)

        print("Host files after sync:", os.listdir('.'))

    except Exception as e:
        print("Error during manual sync:", e)

if __name__ == "__main__":
    debug_sync_algorithm()