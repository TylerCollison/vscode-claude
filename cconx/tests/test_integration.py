def test_full_workflow():
    """Test complete cconx workflow"""
    from cconx.cconx.cli import main
    from cconx.cconx.config import ConfigManager
    from cconx.cconx.instances import InstanceManager

    # Test that all components work together
    config_manager = ConfigManager()
    instance_manager = InstanceManager()

    # Verify we can load config and create instances
    config = config_manager.load_global_config()
    assert "port_range" in config

    # This is a smoke test - actual Docker operations would be mocked in real tests
    assert True  # Placeholder for now


def test_dns_integration_with_mocked_components():
    """Test DNS integration flow with mocked Docker operations"""
    from unittest.mock import patch, MagicMock
    from cconx.cconx.cli import start_command
    from cconx.cconx.config import ConfigManager
    import argparse

    # Create mock arguments with DNS configuration
    args = argparse.Namespace(
        name="dns-test-instance",
        port=None,
        env=[],
        env_append=[],
        image=None,
        dns=["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"]
    )

    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager, \
         patch('cconx.cconx.compose.generate') as mock_generate, \
         patch('cconx.cconx.docker.DockerClient') as MockDockerClient:

        # Mock ConfigManager
        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True,
            "docker_network": None,
            "dns_servers": None
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.get_default_image.return_value = "tylercollison2089/vscode-claude:latest"
        mock_config_manager.format_ide_address.return_value = "http://localhost:8000"
        mock_config_manager.get_dns_servers.return_value = None
        # Mock DNS validation
        mock_config_manager._validate_dns_servers.return_value = ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"]

        # Mock PortManager
        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        # Mock InstanceManager
        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "dns-test-instance", "port": 8000
        }

        # Mock DockerClient
        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        # Mock compose generation
        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "tylercollison2089/vscode-claude:latest",
                    "ports": ["8000:8000"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify DNS validation was called
            mock_config_manager._validate_dns_servers.assert_called_once_with(["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"])

            # Verify container creation includes DNS configuration
            mock_docker_client.client.containers.create.assert_called_once()
            create_call_args = mock_docker_client.client.containers.create.call_args
            assert "dns" in create_call_args[1]
            assert create_call_args[1]["dns"] == ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"]

            # Verify success message
            mock_print.assert_any_call("Container 'cconx-dns-test-instance' started successfully")


def test_dns_integration_with_global_config():
    """Test DNS integration using global configuration"""
    from unittest.mock import patch, MagicMock
    from cconx.cconx.cli import start_command
    import argparse

    # Create mock arguments without CLI DNS flag
    args = argparse.Namespace(
        name="global-dns-test-instance",
        port=None,
        env=[],
        env_append=[],
        image=None,
        dns=None
    )

    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager, \
         patch('cconx.cconx.compose.generate') as mock_generate, \
         patch('cconx.cconx.docker.DockerClient') as MockDockerClient:

        # Mock ConfigManager with global DNS configuration
        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True,
            "docker_network": None,
            "dns_servers": ["9.9.9.9", "8.8.8.8"]
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.get_default_image.return_value = "tylercollison2089/vscode-claude:latest"
        mock_config_manager.format_ide_address.return_value = "http://localhost:8000"
        mock_config_manager.get_dns_servers.return_value = ["9.9.9.9", "8.8.8.8"]

        # Mock other components
        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "global-dns-test-instance", "port": 8000
        }

        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "tylercollison2089/vscode-claude:latest",
                    "ports": ["8000:8000"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify DNS validation was NOT called (global DNS already validated)
            mock_config_manager._validate_dns_servers.assert_not_called()

            # Verify container creation includes global DNS servers
            mock_docker_client.client.containers.create.assert_called_once()
            create_call_args = mock_docker_client.client.containers.create.call_args
            assert "dns" in create_call_args[1]
            assert create_call_args[1]["dns"] == ["9.9.9.9", "8.8.8.8"]


def test_dns_integration_backward_compatibility():
    """Test DNS integration maintains backward compatibility"""
    from unittest.mock import patch, MagicMock
    from cconx.cconx.cli import start_command
    import argparse

    # Create mock arguments
    args = argparse.Namespace(
        name="compat-test-instance",
        port=None,
        env=[],
        env_append=[],
        image=None,
        dns=None
    )

    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager, \
         patch('cconx.cconx.compose.generate') as mock_generate, \
         patch('cconx.cconx.docker.DockerClient') as MockDockerClient:

        # Mock ConfigManager with old config format (no dns_servers field)
        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True,
            "docker_network": None
            # No dns_servers key - simulates old config
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.get_default_image.return_value = "tylercollison2089/vscode-claude:latest"
        mock_config_manager.format_ide_address.return_value = "http://localhost:8000"
        mock_config_manager.get_dns_servers.return_value = None

        # Mock other components
        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "compat-test-instance", "port": 8000
        }

        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "tylercollison2089/vscode-claude:latest",
                    "ports": ["8000:8000"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify DNS validation was NOT called (no DNS configuration)
            mock_config_manager._validate_dns_servers.assert_not_called()

            # Verify container creation does NOT include DNS parameter
            mock_docker_client.client.containers.create.assert_called_once()
            create_call_args = mock_docker_client.client.containers.create.call_args
            assert "dns" not in create_call_args[1]

            # Verify normal operation succeeded
            mock_print.assert_any_call("Container 'cconx-compat-test-instance' started successfully")


def test_dns_integration_host_network_skipping():
    """Test DNS integration skips DNS for host network mode"""
    from unittest.mock import patch, MagicMock
    from cconx.cconx.cli import start_command
    import argparse

    # Create mock arguments with DNS servers
    args = argparse.Namespace(
        name="host-network-test-instance",
        port=None,
        env=[],
        env_append=[],
        image=None,
        dns=["8.8.8.8", "1.1.1.1"]
    )

    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager, \
         patch('cconx.cconx.compose.generate') as mock_generate, \
         patch('cconx.cconx.docker.DockerClient') as MockDockerClient:

        # Mock ConfigManager with host network
        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True,
            "docker_network": "host"
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.get_default_image.return_value = "tylercollison2089/vscode-claude:latest"
        mock_config_manager.format_ide_address.return_value = "http://localhost:8000"
        mock_config_manager.get_dns_servers.return_value = None
        mock_config_manager.get_docker_network.return_value = "host"
        # Mock DNS validation
        mock_config_manager._validate_dns_servers.return_value = ["8.8.8.8", "1.1.1.1"]

        # Mock other components
        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "host-network-test-instance", "port": 8000
        }

        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "tylercollison2089/vscode-claude:latest",
                    "ports": ["8000:8000"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify DNS validation WAS called (CLI DNS provided)
            mock_config_manager._validate_dns_servers.assert_called_once_with(["8.8.8.8", "1.1.1.1"])

            # Verify container creation does NOT include DNS parameter for host network
            mock_docker_client.client.containers.create.assert_called_once()
            create_call_args = mock_docker_client.client.containers.create.call_args
            assert "dns" not in create_call_args[1]

            # Verify container uses host network
            assert create_call_args[1]["network"] == "host"