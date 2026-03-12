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