import pytest
import sys
import os
from io import StringIO
from contextlib import redirect_stdout


def test_cli_start_help_does_not_contain_port_auto_flag():
    """Test that CLI start help output does not contain --port-auto flag after removal"""

    # Add cconx directory to Python path
    sys.path.insert(0, os.path.join(os.getcwd(), 'cconx'))

    # Mock docker first (as done in conftest.py)
    mock_docker_module = type('MockDocker', (), {})
    mock_docker_module.errors = type('MockDockerErrors', (), {})
    sys.modules['docker'] = mock_docker_module
    sys.modules['docker.errors'] = mock_docker_module.errors

    # Mock specific exception classes that are used in the code
    mock_docker_module.errors.NotFound = type('NotFound', (Exception,), {})
    mock_docker_module.errors.APIError = type('APIError', (Exception,), {})
    mock_docker_module.errors.DockerException = type('DockerException', (Exception,), {})

    # Try importing from the cli module directly
    import importlib
    cli_module = importlib.import_module('cli')

    # Capture help output
    captured_output = StringIO()

    # Mock sys.argv to simulate 'cconx start --help' command
    original_argv = sys.argv
    sys.argv = ['cconx', 'start', '--help']

    try:
        # Redirect stdout to capture help output
        with redirect_stdout(captured_output):
            # Call main function which should print help and exit
            try:
                cli_module.main()
            except SystemExit:
                # argparse help triggers SystemExit, which is expected
                pass

        # Get the captured help text
        help_text = captured_output.getvalue()

        # Verify that --port-auto flag is NOT present in the help output
        assert '--port-auto' not in help_text, "--port-auto flag should not appear in CLI help output"

        # Verify that other expected flags are still present
        assert '--port' in help_text, "--port flag should still be present"
        assert 'name' in help_text, "name argument should be present"

    finally:
        # Restore original sys.argv
        sys.argv = original_argv
        sys.path.remove(os.path.join(os.getcwd(), 'cconx'))