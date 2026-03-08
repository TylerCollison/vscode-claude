def test_load_global_config():
    """Test loading global configuration"""
    from vsclaude.config import ConfigManager
    manager = ConfigManager()
    config = manager.load_global_config()
    assert config is not None
    assert "port_range" in config


def test_global_config_includes_environment():
    """Test that global config includes environment field with empty dict default"""
    from vsclaude.config import ConfigManager
    manager = ConfigManager()
    config = manager.load_global_config()
    assert "environment" in config
    assert isinstance(config["environment"], dict)
    assert config["environment"] == {}


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