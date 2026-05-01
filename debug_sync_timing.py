#!/usr/bin/env python3
"""Debug sync timing and behavior"""

import os
import subprocess

def debug_sync_timing():
    """Debug sync timing and behavior"""

    print("=== Debugging Sync Timing ===")

    # Create initial file
    test_file = "sync_timing_test.txt"
    with open(test_file, 'w') as f:
        f.write("Initial host content\n")

    print(f"✓ Created {test_file} with initial content")

    # Check container content before sync
    result = subprocess.run(['docker', 'exec', 'build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a',
                           'cat', f'/workspace/{test_file}'], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"Container content BEFORE sync: {result.stdout.strip()}")
    else:
        print("File not found in container BEFORE sync")

    # Run build-env command that modifies file
    print("\nRunning build-env command...")
    result = subprocess.run(['build-env', 'sh', '-c', f'echo "Modified container content" > {test_file}'],
                          capture_output=True, text=True)

    print(f"Command exit code: {result.returncode}")
    print(f"Command output: {result.stdout}")

    # Check container content after sync
    result = subprocess.run(['docker', 'exec', 'build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a',
                           'cat', f'/workspace/{test_file}'], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"Container content AFTER sync: {result.stdout.strip()}")
    else:
        print("File not found in container AFTER sync")

    # Check host content after sync
    print(f"Host content AFTER sync: {open(test_file).read().strip()}")

    # Manual sync test
    print("\n=== Manual Sync Test ===")

    # Manual host → container sync
    result = subprocess.run(['docker', 'cp', f'{test_file}', 'build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a:/workspace/'],
                          capture_output=True, text=True)
    print(f"Manual host→container sync: {result.returncode}")

    # Manual container → host sync
    result = subprocess.run(['docker', 'cp', 'build-env-521b3ca0-0993-49ec-8f50-f0548a8c9f6a:/workspace/.', '.'],
                          capture_output=True, text=True)
    print(f"Manual container→host sync: {result.returncode}")

    print(f"Host content AFTER manual sync: {open(test_file).read().strip()}")

if __name__ == "__main__":
    debug_sync_timing()