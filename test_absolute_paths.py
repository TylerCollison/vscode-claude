#!/usr/bin/env python3
"""Test with absolute paths"""

import os
import subprocess

def test_absolute_paths():
    """Test sync with absolute paths"""

    print("=== Testing with Absolute Paths ===")

    # Clean up
    if os.path.exists('abs_test.txt'):
        os.remove('abs_test.txt')

    # Test 1: Create file with absolute path in container
    print("\nTest 1: Create file with absolute path")

    result = subprocess.run(['build-env', 'sh', '-c', 'echo "Created in container" > /workspace/abs_test.txt'],
                          capture_output=True, text=True)

    print(f"Command exit code: {result.returncode}")

    # Check if file exists on host
    if os.path.exists('abs_test.txt'):
        with open('abs_test.txt', 'r') as f:
            content = f.read().strip()
        print(f"✓ File synced back to host: {content}")
    else:
        print("✗ File NOT synced back to host")

    # Test 2: Modify file with absolute path
    print("\nTest 2: Modify file with absolute path")

    # Create file on host first
    with open('abs_test2.txt', 'w') as f:
        f.write("Initial host content\n")

    print("✓ Created file on host")

    # Modify in container with absolute path
    result = subprocess.run(['build-env', 'sh', '-c', 'echo "Modified in container" > /workspace/abs_test2.txt'],
                          capture_output=True, text=True)

    print(f"Modify command exit code: {result.returncode}")

    # Check host content
    if os.path.exists('abs_test2.txt'):
        with open('abs_test2.txt', 'r') as f:
            content = f.read().strip()
        print(f"Host content after modify: {content}")
        if "Modified in container" in content:
            print("✓ Content successfully synced back")
        else:
            print("✗ Content NOT synced back")

    # Test 3: Check container working directory
    print("\nTest 3: Check container working directory")

    result = subprocess.run(['build-env', 'pwd'], capture_output=True, text=True)
    print(f"Container pwd: {result.stdout.strip()}")

    result = subprocess.run(['build-env', 'ls', '-la', '/workspace'], capture_output=True, text=True)
    print(f"Container /workspace contents: {result.stdout[:200]}...")

if __name__ == "__main__":
    test_absolute_paths()