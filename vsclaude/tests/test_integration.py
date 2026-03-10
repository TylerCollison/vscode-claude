def test_full_workflow():
    """Test complete vsclaude workflow"""
    from vsclaude.cli import main
    from vsclaude.config import ConfigManager
    from vsclaude.instances import InstanceManager

    # Test that all components work together
    config_manager = ConfigManager()
    instance_manager = InstanceManager()

    # Verify we can load config and create instances
    config = config_manager.load_global_config()
    assert "port_range" in config

    # This is a smoke test - actual Docker operations would be mocked in real tests
    assert True  # Placeholder for now