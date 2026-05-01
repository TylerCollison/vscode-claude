#!/usr/bin/env python3
"""Debug content sync timing"""

import os
import subprocess

def debug_content_sync():
    """Debug content sync timing"""

    print("=== Debugging Content Sync ===")

    # Clean up
    if os.path.exists('debug_content.txt'):
        os.remove('debug_content.txt')

    # Step 1: Create file on host
    with open('debug_content.txt', 'w') as f:
        f.write("Step 1: Created on host\n")

    print("Step 1: Created file on host")

    # Step 2: Check container content before command
    result = subprocess.run(['docker', 'exec', 'build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a',
                           'cat', '/workspace/debug_content.txt'], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"Container content BEFORE command: {result.stdout.strip()}")
    else:
        print("File not found in container BEFORE command")

    # Step 3: Run command that modifies file
    print("\nStep 3: Running command that modifies file...")

    # First, let's see what happens with a simple echo
    result = subprocess.run(['build-env', 'sh', '-c', 'echo "Step 3: Modified in container" > debug_content.txt'],
                          capture_output=True, text=True)

    print(f"Command exit code: {result.returncode}")
    print(f"Command output: {result.stdout}")

    # Step 4: Check container content after command
    result = subprocess.run(['docker', 'exec', 'build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a',
                           'cat', '/workspace/debug_content.txt'], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"Container content AFTER command: {result.stdout.strip()}")
    else:
        print("File not found in container AFTER command")

    # Step 5: Check host content after sync
    if os.path.exists('debug_content.txt'):
        with open('debug_content.txt', 'r') as f:
            content = f.read().strip()
        print(f"Host content AFTER sync: {content}")
    else:
        print("File not found on host AFTER sync")

    # Step 6: Manual sync test
    print("\nStep 6: Manual sync test")

    # Manual container → host sync
    result = subprocess.run(['docker', 'cp', 'build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a:/workspace/debug_content.txt', '.'],
                          capture_output=True, text=True)

    print(f"Manual sync result: {result.returncode}")

    if os.path.exists('debug_content.txt'):
        with open('debug_content.txt', 'r') as f:
            content = f.read().strip()
        print(f"Host content AFTER manual sync: {content}")

    # Step 7: Test with different approach
    print("\nStep 7: Testing with different approach")

    # Create new file
    with open('debug2.txt', 'w') as f:
        f.write("Initial host content\n")

    # Run command that appends to file
    result = subprocess.run(['build-env', 'sh', '-c', 'echo "Appended in container" >> debug2.txt'],
                          capture_output=True, text=True)

    print(f"Append command exit code: {result.returncode}")

    if os.path.exists('debug2.txt'):
        with open('debug2.txt', 'r') as f:
            content = f.read()
        print(f"Host content after append: {repr(content)}")

if __name__ == "__main__":
    debug_content_sync()