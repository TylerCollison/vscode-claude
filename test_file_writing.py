#!/usr/bin/env python3
"""Test different file writing approaches"""

import subprocess

def test_file_writing():
    """Test different file writing approaches"""

    print("=== Testing File Writing Approaches ===")

    # Clean up
    subprocess.run(['rm', '-f', 'test*.txt'], capture_output=True)

    # Test 1: Using touch (we know this works)
    print("\nTest 1: Using touch")

    result = subprocess.run(['build-env', 'touch', 'test_touch.txt'], capture_output=True, text=True)
    print(f"Touch exit code: {result.returncode}")

    # Check if file exists
    if subprocess.run(['ls', 'test_touch.txt'], capture_output=True).returncode == 0:
        print("✓ File created and synced")
    else:
        print("✗ File NOT created/synced")

    # Test 2: Using echo with shell redirection
    print("\nTest 2: Using echo with shell redirection")

    result = subprocess.run(['build-env', 'sh', '-c', 'echo "test content" > test_echo.txt'], capture_output=True, text=True)
    print(f"Echo redirection exit code: {result.returncode}")

    # Check if file exists
    if subprocess.run(['ls', 'test_echo.txt'], capture_output=True).returncode == 0:
        print("✓ File created and synced")
        result = subprocess.run(['cat', 'test_echo.txt'], capture_output=True, text=True)
        print(f"File content: {result.stdout.strip()}")
    else:
        print("✗ File NOT created/synced")

    # Test 3: Using printf instead of echo
    print("\nTest 3: Using printf")

    result = subprocess.run(['build-env', 'printf', '%s\\n', 'printf content'], capture_output=True, text=True)
    print(f"Printf exit code: {result.returncode}")
    print(f"Printf output: {result.stdout.strip()}")

    # Test 4: Using tee to write file
    print("\nTest 4: Using tee")

    result = subprocess.run(['build-env', 'sh', '-c', 'echo "tee content" | tee test_tee.txt'], capture_output=True, text=True)
    print(f"Tee exit code: {result.returncode}")

    # Check if file exists
    if subprocess.run(['ls', 'test_tee.txt'], capture_output=True).returncode == 0:
        print("✓ File created and synced")
        result = subprocess.run(['cat', 'test_tee.txt'], capture_output=True, text=True)
        print(f"File content: {result.stdout.strip()}")
    else:
        print("✗ File NOT created/synced")

    # Test 5: Using cat to write file
    print("\nTest 5: Using cat")

    result = subprocess.run(['build-env', 'sh', '-c', 'cat > test_cat.txt << EOF\ncat content\nEOF'], capture_output=True, text=True)
    print(f"Cat heredoc exit code: {result.returncode}")

    # Check if file exists
    if subprocess.run(['ls', 'test_cat.txt'], capture_output=True).returncode == 0:
        print("✓ File created and synced")
        result = subprocess.run(['cat', 'test_cat.txt'], capture_output=True, text=True)
        print(f"File content: {result.stdout.strip()}")
    else:
        print("✗ File NOT created/synced")

if __name__ == "__main__":
    test_file_writing()