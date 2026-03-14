def test_cli_includes_volume_config():
    """Test that CLI uses volume config from global settings"""
    from unittest.mock import patch, MagicMock
    import sys

    # Mock docker module to avoid import errors
    sys.modules['docker'] = MagicMock()
    sys.modules['docker.errors'] = MagicMock()

    # Add parent directory to Python path
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from cconx.cconx.cli import start_command

    # Mock the config to return custom volumes
    with patch('cconx.cconx.cconx.config.ConfigManager') as MockConfigManager:
        mock_manager = MockConfigManager.return_value
        mock_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "enabled_volumes": ["/config", "/workspace"],
            "include_docker_sock": False
        }
        mock_manager.get_enabled_volumes.return_value = ["/config", "/workspace"]
        mock_manager.get_include_docker_sock.return_value = False
        mock_manager.get_global_environment.return_value = {}
        mock_manager.format_ide_address.return_value = "http://localhost:8443"

        # Test that generate is called with correct volume parameters
        with patch('cconx.cconx.cconx.compose.generate') as mock_generate:
            with patch('cconx.cconx.cconx.instances.InstanceManager') as MockInstanceManager:
                mock_instance_manager = MockInstanceManager.return_value
                mock_instance_manager.create_instance_config.return_value = {}

                # Mock command line args
                class MockArgs:
                    name = "test-instance"
                    port = 8443
                    env = []

                start_command(MockArgs())

                # Verify generate was called with volume parameters
                mock_generate.assert_called_once()
                call_kwargs = mock_generate.call_args[1]
                assert call_kwargs["enabled_volumes"] == ["/config", "/workspace"]
                assert call_kwargs["include_docker_sock"] == False