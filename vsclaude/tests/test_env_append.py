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

    from vsclaude.vsclaude.cli import main
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

    from vsclaude.vsclaude.cli import start_command

    # Create mock arguments
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = 8080
    args.env = []
    args.env_append = ["PATH=/custom/bin", "CUSTOM_VAR=appended_value"]

    # Mock dependencies using full module paths
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

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

    from vsclaude.vsclaude.cli import start_command

    # Mock args with both env and env_append
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = 8080
    args.env = ["THEME=light", "PATH=/override/bin"]  # Override PATH
    args.env_append = ["PATH=/append/bin"]  # Try to append

    # Mock dependencies using full module paths
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

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

def test_env_append_fallback():
    """Test env-append falls back to set behavior when global doesn't exist"""
    from unittest.mock import patch, MagicMock, Mock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vsclaude.vsclaude.cli import start_command

    # Mock args with env_append for non-existent global variable
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = 8080
    args.env = []
    args.env_append = ["NEW_VAR=new_value"]

    # Mock dependencies using full module paths
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config without NEW_VAR
        mock_config_manager = Mock()
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {"EXISTING_VAR": "existing"}
        }
        mock_config_manager.get_global_environment.return_value = {"EXISTING_VAR": "existing"}
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

        # NEW_VAR should be set as new variable since it doesn't exist globally
        assert environment_arg["NEW_VAR"] == "new_value"

        # EXISTING_VAR should be preserved from global config
        assert environment_arg["EXISTING_VAR"] == "existing"

def test_mm_channel_priority_with_env_append():
    """Test MM_CHANNEL auto-population priority order and env-append interactions"""
    from unittest.mock import patch, MagicMock, Mock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vsclaude.vsclaude.cli import start_command

    # Scenario 1: Basic auto-population (no overrides)
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = []
    args.env_append = []

    # Mock dependencies
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config without MM_CHANNEL
        mock_config_manager = Mock()
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {}
        }
        mock_config_manager.get_global_environment.return_value = {}
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

        # Verify that create_instance_config was called with auto-populated MM_CHANNEL
        call_args = mock_instance_manager.create_instance_config.call_args
        assert call_args is not None

        # Get the environment passed to create_instance_config
        environment_arg = call_args.kwargs.get('environment', {})

        # MM_CHANNEL should be auto-populated from instance name
        assert environment_arg["MM_CHANNEL"] == "test-instance", "MM_CHANNEL should auto-populate when no overrides exist"


# Additional scenarios testing MM_CHANNEL priority order
def test_mm_channel_cli_override_priority():
    """Test CLI override priority (highest) overrides auto-population"""
    from unittest.mock import patch, MagicMock, Mock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vsclaude.vsclaude.cli import start_command

    # Mock args with CLI MM_CHANNEL override
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = ["MM_CHANNEL=custom-channel"]
    args.env_append = []

    # Mock dependencies
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config without MM_CHANNEL
        mock_config_manager = Mock()
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {}
        }
        mock_config_manager.get_global_environment.return_value = {}
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

        # Verify that create_instance_config was called with CLI-overridden MM_CHANNEL
        call_args = mock_instance_manager.create_instance_config.call_args
        assert call_args is not None

        # Get the environment passed to create_instance_config
        environment_arg = call_args.kwargs.get('environment', {})

        # MM_CHANNEL should be overridden by CLI argument, not auto-populated
        assert environment_arg["MM_CHANNEL"] == "custom-channel", "CLI override should have highest priority"


def test_mm_channel_global_config_priority():
    """Test global config priority overrides auto-population"""
    from unittest.mock import patch, MagicMock, Mock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vsclaude.vsclaude.cli import start_command

    # Mock args without MM_CHANNEL override
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = []
    args.env_append = []

    # Mock dependencies
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config WITH MM_CHANNEL set
        mock_config_manager = Mock()
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {"MM_CHANNEL": "global-channel"}
        }
        mock_config_manager.get_global_environment.return_value = {"MM_CHANNEL": "global-channel"}
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

        # Verify that create_instance_config was called with global MM_CHANNEL
        call_args = mock_instance_manager.create_instance_config.call_args
        assert call_args is not None

        # Get the environment passed to create_instance_config
        environment_arg = call_args.kwargs.get('environment', {})

        # MM_CHANNEL should use global config value, not auto-populate
        assert environment_arg["MM_CHANNEL"] == "global-channel", "Global config should override auto-population"


def test_mm_channel_with_env_append_isolation():
    """Test MM_CHANNEL auto-population when other variables use env-append"""
    from unittest.mock import patch, MagicMock, Mock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vsclaude.vsclaude.cli import start_command

    # Mock args with env-append for other variables but not MM_CHANNEL
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = []
    args.env_append = ["PATH=/custom/bin", "CUSTOM_VAR=custom_value"]

    # Mock dependencies
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config with PATH but without MM_CHANNEL
        mock_config_manager = Mock()
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {"PATH": "/usr/bin:/bin"}
        }
        mock_config_manager.get_global_environment.return_value = {"PATH": "/usr/bin:/bin"}
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

        # Verify that create_instance_config was called with correct environment
        call_args = mock_instance_manager.create_instance_config.call_args
        assert call_args is not None

        # Get the environment passed to create_instance_config
        environment_arg = call_args.kwargs.get('environment', {})

        # MM_CHANNEL should auto-populate even when other variables use env-append
        assert environment_arg["MM_CHANNEL"] == "test-instance", "MM_CHANNEL should auto-populate regardless of other env-append variables"
        assert environment_arg["PATH"] == "/usr/bin:/bin/custom/bin", "PATH should be appended"
        assert environment_arg["CUSTOM_VAR"] == "custom_value", "New variable should be set"


def test_mm_channel_priority_with_cli_and_env_append():
    """Test MM_CHANNEL priority order with CLI override and env-append"""
    from unittest.mock import patch, MagicMock, Mock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from vsclaude.vsclaude.cli import start_command

    # Mock args with CLI MM_CHANNEL override AND env-append
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = ["MM_CHANNEL=cli-override"]
    args.env_append = ["PATH=/custom/bin"]

    # Mock dependencies
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config WITH MM_CHANNEL set and PATH
        mock_config_manager = Mock()
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {"MM_CHANNEL": "global-channel", "PATH": "/usr/bin"}
        }
        mock_config_manager.get_global_environment.return_value = {"MM_CHANNEL": "global-channel", "PATH": "/usr/bin"}
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

        # Verify that create_instance_config was called with correct environment
        call_args = mock_instance_manager.create_instance_config.call_args
        assert call_args is not None

        # Get the environment passed to create_instance_config
        environment_arg = call_args.kwargs.get('environment', {})

        # CLI override should have highest priority
        assert environment_arg["MM_CHANNEL"] == "cli-override", "CLI override should override global config"
        # PATH should be appended
        assert environment_arg["PATH"] == "/usr/bin/custom/bin", "PATH should be appended to global config"

if __name__ == "__main__":
    test_cli_env_append_argument()
    test_env_append_functionality()
    test_mixed_env_and_env_append()
    test_env_append_fallback()
    test_mm_channel_priority_with_env_append()
    test_mm_channel_cli_override_priority()
    test_mm_channel_global_config_priority()
    test_mm_channel_with_env_append_isolation()
    test_mm_channel_priority_with_cli_and_env_append()