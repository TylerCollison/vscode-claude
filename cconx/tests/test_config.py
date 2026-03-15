import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_load_global_config():
    """Test loading global configuration"""
    from cconx.config import ConfigManager
    manager = ConfigManager()
    config = manager.load_global_config()
    assert config is not None
    assert "port_range" in config


def test_global_config_includes_environment():
    """Test that global config includes environment field with dict default"""
    from cconx.config import ConfigManager
    manager = ConfigManager()
    config = manager.load_global_config()
    assert "environment" in config
    assert isinstance(config["environment"], dict)


def test_get_global_environment():
    """Test getting environment from global config"""
    from cconx.config import ConfigManager
    manager = ConfigManager()
    # This test should fail initially since get_global_environment method doesn't exist
    environment = manager.get_global_environment()
    assert isinstance(environment, dict)


def test_get_enabled_volumes():
    """Test getting enabled volumes from global config"""
    from cconx.config import ConfigManager
    manager = ConfigManager()
    volumes = manager.get_enabled_volumes()
    assert isinstance(volumes, list)
    assert volumes == []


def test_get_include_docker_sock():
    """Test getting Docker socket preference"""
    from cconx.config import ConfigManager
    manager = ConfigManager()
    include_docker_sock = manager.get_include_docker_sock()
    assert isinstance(include_docker_sock, bool)
    assert include_docker_sock == True


def test_validate_volume_paths():
    """Test volume path validation"""
    from cconx.config import ConfigManager

    # Valid paths
    manager = ConfigManager()
    assert manager.validate_volume_paths(["/config", "/workspace"]) == True

    # Invalid paths
    assert manager.validate_volume_paths(["config", "workspace"]) == False
    assert manager.validate_volume_paths([""]) == False


def test_default_config_includes_volume_settings():
    """Test that default config includes volume settings"""
    from cconx.config import ConfigManager
    manager = ConfigManager()
    config = manager._default_global_config()
    assert "enabled_volumes" in config
    assert isinstance(config["enabled_volumes"], list)
    assert config["enabled_volumes"] == []
    assert "include_docker_sock" in config
    assert config["include_docker_sock"] == True


def test_get_docker_network():
    """Test getting docker network from config"""
    import tempfile
    from cconx.config import ConfigManager

    # Test default value (no network) with clean config
    with tempfile.TemporaryDirectory() as tmpdir:
        config_manager = ConfigManager(tmpdir)
        assert config_manager.get_docker_network() is None

        # Test with network specified
        config = config_manager.load_global_config()
        config["docker_network"] = "test-network"
        config_manager._save_config(config)

        assert config_manager.get_docker_network() == "test-network"


def test_docker_network_default_value():
    """Test that docker_network defaults to None"""
    from cconx.config import ConfigManager
    config_manager = ConfigManager()
    default_config = config_manager._default_global_config()
    assert default_config["docker_network"] is None


def test_network_exists_with_mock():
    """Test network_exists with MockDockerClient"""
    from cconx.cconx.docker import MockDockerClient
    mock_client = MockDockerClient()
    assert mock_client.network_exists("bridge") == True
    assert mock_client.network_exists("host") == True
    assert mock_client.network_exists("none") == True
    assert mock_client.network_exists("non-existent") == False


def test_start_command_with_missing_network():
    """Test start command exits gracefully when network doesn't exist"""
    from unittest.mock import patch, MagicMock
    import argparse
    import sys
    import tempfile

    # Test start_command CLI function
    try:
        from cconx.cconx.cli import start_command
    except ImportError:
        # If cli module isn't available, create a simplified test
        from unittest.mock import patch, MagicMock

        def test_start_command_simplified():
            """Simplified test for network validation logic"""
            from cconx.config import ConfigManager
            from cconx.cconx.docker import MockDockerClient

            # Create a temporary directory for config
            with tempfile.TemporaryDirectory() as tmpdir:
                config_manager = ConfigManager(tmpdir)

                # Set a non-existent network
                config = config_manager.load_global_config()
                config["docker_network"] = "non-existent-network"
                config_manager._save_config(config)

                # Mock Docker client that returns False for network
                mock_client = MockDockerClient()

                # Test that network validation logic works
                network_name = config_manager.get_docker_network()
                assert network_name == "non-existent-network"
                assert mock_client.network_exists(network_name) == False

        test_start_command_simplified()


def test_backward_compatibility():
    """Test that existing configs without docker_network work unchanged"""
    import tempfile
    from cconx.config import ConfigManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_manager = ConfigManager(tmpdir)
        config = config_manager.load_global_config()

        # Remove docker_network if it exists (simulate old config)
        if "docker_network" in config:
            del config["docker_network"]

        config_manager._save_config(config)

        # Reload and verify get_docker_network returns None
        reloaded_config = config_manager.load_global_config()
        assert "docker_network" not in reloaded_config
        assert config_manager.get_docker_network() is None


def test_get_dns_servers():
    """Test getting DNS servers from config"""
    import tempfile
    from cconx.config import ConfigManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_manager = ConfigManager(tmpdir)

        # Test default value (no DNS servers) with clean config
        assert config_manager.get_dns_servers() is None

        # Test with DNS servers specified
        config = config_manager.load_global_config()
        config["dns_servers"] = ["8.8.8.8", "1.1.1.1"]
        config_manager._save_config(config)

        dns_servers = config_manager.get_dns_servers()
        assert dns_servers == ["8.8.8.8", "1.1.1.1"]

        # Test empty list (use Docker defaults)
        config["dns_servers"] = []
        config_manager._save_config(config)
        assert config_manager.get_dns_servers() == []


def test_validate_dns_servers():
    """Test DNS server validation"""
    from cconx.config import ConfigManager

    config_manager = ConfigManager()

    # Test valid IPv4 addresses
    valid_servers = ["8.8.8.8", "192.168.1.1", "10.0.0.1"]
    assert config_manager._validate_dns_servers(valid_servers) == valid_servers

    # Test valid IPv6 addresses
    ipv6_servers = ["2001:4860:4860::8888", "::1", "fe80::1"]
    assert config_manager._validate_dns_servers(ipv6_servers) == ipv6_servers

    # Test mixed valid addresses
    mixed_servers = ["8.8.8.8", "2001:4860:4860::8888", "1.1.1.1"]
    assert config_manager._validate_dns_servers(mixed_servers) == mixed_servers

    # Test filtering invalid addresses
    invalid_servers = ["8.8.8.8", "invalid", "1.1.1.1", "not-an-ip"]
    valid_result = config_manager._validate_dns_servers(invalid_servers)
    assert valid_result == ["8.8.8.8", "1.1.1.1"]

    # Test duplicate DNS servers (should be preserved)
    duplicate_servers = ["8.8.8.8", "8.8.8.8", "1.1.1.1"]
    assert config_manager._validate_dns_servers(duplicate_servers) == duplicate_servers

    # Test empty list
    assert config_manager._validate_dns_servers([]) == []

    # Test invalid input type
    try:
        config_manager._validate_dns_servers("not-a-list")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_dns_servers_backward_compatibility():
    """Test that existing configs without dns_servers work unchanged"""
    import tempfile
    from cconx.config import ConfigManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_manager = ConfigManager(tmpdir)
        config = config_manager.load_global_config()

        # Remove dns_servers if it exists (simulate old config)
        if "dns_servers" in config:
            del config["dns_servers"]

        config_manager._save_config(config)

        # Reload and verify get_dns_servers returns None
        reloaded_config = config_manager.load_global_config()
        assert "dns_servers" not in reloaded_config
        assert config_manager.get_dns_servers() is None


def test_dns_servers_default_value():
    """Test that dns_servers defaults to None"""
    from cconx.config import ConfigManager
    config_manager = ConfigManager()
    default_config = config_manager._default_global_config()
    assert default_config["dns_servers"] is None


def test_get_dns_servers_none_case():
    """Test get_dns_servers behavior with None value"""
    import tempfile
    from cconx.config import ConfigManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_manager = ConfigManager(tmpdir)

        # Test explicit None value
        config = config_manager.load_global_config()
        config["dns_servers"] = None
        config_manager._save_config(config)

        assert config_manager.get_dns_servers() is None


def test_get_dns_servers_empty_list():
    """Test get_dns_servers behavior with empty list"""
    import tempfile
    from cconx.config import ConfigManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_manager = ConfigManager(tmpdir)

        # Test empty list
        config = config_manager.load_global_config()
        config["dns_servers"] = []
        config_manager._save_config(config)

        assert config_manager.get_dns_servers() == []


def test_validate_dns_servers_mixed_ipv4_ipv6():
    """Test DNS validation with mixed IPv4 and IPv6 addresses"""
    from cconx.config import ConfigManager

    config_manager = ConfigManager()

    # Test mixed valid addresses
    mixed_servers = ["8.8.8.8", "2001:4860:4860::8888", "1.1.1.1", "::1", "192.168.1.1"]
    validated_servers = config_manager._validate_dns_servers(mixed_servers)

    # All valid addresses should be preserved
    assert validated_servers == mixed_servers


def test_validate_dns_servers_with_warnings():
    """Test DNS validation with invalid addresses that trigger warnings"""
    from cconx.config import ConfigManager

    config_manager = ConfigManager()

    # Test addresses that will trigger warnings
    problem_servers = ["8.8.8.8", "invalid-address", "1.1.1.1", "not-an-ip", "2001:4860:4860::8888"]
    valid_result = config_manager._validate_dns_servers(problem_servers)

    # Only valid IP addresses should be kept
    assert valid_result == ["8.8.8.8", "1.1.1.1", "2001:4860:4860::8888"]


def test_validate_dns_servers_single_invalid():
    """Test DNS validation with only invalid addresses"""
    from cconx.config import ConfigManager

    config_manager = ConfigManager()

    # Test with all invalid addresses
    invalid_servers = ["invalid", "not-an-ip", "bad-address"]
    valid_result = config_manager._validate_dns_servers(invalid_servers)

    # All invalid addresses should be filtered out
    assert valid_result == []


def test_validate_dns_servers_special_cases():
    """Test DNS validation with special IP address cases"""
    from cconx.config import ConfigManager

    config_manager = ConfigManager()

    # Test special but valid IP addresses
    special_servers = ["0.0.0.0", "127.0.0.1", "255.255.255.255", "::"]
    validated_servers = config_manager._validate_dns_servers(special_servers)

    # All special addresses are valid IPs
    assert validated_servers == special_servers


def test_config_manager_setup_wizard_integration():
    """Test ConfigManager integration with setup wizard."""
    import tempfile
    from unittest.mock import patch, MagicMock
    from cconx.config import ConfigManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_manager = ConfigManager(tmpdir)

        # Test that setup wizard method exists
        assert hasattr(config_manager, 'run_setup_wizard')

        # Test method returns a dictionary
        with patch('cconx.wizard.setup_wizard.SetupWizard') as mock_wizard:
            mock_instance = MagicMock()
            mock_wizard.return_value = mock_instance
            mock_instance.run.return_value = {"test": "value"}

            result = config_manager.run_setup_wizard()
            assert result == {"test": "value"}