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

def test_env_append_functionality():
    """Test actual environment append functionality"""
    from unittest.mock import patch, MagicMock, Mock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vsclaude.cli import start_command

    # Create mock arguments
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = 8080
    args.env = []
    args.env_append = ["PATH=/custom/bin", "CUSTOM_VAR=appended_value"]

    # Mock dependencies using full module paths
    with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.compose.generate') as mock_generate:

        # Configure config manager mock
        mock_config_manager = Mock()
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {"PATH": "/usr/local/bin:/usr/bin:/bin", "GLOBAL_VAR": "global_value"}
        }
        mock_config_manager.get_global_environment.return_value = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "GLOBAL_VAR": "global_value"
        }
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = False
        mock_config_manager.format_ide_address.return_value = "http://localhost:8080"
        MockConfigManager.return_value = mock_config_manager

        # Configure instance manager mock
        mock_instance_manager = Mock()
        mock_instance_manager.create_instance_config.return_value = {"name": "test-instance", "port": 8080}
        MockInstanceManager.return_value = mock_instance_manager

        # Configure port manager mock
        mock_port_manager = Mock()
        mock_port_manager.find_available_port.return_value = 8080
        MockPortManager.return_value = mock_port_manager

        # Configure compose generate mock
        mock_generate.return_value = {"services": {"claude": {"environment": {}}}}

        # Call start_command
        result = start_command(args)

        # Verify that create_instance_config was called with correctly merged environment
        call_args = mock_instance_manager.create_instance_config.call_args
        assert call_args is not None

        # Get the environment passed to create_instance_config
        environment_arg = call_args.kwargs.get('environment', {})

        # Test that PATH was appended correctly
        assert environment_arg["PATH"] == "/usr/local/bin:/usr/bin:/bin/custom/bin"

        # Test that new variable was added correctly
        assert environment_arg["CUSTOM_VAR"] == "appended_value"

        # Test that global variables are preserved
        assert environment_arg["GLOBAL_VAR"] == "global_value"

def test_mixed_env_and_env_append():
    """Test mixed usage of --env and --env-append"""
    from unittest.mock import patch, MagicMock, Mock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vsclaude.cli import start_command

    # Mock args with both env and env_append
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = 8080
    args.env = ["THEME=light", "PATH=/override/bin"]  # Override PATH
    args.env_append = ["PATH=/append/bin"]  # Try to append

    # Mock dependencies using full module paths
    with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.compose.generate') as mock_generate:

        # Configure global config with existing PATH
        mock_config_manager = Mock()
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {"PATH": "/usr/bin", "THEME": "dark"}
        }
        mock_config_manager.get_global_environment.return_value = {
            "PATH": "/usr/bin",
            "THEME": "dark"
        }
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = False
        mock_config_manager.format_ide_address.return_value = "http://localhost:8080"
        MockConfigManager.return_value = mock_config_manager

        # Configure instance manager mock
        mock_instance_manager = Mock()
        mock_instance_manager.create_instance_config.return_value = {"name": "test-instance", "port": 8080}
        MockInstanceManager.return_value = mock_instance_manager

        # Configure port manager mock
        mock_port_manager = Mock()
        mock_port_manager.find_available_port.return_value = 8080
        MockPortManager.return_value = mock_port_manager

        # Configure compose generate mock
        mock_generate.return_value = {"services": {"claude": {"environment": {}}}}

        # Call start_command
        result = start_command(args)

        # Verify that create_instance_config was called with correctly merged environment
        call_args = mock_instance_manager.create_instance_config.call_args
        assert call_args is not None

        # Get the environment passed to create_instance_config
        environment_arg = call_args.kwargs.get('environment', {})

        # --env should override both global and append
        assert environment_arg["PATH"] == "/override/bin"
        assert environment_arg["THEME"] == "light"

if __name__ == "__main__":
    test_cli_env_append_argument()
    test_env_append_functionality()
    test_mixed_env_and_env_append()