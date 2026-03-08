import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_generate_compose_config():
    """Test generating docker-compose configuration"""
    from vsclaude.compose import generate
    config = generate("test-instance", 8443, {})
    assert "services" in config
    assert "vscode-claude" in config["services"]