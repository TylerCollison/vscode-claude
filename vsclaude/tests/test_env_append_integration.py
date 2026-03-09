#!/usr/bin/env python3
"""Integration test for env-append feature"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

def test_env_append_integration():
    """Integration test for env-append feature"""
    import sys

    # Mock docker module before importing cli
    mock_docker_module = type('MockDocker', (), {})
    mock_docker_module.errors = type('MockDockerErrors', (), {})
    sys.modules['docker'] = mock_docker_module
    sys.modules['docker.errors'] = mock_docker_module.errors

    from vsclaude.vsclaude.cli import start_command

    # Create temporary global config
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".vsclaude"
        config_dir.mkdir()

        # Write global config with environment variables
        global_config = {
            "port_range": {"min": 8080, "max": 9000},
            "default_profile": "default",
            "ide_address_template": "http://{host}:{port}",
            "environment": {
                "PATH": "/usr/bin",
                "GLOBAL_VAR": "global_value"
            }
        }

        with open(config_dir / "global-config.json", "w") as f:
            json.dump(global_config, f)

        # Mock args
        args = Mock()
        args.name = "integration-test"
        args.port_auto = False
        args.port = 8080
        args.env = ["GLOBAL_VAR=overridden"]
        args.env_append = ["PATH=/custom/bin", "NEW_VAR=new_value"]

        # Mock dependencies that require actual operations
        with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.vsclaude.compose.generate') as mock_generate:

            # Configure mock to use our temp config
            mock_config = Mock()
            mock_config.config_dir = config_dir
            mock_config.load_global_config.return_value = global_config
            mock_config.get_global_environment.return_value = global_config["environment"]
            mock_config.get_enabled_volumes.return_value = []
            mock_config.get_include_docker_sock.return_value = False
            mock_config.format_ide_address.return_value = "http://localhost:8080"
            MockConfigManager.return_value = mock_config

            # Configure port manager mock
            mock_port_manager = Mock()
            MockPortManager.return_value = mock_port_manager

            # Configure instance manager mock
            mock_instance_manager = Mock()
            MockInstanceManager.return_value = mock_instance_manager

            # Call start_command
            start_command(args)

            # Verify correct environment merging
            mock_generate.assert_called_once()
            env_vars = mock_generate.call_args[0][2]

            # PATH should be appended
            assert env_vars["PATH"] == "/usr/bin/custom/bin"
            # GLOBAL_VAR should be overridden by --env
            assert env_vars["GLOBAL_VAR"] == "overridden"
            # NEW_VAR should be added as new variable
            assert env_vars["NEW_VAR"] == "new_value"
            # MM_CHANNEL should be auto-populated
            assert env_vars["MM_CHANNEL"] == "integration-test"

def test_env_append_fallback_integration():
    """Integration test for env-append fallback behavior"""
    import sys

    # Mock docker module before importing cli
    mock_docker_module = type('MockDocker', (), {})
    mock_docker_module.errors = type('MockDockerErrors', (), {})
    sys.modules['docker'] = mock_docker_module
    sys.modules['docker.errors'] = mock_docker_module.errors

    from vsclaude.vsclaude.cli import start_command

    # Create temporary global config
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".vsclaude"
        config_dir.mkdir()

        # Write global config WITHOUT the target variable
        global_config = {
            "port_range": {"min": 8080, "max": 9000},
            "default_profile": "default",
            "ide_address_template": "http://{host}:{port}",
            "environment": {
                "EXISTING_VAR": "existing_value"
            }
        }

        with open(config_dir / "global-config.json", "w") as f:
            json.dump(global_config, f)

        # Mock args
        args = Mock()
        args.name = "integration-test-fallback"
        args.port_auto = False
        args.port = 8080
        args.env = []
        args.env_append = ["NEW_VAR=fallback_value"]

        # Mock dependencies that require actual operations
        with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.vsclaude.compose.generate') as mock_generate:

            # Configure mock to use our temp config
            mock_config = Mock()
            mock_config.config_dir = config_dir
            mock_config.load_global_config.return_value = global_config
            mock_config.get_global_environment.return_value = global_config["environment"]
            mock_config.get_enabled_volumes.return_value = []
            mock_config.get_include_docker_sock.return_value = False
            mock_config.format_ide_address.return_value = "http://localhost:8080"
            MockConfigManager.return_value = mock_config

            # Configure port manager mock
            mock_port_manager = Mock()
            MockPortManager.return_value = mock_port_manager

            # Configure instance manager mock
            mock_instance_manager = Mock()
            MockInstanceManager.return_value = mock_instance_manager

            # Call start_command
            start_command(args)

            # Verify correct environment merging with fallback
            mock_generate.assert_called_once()
            env_vars = mock_generate.call_args[0][2]

            # EXISTING_VAR should be preserved
            assert env_vars["EXISTING_VAR"] == "existing_value"
            # NEW_VAR should be set as new variable (fallback)
            assert env_vars["NEW_VAR"] == "fallback_value"
            # MM_CHANNEL should be auto-populated
            assert env_vars["MM_CHANNEL"] == "integration-test-fallback"

def test_env_append_complex_scenario_integration():
    """Integration test for complex env-append scenarios"""
    import sys

    # Mock docker module before importing cli
    mock_docker_module = type('MockDocker', (), {})
    mock_docker_module.errors = type('MockDockerErrors', (), {})
    sys.modules['docker'] = mock_docker_module
    sys.modules['docker.errors'] = mock_docker_module.errors

    from vsclaude.vsclaude.cli import start_command

    # Create temporary global config
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".vsclaude"
        config_dir.mkdir()

        # Write global config with multiple environment variables
        global_config = {
            "port_range": {"min": 8080, "max": 9000},
            "default_profile": "default",
            "ide_address_template": "http://{host}:{port}",
            "environment": {
                "PATH": "/usr/bin:/bin",
                "LIBRARY_PATH": "/usr/lib",
                "DEFAULT_VAR": "default_value",
                "SHARED_VAR": "global_version"
            }
        }

        with open(config_dir / "global-config.json", "w") as f:
            json.dump(global_config, f)

        # Mock args with mixed scenarios
        args = Mock()
        args.name = "complex-integration-test"
        args.port_auto = False
        args.port = 8080
        args.env = ["SHARED_VAR=cli_version"]  # Override global
        args.env_append = [
            "PATH=/custom/bin:/more/bin",  # Append to existing
            "LIBRARY_PATH=/custom/lib",     # Append to existing
            "NEW_VAR=new_value",            # New variable fallback
            "DEFAULT_VAR=/appended"         # Append to existing that will be overridden
        ]

        # Mock dependencies that require actual operations
        with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.vsclaude.compose.generate') as mock_generate:

            # Configure mock to use our temp config
            mock_config = Mock()
            mock_config.config_dir = config_dir
            mock_config.load_global_config.return_value = global_config
            mock_config.get_global_environment.return_value = global_config["environment"]
            mock_config.get_enabled_volumes.return_value = []
            mock_config.get_include_docker_sock.return_value = False
            mock_config.format_ide_address.return_value = "http://localhost:8080"
            MockConfigManager.return_value = mock_config

            # Configure port manager mock
            mock_port_manager = Mock()
            MockPortManager.return_value = mock_port_manager

            # Configure instance manager mock
            mock_instance_manager = Mock()
            MockInstanceManager.return_value = mock_instance_manager

            # Call start_command
            start_command(args)

            # Verify correct environment merging
            mock_generate.assert_called_once()
            env_vars = mock_generate.call_args[0][2]

            # PATH should be appended correctly
            assert env_vars["PATH"] == "/usr/bin:/bin/custom/bin:/more/bin"
            # LIBRARY_PATH should be appended correctly
            assert env_vars["LIBRARY_PATH"] == "/usr/lib/custom/lib"
            # SHARED_VAR should be overridden by CLI (not appended)
            assert env_vars["SHARED_VAR"] == "cli_version"
            # NEW_VAR should be set as new variable
            assert env_vars["NEW_VAR"] == "new_value"
            # DEFAULT_VAR should be appended even though it's in global config
            # But since it wasn't overridden by --env, it should be appended
            assert env_vars["DEFAULT_VAR"] == "default_value/appended"
            # MM_CHANNEL should be auto-populated
            assert env_vars["MM_CHANNEL"] == "complex-integration-test"

if __name__ == "__main__":
    test_env_append_integration()
    test_env_append_fallback_integration()
    test_env_append_complex_scenario_integration()
    print("All integration tests passed!")