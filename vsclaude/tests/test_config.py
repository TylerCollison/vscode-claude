import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_load_global_config():
    """Test loading global configuration"""
    from vsclaude.config import ConfigManager
    manager = ConfigManager()
    config = manager.load_global_config()
    assert config is not None
    assert "port_range" in config


def test_global_config_includes_environment():
    """Test that global config includes environment field with dict default"""
    from vsclaude.config import ConfigManager
    manager = ConfigManager()
    config = manager.load_global_config()
    assert "environment" in config
    assert isinstance(config["environment"], dict)


def test_get_global_environment():
    """Test getting environment from global config"""
    from vsclaude.config import ConfigManager
    manager = ConfigManager()
    # This test should fail initially since get_global_environment method doesn't exist
    environment = manager.get_global_environment()
    assert isinstance(environment, dict)


def test_get_enabled_volumes():
    """Test getting enabled volumes from global config"""
    from vsclaude.config import ConfigManager
    manager = ConfigManager()
    volumes = manager.get_enabled_volumes()
    assert isinstance(volumes, list)
    assert volumes == []


def test_get_include_docker_sock():
    """Test getting Docker socket preference"""
    from vsclaude.config import ConfigManager
    manager = ConfigManager()
    include_docker_sock = manager.get_include_docker_sock()
    assert isinstance(include_docker_sock, bool)
    assert include_docker_sock == True


def test_validate_volume_paths():
    """Test volume path validation"""
    from vsclaude.config import ConfigManager

    # Valid paths
    manager = ConfigManager()
    assert manager.validate_volume_paths(["/config", "/workspace"]) == True

    # Invalid paths
    assert manager.validate_volume_paths(["config", "workspace"]) == False
    assert manager.validate_volume_paths([""]) == False


def test_default_config_includes_volume_settings():
    """Test that default config includes volume settings"""
    from vsclaude.config import ConfigManager
    manager = ConfigManager()
    config = manager._default_global_config()
    assert "enabled_volumes" in config
    assert isinstance(config["enabled_volumes"], list)
    assert config["enabled_volumes"] == []
    assert "include_docker_sock" in config
    assert config["include_docker_sock"] == True