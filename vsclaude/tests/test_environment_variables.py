def test_environment_variable_passthrough():
    """Test that any environment variable is passed through"""
    from vsclaude.compose import generate
    environment_vars = {
        "PASSWORD": "mypassword",
        "CCR_PROFILE": "custom",
        "CUSTOM_VAR": "custom_value",
        "UNKNOWN_VAR": "unknown_value"
    }
    config = generate("test", 8443, environment_vars)
    service_env = config["services"]["vscode-claude"]["environment"]

    # Check that all variables are present
    env_dict = {item.split('=')[0]: item.split('=')[1] for item in service_env}
    assert "CUSTOM_VAR" in env_dict
    assert "UNKNOWN_VAR" in env_dict
    assert env_dict["CUSTOM_VAR"] == "custom_value"


def test_cli_environment_variable_parsing():
    """Test CLI environment variable parsing"""
    import argparse
    from unittest.mock import Mock
    import sys
    import os
    # Add the parent directory to Python path to import cli module
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from cli import start_command

    # Mock args with environment variables
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = ["CUSTOM_VAR=custom_value", "ANOTHER_VAR=another_value", "PASSWORD=overridden"]

    # Mock dependencies to avoid actual Docker operations
    from unittest.mock import patch, MagicMock

    with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.compose.generate') as mock_generate:

        # Configure mocks
        mock_config = MagicMock()
        mock_config.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000}
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

        # Verify generate was called with correct environment variables
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args
        assert call_args[0][0] == "test-instance"
        assert call_args[0][1] == 8080

        # Check that environment variables were passed correctly
        env_vars = call_args[0][2]
        assert env_vars["CUSTOM_VAR"] == "custom_value"
        assert env_vars["ANOTHER_VAR"] == "another_value"
        assert env_vars["PASSWORD"] == "overridden"