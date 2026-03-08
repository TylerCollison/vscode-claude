import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from vsclaude.compose import generate
from vsclaude.config import ConfigManager


def test_empty_volumes_result_in_no_mounts():
    """Test that empty enabled_volumes results in no volume mounts"""
    config = generate("test-instance", 8443, {}, enabled_volumes=[])
    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    # Should only have Docker socket
    assert len(volumes) == 1
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes


def test_custom_volume_paths():
    """Test custom volume paths"""
    config = generate(
        "test-instance",
        8443,
        {},
        enabled_volumes=["/config", "/workspace", "/custom/path"]
    )
    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    assert "test-instance-config:/config" in volumes
    assert "test-instance-workspace:/workspace" in volumes
    assert "test-instance-path:/custom/path" in volumes


def test_docker_sock_independence():
    """Test that Docker socket is independent of volume configuration"""
    # Docker socket enabled, no volumes
    config = generate("test-instance", 8443, {}, enabled_volumes=[], include_docker_sock=True)
    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    assert len(volumes) == 1
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes

    # Docker socket disabled, volumes enabled
    config = generate(
        "test-instance",
        8443,
        {},
        enabled_volumes=["/config", "/workspace"],
        include_docker_sock=False
    )
    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    assert len(volumes) == 2
    assert "/var/run/docker.sock:/var/run/docker.sock" not in volumes


def test_volume_name_generation():
    """Test that volume names are generated correctly"""
    config = generate(
        "my-instance",
        8443,
        {},
        enabled_volumes=["/config", "/deep/nested/path"]
    )
    volumes = config["volumes"]
    assert "my-instance-config" in volumes
    assert "my-instance-path" in volumes  # basename of nested path


def test_config_manager_volume_methods():
    """Test ConfigManager volume-related methods"""
    manager = ConfigManager()

    # Test default values
    volumes = manager.get_enabled_volumes()
    assert volumes == []

    include_docker_sock = manager.get_include_docker_sock()
    assert include_docker_sock == True

    # Test validation method
    assert manager.validate_volume_paths(["/config", "/workspace"]) == True
    assert manager.validate_volume_paths(["config", "workspace"]) == False
    assert manager.validate_volume_paths([""]) == False
    assert manager.validate_volume_paths(None) == False


def test_edge_cases():
    """Test edge cases for volume functionality"""
    # Test empty string path
    config = generate("test-instance", 8443, {}, enabled_volumes=["/config", ""])
    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    # Empty string should be filtered out or handled gracefully
    assert "test-instance-config:/config" in volumes

    # Test very long instance name
    long_name = "a" * 50
    config = generate(long_name, 8443, {}, enabled_volumes=["/config"])
    volumes = config["volumes"]
    assert f"{long_name}-config" in volumes


def test_default_config_volume_settings():
    """Test that default config includes volume settings"""
    manager = ConfigManager()
    config = manager._default_global_config()
    assert "enabled_volumes" in config
    assert isinstance(config["enabled_volumes"], list)
    assert config["enabled_volumes"] == []
    assert "include_docker_sock" in config
    assert config["include_docker_sock"] == True


def test_backward_compatibility():
    """Test backward compatibility when enabled_volumes is None"""
    config = generate("test-instance", 8443, {}, enabled_volumes=None)
    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    # Should default to /config and /workspace
    assert "test-instance-config:/config" in volumes
    assert "test-instance-workspace:/workspace" in volumes
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes


def test_volume_definitions_in_config():
    """Test that volume definitions are correctly included in config"""
    config = generate("test-instance", 8443, {}, enabled_volumes=["/config", "/workspace"])

    # Check volume definitions
    assert "volumes" in config
    volumes_def = config["volumes"]
    assert "test-instance-config" in volumes_def
    assert "test-instance-workspace" in volumes_def

    # Check that volumes are empty dicts (default Docker volume config)
    assert volumes_def["test-instance-config"] == {}
    assert volumes_def["test-instance-workspace"] == {}


def test_environment_vars_with_volumes():
    """Test that environment variables work correctly with volume configuration"""
    env_vars = {
        "CUSTOM_VAR": "custom_value",
        "ANOTHER_VAR": "another_value"
    }
    config = generate("test-instance", 8443, env_vars, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]

    # Check environment variables
    environment = service["environment"]
    env_dict = {item.split("=")[0]: item.split("=")[1] for item in environment}
    assert env_dict["CUSTOM_VAR"] == "custom_value"
    assert env_dict["ANOTHER_VAR"] == "another_value"
    assert env_dict["IDE_ADDRESS"] == "http://localhost:8443"

    # Check volumes are still present
    volumes = service["volumes"]
    assert "test-instance-config:/config" in volumes
    assert "test-instance-workspace:/workspace" in volumes