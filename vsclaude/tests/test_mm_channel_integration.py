import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Mock docker before importing cli
sys.modules['docker'] = MagicMock()
sys.modules['docker.errors'] = MagicMock()

# Add the parent directory to Python path to import cli module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vsclaude.vsclaude.cli import start_command

class TestMMChannelIntegration(unittest.TestCase):
    def test_mm_channel_flows_to_compose_generation(self):
        """Test MM_CHANNEL flows correctly to Docker Compose generation"""
        args = MagicMock()
        args.name = "integration-test"
        args.port = 9090
        args.env = []

        with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.compose.generate') as mock_generate:

            mock_config_manager = MockConfigManager.return_value
            mock_config_manager.load_global_config.return_value = {
                "port_range": {"min": 8000, "max": 9000},
                "environment": {}
            }
            mock_config_manager.get_global_environment.return_value = {}
            mock_config_manager.format_ide_address.return_value = "http://localhost:9090"

            mock_port_manager = MockPortManager.return_value
            mock_port_manager.find_available_port.return_value = 9090

            mock_instance_manager = MockInstanceManager.return_value
            mock_instance_manager.create_instance_config.return_value = {
                "name": "integration-test", "port": 9090, "environment": {}
            }

            # Mock compose generation
            mock_generate.return_value = {
                "services": {
                    "vscode-claude": {
                        "environment": ["MM_CHANNEL=integration-test"]
                    }
                }
            }

            result = start_command(args)

            # Verify compose was called with correct MM_CHANNEL
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args
            environment_vars = call_args[0][2]
            self.assertIn('MM_CHANNEL', environment_vars)
            self.assertEqual(environment_vars['MM_CHANNEL'], 'integration-test')

    def test_priority_order_env_trumps_global_trumps_auto(self):
        """Test priority order: --env → global → auto-population"""
        # Test 1: --env flag should win
        args = MagicMock()
        args.name = "priority-test"
        args.port = 9091
        args.env = ["MM_CHANNEL=env-override"]

        with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.compose.generate') as mock_generate:

            mock_config_manager = MockConfigManager.return_value
            mock_config_manager.load_global_config.return_value = {
                "port_range": {"min": 8000, "max": 9000},
                "environment": {"MM_CHANNEL": "global-value"}
            }
            mock_config_manager.get_global_environment.return_value = {"MM_CHANNEL": "global-value"}
            mock_config_manager.format_ide_address.return_value = "http://localhost:9091"

            mock_port_manager = MockPortManager.return_value
            mock_port_manager.find_available_port.return_value = 9091

            mock_instance_manager = MockInstanceManager.return_value
            mock_instance_manager.create_instance_config.return_value = {
                "name": "priority-test", "port": 9091, "environment": {}
            }

            result = start_command(args)

            mock_generate.assert_called_once()
            environment_vars = mock_generate.call_args[0][2]
            self.assertEqual(environment_vars['MM_CHANNEL'], 'env-override')


if __name__ == '__main__':
    unittest.main()