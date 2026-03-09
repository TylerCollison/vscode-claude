import unittest
from unittest.mock import Mock, patch, MagicMock, mock_open
import sys
import os

# Mock docker before importing cli
sys.modules['docker'] = MagicMock()
sys.modules['docker.errors'] = MagicMock()

# Add the parent directory to Python path to import cli module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vsclaude.vsclaude.cli import start_command


class TestMMChannelAutoPopulation(unittest.TestCase):
    def test_mm_channel_auto_population_no_override(self):
        """Test MM_CHANNEL auto-population when no override exists"""
        # Mock args with instance name but no MM_CHANNEL override
        args = Mock()
        args.name = "test-instance"
        args.port_auto = False
        args.port = None
        args.env = []  # No MM_CHANNEL override
        args.env_append = []  # Add env_append attribute

        with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.vsclaude.compose.generate') as mock_generate:

            # Configure mocks
            mock_config = MagicMock()
            mock_config.load_global_config.return_value = {
                "port_range": {"min": 8080, "max": 9000}
            }
            mock_config.get_global_environment.return_value = {}  # No global MM_CHANNEL
            MockConfigManager.return_value = mock_config

            mock_port_manager = MagicMock()
            mock_port_manager.find_available_port.return_value = 8080
            MockPortManager.return_value = mock_port_manager

            mock_instance_manager = MagicMock()
            mock_instance_manager.create_instance_config.return_value = {
                "name": "test-instance", "port": 8080, "environment": {}
            }
            MockInstanceManager.return_value = mock_instance_manager

            # Call the function
            start_command(args)

            # Verify generate was called with auto-populated MM_CHANNEL
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args
            env_vars = call_args[0][2]

            self.assertIn("MM_CHANNEL", env_vars)
            self.assertEqual(env_vars["MM_CHANNEL"], "test-instance")  # Auto-populated from instance name


    def test_mm_channel_cli_override(self):
        """Test CLI --env flag override takes precedence over auto-population"""
        # Mock args with MM_CHANNEL override via CLI
        args = Mock()
        args.name = "test-instance"
        args.port_auto = False
        args.port = None
        args.env = ["MM_CHANNEL=custom-channel"]  # CLI override
        args.env_append = []

        with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.vsclaude.compose.generate') as mock_generate:

            # Configure mocks
            mock_config = MagicMock()
            mock_config.load_global_config.return_value = {
                "port_range": {"min": 8080, "max": 9000}
            }
            mock_config.get_global_environment.return_value = {}  # No global MM_CHANNEL
            MockConfigManager.return_value = mock_config

            mock_port_manager = MagicMock()
            mock_port_manager.find_available_port.return_value = 8080
            MockPortManager.return_value = mock_port_manager

            mock_instance_manager = MagicMock()
            mock_instance_manager.create_instance_config.return_value = {
                "name": "test-instance", "port": 8080, "environment": {}
            }
            MockInstanceManager.return_value = mock_instance_manager

            # Call the function
            start_command(args)

            # Verify generate was called with CLI override
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args
            env_vars = call_args[0][2]

            self.assertEqual(env_vars["MM_CHANNEL"], "custom-channel")  # CLI override respected


    def test_mm_channel_global_config_override(self):
        """Test global config MM_CHANNEL setting takes precedence over auto-population"""
        # Mock args with no CLI override
        args = Mock()
        args.name = "test-instance"
        args.port_auto = False
        args.port = None
        args.env = []  # No CLI override
        args.env_append = []

        with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.vsclaude.compose.generate') as mock_generate:

            # Configure mocks - global config has MM_CHANNEL set
            mock_config = MagicMock()
            mock_config.load_global_config.return_value = {
                "port_range": {"min": 8080, "max": 9000}
            }
            mock_config.get_global_environment.return_value = {
                "MM_CHANNEL": "global-channel"  # Global config has MM_CHANNEL
            }
            MockConfigManager.return_value = mock_config

            mock_port_manager = MagicMock()
            mock_port_manager.find_available_port.return_value = 8080
            MockPortManager.return_value = mock_port_manager

            mock_instance_manager = MagicMock()
            mock_instance_manager.create_instance_config.return_value = {
                "name": "test-instance", "port": 8080, "environment": {}
            }
            MockInstanceManager.return_value = mock_instance_manager

            # Call the function
            start_command(args)

            # Verify generate was called with global config value
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args
            env_vars = call_args[0][2]

            self.assertEqual(env_vars["MM_CHANNEL"], "global-channel")  # Global config respected


    def test_mm_channel_cli_overrides_global_config(self):
        """Test CLI --env flag override takes precedence over global config"""
        # Mock args with MM_CHANNEL override via CLI
        args = Mock()
        args.name = "test-instance"
        args.port_auto = False
        args.port = None
        args.env = ["MM_CHANNEL=cli-channel"]  # CLI override
        args.env_append = []

        with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.vsclaude.compose.generate') as mock_generate:

            # Configure mocks - global config also has MM_CHANNEL
            mock_config = MagicMock()
            mock_config.load_global_config.return_value = {
                "port_range": {"min": 8080, "max": 9000}
            }
            mock_config.get_global_environment.return_value = {
                "MM_CHANNEL": "global-channel"  # Global config has MM_CHANNEL
            }
            MockConfigManager.return_value = mock_config

            mock_port_manager = MagicMock()
            mock_port_manager.find_available_port.return_value = 8080
            MockPortManager.return_value = mock_port_manager

            mock_instance_manager = MagicMock()
            mock_instance_manager.create_instance_config.return_value = {
                "name": "test-instance", "port": 8080, "environment": {}
            }
            MockInstanceManager.return_value = mock_instance_manager

            # Call the function
            start_command(args)

            # Verify generate was called with CLI override (not global config)
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args
            env_vars = call_args[0][2]

            self.assertEqual(env_vars["MM_CHANNEL"], "cli-channel")  # CLI override respected over global config


if __name__ == '__main__':
    unittest.main()