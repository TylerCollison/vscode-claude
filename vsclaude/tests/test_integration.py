import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

def test_cli_with_global_environment():
    """Test CLI workflow with global environment settings"""
    from vsclaude.cli import start_command

    # Create a temporary directory for global config
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".vsclaude"
        config_dir.mkdir()

        # Create global config with environment variables
        global_config = {
            "port_range": {"min": 8080, "max": 9000},
            "default_profile": "default",
            "ide_address_template": "http://{host}:{port}",
            "environment": {
                "GLOBAL_VAR_1": "global_value_1",
                "GLOBAL_VAR_2": "global_value_2",
                "SHARED_SETTING": "global_setting"
            }
        }

        config_file = config_dir / "global-config.json"
        with open(config_file, 'w') as f:
            json.dump(global_config, f)

        # Mock args with NO instance-specific environment variables
        args = Mock()
        args.name = "test-instance"
        args.port_auto = False
        args.port = None
        args.env = []  # Empty list - no instance env vars
        args.env_append = []

        # Mock dependencies
        with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.compose.generate') as mock_generate:

            # Configure config manager mock to use our temp directory
            mock_config = MagicMock()
            mock_config.load_global_config.return_value = global_config
            mock_config.get_global_environment.return_value = global_config["environment"]
            mock_config.config_dir = config_dir
            mock_config.format_ide_address.return_value = f"http://localhost:8080"
            MockConfigManager.return_value = mock_config

            # Mock port manager
            mock_port_manager = MagicMock()
            mock_port_manager.find_available_port.return_value = 8080
            MockPortManager.return_value = mock_port_manager

            # Mock instance manager
            mock_instance_manager = MagicMock()
            MockInstanceManager.return_value = mock_instance_manager

            # Call the function
            result = start_command(args)

            # Verify generate was called with global environment
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args

            # Extract environment from call arguments
            env_vars = call_args[0][2]

            # Verify only global environment variables are present plus MM_CHANNEL auto-population
            assert env_vars["GLOBAL_VAR_1"] == "global_value_1"
            assert env_vars["GLOBAL_VAR_2"] == "global_value_2"
            assert env_vars["SHARED_SETTING"] == "global_setting"
            assert env_vars["MM_CHANNEL"] == "test-instance"  # Auto-populated from instance name
            assert len(env_vars) == 4  # Should have the 3 global variables + MM_CHANNEL


def test_cli_instance_overrides_global():
    """Test CLI instance environment overrides global settings"""
    from vsclaude.cli import start_command

    # Create a temporary directory for global config
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".vsclaude"
        config_dir.mkdir()

        # Create global config with environment variables
        global_config = {
            "port_range": {"min": 8080, "max": 9000},
            "default_profile": "default",
            "ide_address_template": "http://{host}:{port}",
            "environment": {
                "GLOBAL_VAR": "global_value",
                "SHARED_VAR": "global_version",
                "ANOTHER_GLOBAL": "global_only"
            }
        }

        config_file = config_dir / "global-config.json"
        with open(config_file, 'w') as f:
            json.dump(global_config, f)

        # Mock args with instance-specific environment variables that override global
        args = Mock()
        args.name = "test-instance"
        args.port_auto = False
        args.port = None
        args.env = ["SHARED_VAR=instance_version", "INSTANCE_ONLY=instance_value"]
        args.env_append = []

        # Mock dependencies
        with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.compose.generate') as mock_generate:

            # Configure config manager mock to use our temp directory
            mock_config = MagicMock()
            mock_config.load_global_config.return_value = global_config
            mock_config.get_global_environment.return_value = global_config["environment"]
            mock_config.config_dir = config_dir
            mock_config.format_ide_address.return_value = f"http://localhost:8080"
            MockConfigManager.return_value = mock_config

            # Mock port manager
            mock_port_manager = MagicMock()
            mock_port_manager.find_available_port.return_value = 8080
            MockPortManager.return_value = mock_port_manager

            # Mock instance manager
            mock_instance_manager = MagicMock()
            MockInstanceManager.return_value = mock_instance_manager

            # Call the function
            result = start_command(args)

            # Verify generate was called with merged environment
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args

            # Extract environment from call arguments
            env_vars = call_args[0][2]

            # Verify override behavior
            assert env_vars["GLOBAL_VAR"] == "global_value"  # Global-only variable remains
            assert env_vars["INSTANCE_ONLY"] == "instance_value"  # Instance-only variable added
            assert env_vars["SHARED_VAR"] == "instance_version"  # Instance overrides global
            assert env_vars["ANOTHER_GLOBAL"] == "global_only"  # Another global variable remains
            assert env_vars["MM_CHANNEL"] == "test-instance"  # Auto-populated from instance name
            assert len(env_vars) == 5  # Should have all variables + MM_CHANNEL


def test_cli_merges_global_and_instance_environments():
    """Test that CLI merges global environment with instance-specific environment"""
    from vsclaude.cli import start_command

    # Create a temporary directory for global config
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".vsclaude"
        config_dir.mkdir()

        # Create global config with environment variables
        global_config = {
            "port_range": {"min": 8080, "max": 9000},
            "default_profile": "default",
            "ide_address_template": "http://{host}:{port}",
            "environment": {
                "GLOBAL_VAR": "global_value",
                "SHARED_VAR": "global_version",
                "ANOTHER_GLOBAL": "global_only"
            }
        }

        config_file = config_dir / "global-config.json"
        with open(config_file, 'w') as f:
            json.dump(global_config, f)

        # Mock args with instance-specific environment variables
        args = Mock()
        args.name = "test-instance"
        args.port_auto = False
        args.port = None
        args.env = ["INSTANCE_VAR=instance_value", "SHARED_VAR=instance_version"]
        args.env_append = []

        # Mock dependencies
        with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.compose.generate') as mock_generate:

            # Configure config manager mock to use our temp directory
            mock_config = MagicMock()
            mock_config.load_global_config.return_value = global_config
            mock_config.get_global_environment.return_value = global_config["environment"]
            mock_config.config_dir = config_dir
            MockConfigManager.return_value = mock_config

            # Mock port manager
            mock_port_manager = MagicMock()
            mock_port_manager.find_available_port.return_value = 8080
            MockPortManager.return_value = mock_port_manager

            # Mock instance manager
            mock_instance_manager = MagicMock()
            MockInstanceManager.return_value = mock_instance_manager

            # Call the function
            start_command(args)

            # Verify generate was called with merged environment
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args

            # Extract environment from call arguments
            env_vars = call_args[0][2]

            # Verify merge behavior
            assert env_vars["GLOBAL_VAR"] == "global_value"  # Global-only variable
            assert env_vars["INSTANCE_VAR"] == "instance_value"  # Instance-only variable
            assert env_vars["SHARED_VAR"] == "instance_version"  # Instance overrides global
            assert env_vars["ANOTHER_GLOBAL"] == "global_only"  # Another global variable