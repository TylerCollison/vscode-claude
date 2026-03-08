def test_create_instance_config():
    """Test creating instance configuration"""
    import sys
    sys.path.insert(0, 'vsclaude')
    from vsclaude.instances import InstanceManager
    manager = InstanceManager()
    config = manager.create_instance_config("test-instance", port=8443)
    assert config["name"] == "test-instance"
    assert config["port"] == 8443