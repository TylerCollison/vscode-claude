#!/usr/bin/env python3
"""Debug command execution environment"""

import subprocess

def debug_command_env():
    """Debug command execution environment"""

    print("=== Debugging Command Execution Environment ===")

    # Test 1: Simple command
    print("\nTest 1: Simple command")

    result = subprocess.run(['build-env', 'echo', 'hello'], capture_output=True, text=True)
    print(f"Simple command output: {result.stdout.strip()}")

    # Test 2: Check environment variables
    print("\nTest 2: Check environment variables")

    result = subprocess.run(['build-env', 'env'], capture_output=True, text=True)
    print(f"Environment variables:\n{result.stdout[:500]}...")

    # Test 3: Check current directory
    print("\nTest 3: Check current directory")

    result = subprocess.run(['build-env', 'pwd'], capture_output=True, text=True)
    print(f"Current directory: {result.stdout.strip()}")

    # Test 4: Create file in current directory
    print("\nTest 4: Create file in current directory")

    result = subprocess.run(['build-env', 'touch', 'test_current_dir.txt'], capture_output=True, text=True)
    print(f"Touch command exit code: {result.returncode}")

    # Check if file exists in container
    result = subprocess.run(['docker', 'exec', 'build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a',
                           'ls', '-la', '/workspace/test_current_dir.txt'], capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ File created in container workspace")
    else:
        print("✗ File NOT created in container workspace")

    # Check if file exists on host
    if subprocess.run(['ls', 'test_current_dir.txt'], capture_output=True).returncode == 0:
        print("✓ File synced back to host")
    else:
        print("✗ File NOT synced back to host")

    # Test 5: Create file with absolute path
    print("\nTest 5: Create file with absolute path")

    result = subprocess.run(['build-env', 'touch', '/workspace/test_abs_path.txt'], capture_output=True, text=True)
    print(f"Touch absolute path exit code: {result.returncode}")

    # Check if file exists in container
    result = subprocess.run(['docker', 'exec', 'build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a',
                           'ls', '-la', '/workspace/test_abs_path.txt'], capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ File created in container workspace (absolute path)")
    else:
        print("✗ File NOT created in container workspace (absolute path)")

if __name__ == "__main__":
    debug_command_env()