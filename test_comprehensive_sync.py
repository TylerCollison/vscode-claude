#!/usr/bin/env python3
"""Comprehensive test of bidirectional sync fix"""

import os
import subprocess

def test_comprehensive_sync():
    """Test comprehensive bidirectional sync"""

    print("=== Comprehensive Bidirectional Sync Test ===")

    # Clean up any existing test files
    test_files = ['host_created.txt', 'container_created.txt', 'content_test.txt']
    for f in test_files:
        if os.path.exists(f):
            os.remove(f)

    # Test 1: Host → Container sync
    print("\nTest 1: Host → Container sync")

    # Create file on host
    with open('host_created.txt', 'w') as f:
        f.write("File created on host\n")

    print("✓ Created file on host")

    # Run command to trigger sync
    result = subprocess.run(['build-env', 'ls', 'host_created.txt'], capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ File successfully synced to container")
    else:
        print("✗ File NOT synced to container")
        return False

    # Test 2: Container → Host sync
    print("\nTest 2: Container → Host sync")

    # Create file in container
    result = subprocess.run(['build-env', 'touch', 'container_created.txt'], capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ File created in container")
    else:
        print("✗ Failed to create file in container")
        return False

    # Check if file exists on host
    if os.path.exists('container_created.txt'):
        print("✓ File successfully synced back to host")
    else:
        print("✗ File NOT synced back to host")
        return False

    # Test 3: Content modification sync
    print("\nTest 3: Content modification sync")

    # Create file with content on host
    with open('content_test.txt', 'w') as f:
        f.write("Original content from host\n")

    print("✓ Created content file on host")

    # Modify content in container
    result = subprocess.run(['build-env', 'sh', '-c', 'echo "Modified content in container" > content_test.txt'],
                          capture_output=True, text=True)

    if result.returncode == 0:
        print("✓ Modified content in container")
    else:
        print("✗ Failed to modify content in container")
        return False

    # Check if content was synced back
    if os.path.exists('content_test.txt'):
        with open('content_test.txt', 'r') as f:
            content = f.read().strip()
        if "Modified content in container" in content:
            print("✓ Content successfully synced back to host")
        else:
            print(f"✗ Content NOT synced back correctly. Got: {content}")
            return False
    else:
        print("✗ File not found after sync")
        return False

    # Test 4: Multiple files sync
    print("\nTest 4: Multiple files sync")

    # Create multiple files on host
    for i in range(3):
        with open(f'multi_file_{i}.txt', 'w') as f:
            f.write(f"Host file {i}\n")

    print("✓ Created multiple files on host")

    # Run command to trigger sync
    result = subprocess.run(['build-env', 'ls', 'multi_file_*.txt'], capture_output=True, text=True)

    if result.returncode == 0 and 'multi_file_' in result.stdout:
        print("✓ Multiple files synced to container")
    else:
        print("✗ Multiple files NOT synced to container")
        return False

    # Create multiple files in container
    for i in range(3, 6):
        result = subprocess.run(['build-env', 'sh', '-c', f'echo "Container file {i}" > multi_file_{i}.txt'],
                              capture_output=True, text=True)

    print("✓ Created multiple files in container")

    # Check if files exist on host
    all_synced = True
    for i in range(3, 6):
        if not os.path.exists(f'multi_file_{i}.txt'):
            print(f"✗ File multi_file_{i}.txt NOT synced back to host")
            all_synced = False

    if all_synced:
        print("✓ Multiple files synced back to host")
    else:
        return False

    print("\n=== All tests passed! Bidirectional sync is working correctly ===")
    return True

if __name__ == "__main__":
    test_comprehensive_sync()