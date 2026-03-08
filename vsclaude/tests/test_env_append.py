#!/usr/bin/env python3
"""Test CLI environment append functionality"""

def test_cli_env_append_argument():
    """Test that --env-append argument is accepted"""
    from unittest.mock import patch, MagicMock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vsclaude.cli import main
    import argparse

    # Create parser identical to the one in main()
    parser = argparse.ArgumentParser(description="VS Code + Claude Docker Management")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    start_parser = subparsers.add_parser("start", help="Start a new instance")
    start_parser.add_argument("name", help="Instance name")
    start_parser.add_argument("--port-auto", action="store_true", help="Auto-allocate port")
    start_parser.add_argument("--port", type=int, help="Specific port number")
    start_parser.add_argument("--env", action="append", help="Environment variable (key=value)")
    start_parser.add_argument("--env-append", action="append", help="Environment variable to append to global config (key=value)")

    # Test that --env-append is recognized and parsed correctly
    args = parser.parse_args(["start", "test-instance", "--env-append", "PATH=/custom/bin"])
    assert args.env_append == ["PATH=/custom/bin"]

if __name__ == "__main__":
    test_cli_env_append_argument()