import sys
from io import StringIO
from contextlib import redirect_stdout


def test_cli_start_help_does_not_contain_port_auto_flag():
    """Test that CLI start help output does not contain --port-auto flag after removal"""

    # The docker module is mocked by cconx/conftest.py before tests run.
    # Import the cli module via the cconx package
    import cconx.cconx.cli as cli_module

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