#!/usr/bin/env python3
"""Verify bidirectional sync fix"""

import os
import subprocess

def verify_bidirectional_sync():
    """Verify bidirectional sync works in both directions"""

    print("=== Verifying Bidirectional Sync Fix ===")

    # Test 1: Host → Container sync
    print("\nTest 1: Host → Container sync")

    # Create test file on host
    host_file = "host_to_container_test.txt"
    with open(host_file, 'w') as f:
        f.write("This file was created on the host\n")

    print(f"✓ Created {host_file} on host")

    # Run build-env command to trigger sync
    result = subprocess.run(['build-env', 'ls', host_file], capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ File successfully synced to container")
    else:
        print("✗ File NOT synced to container")
        return False

    # Test 2: Container → Host sync
    print("\nTest 2: Container → Host sync")

    # Create file in container
    container_file = "container_to_host_test.txt"
    result = subprocess.run(['build-env', 'touch', container_file], capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ File created in container")
    else:
        print("✗ Failed to create file in container")
        return False

    # Check if file exists on host
    if os.path.exists(container_file):
        print("✓ File successfully synced back to host")
    else:
        print("✗ File NOT synced back to host")
        return False

    # Test 3: Content sync
    print("\nTest 3: Content synchronization")

    # Create file with content on host
    content_file = "content_test.txt"
    with open(content_file, 'w') as f:
        f.write("Original content from host\n")

    print("✓ Created content file on host")

    # Modify content in container
    result = subprocess.run(['build-env', 'sh', '-c', f'echo "Modified content in container" > {content_file}'],
                          capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ Modified content in container")
    else:
        print("✗ Failed to modify content in container")
        return False

    # Check if content was synced back
    if os.path.exists(content_file):
        with open(content_file, 'r') as f:
            content = f.read().strip()
        if "Modified content in container" in content:
            print("✓ Content successfully synced back to host")
        else:
            print("✗ Content NOT synced back correctly")
            return False
    else:
        print("✗ File not found after sync")
        return False

    print("\n=== All tests passed! Bidirectional sync is working correctly ===")
    return True

if __name__ == "__main__":
    verify_bidirectional_sync()