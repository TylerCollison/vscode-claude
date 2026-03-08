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