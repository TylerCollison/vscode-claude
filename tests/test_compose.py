def test_generate_compose_config():
    """Test generating docker-compose configuration"""
    from vsclaude.vsclaude.compose import generate
    config = generate("test-instance", 8443, {})
    assert "services" in config
    assert "vscode-claude" in config["services"]