import pytest
from cconx.cconx.compose import generate, _validate_instance_name, _validate_port, _validate_restart_policy, _validate_image_name


def test_generate_basic_config():
    """Test generating basic docker-compose configuration"""
    config = generate("test-instance", 8443, {}, enabled_volumes=["/config", "/workspace"])

    assert "services" in config
    assert "volumes" in config
    assert "vscode-claude" in config["services"]

    service = config["services"]["vscode-claude"]
    assert service["image"] == "tylercollison2089/vscode-claude:latest"
    assert service["container_name"] == "cconx-test-instance"
    assert service["ports"] == ["8443:8443"]
    assert service["restart"] == "unless-stopped"

    # Check environment variables
    env_vars = {item.split('=')[0]: item.split('=')[1] for item in service["environment"]}
    assert env_vars["IDE_ADDRESS"] == "http://localhost:8443"
    assert env_vars["CCR_PROFILE"] == "default"

    # Check volumes
    volumes = config["volumes"]
    assert "test-instance-config" in volumes
    assert "test-instance-workspace" in volumes


def test_generate_with_custom_parameters():
    """Test generating configuration with custom parameters"""
    environment_vars = {
        "CCR_PROFILE": "custom-profile",
        "EXTRA_VAR": "extra-value"
    }

    config = generate(
        instance_name="custom-instance",
        port=9000,
        environment_vars=environment_vars,
        image_tag="v1.0.0",
        container_port=8080,
        additional_ports=["3000:3000", "5000:5000"],
        restart_policy="always",
        include_docker_sock=False,
        enabled_volumes=["/config", "/workspace"]
    )

    service = config["services"]["vscode-claude"]
    assert service["image"] == "tylercollison2089/vscode-claude:v1.0.0"
    assert service["ports"] == ["9000:8080", "3000:3000", "5000:5000"]
    assert service["restart"] == "always"

    # Check environment variable merging
    env_vars = {item.split('=')[0]: item.split('=')[1] for item in service["environment"]}
    assert env_vars["IDE_ADDRESS"] == "http://localhost:9000"
    assert env_vars["CCR_PROFILE"] == "custom-profile"  # Custom value should override
    assert env_vars["EXTRA_VAR"] == "extra-value"

    # Check volumes (Docker socket should be excluded)
    volumes = service["volumes"]
    assert "/var/run/docker.sock:/var/run/docker.sock" not in volumes
    assert "custom-instance-config:/config" in volumes
    assert "custom-instance-workspace:/workspace" in volumes


def test_generate_with_custom_image_name():
    """Test generating configuration with custom image name"""
    config = generate(
        instance_name="test-instance",
        port=8443,
        image_name="custom-registry/my-image",
        image_tag="v1.2.3",
        enabled_volumes=["/config", "/workspace"]
    )

    service = config["services"]["vscode-claude"]
    assert service["image"] == "custom-registry/my-image:v1.2.3"

    # Test with default image tag
    config2 = generate(
        instance_name="test-instance",
        port=8443,
        image_name="custom-registry/my-image",
        enabled_volumes=["/config", "/workspace"]
    )

    service2 = config2["services"]["vscode-claude"]
    assert service2["image"] == "custom-registry/my-image:latest"

    # Test with just image name override (no tag)
    config3 = generate(
        instance_name="test-instance",
        port=8443,
        image_name="custom-registry/my-image",
        image_tag="",
        enabled_volumes=["/config", "/workspace"]
    )

    service3 = config3["services"]["vscode-claude"]
    assert service3["image"] == "custom-registry/my-image"


def test_generate_with_none_environment_vars():
    """Test generating configuration with None environment_vars"""
    config = generate("test-instance", 8443, None, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]

    env_vars = {item.split('=')[0]: item.split('=')[1] for item in service["environment"]}
    assert env_vars["IDE_ADDRESS"] == "http://localhost:8443"
    assert env_vars["CCR_PROFILE"] == "default"


def test_generate_with_empty_environment_vars():
    """Test generating configuration with empty environment_vars"""
    config = generate("test-instance", 8443, {}, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]

    env_vars = {item.split('=')[0]: item.split('=')[1] for item in service["environment"]}
    assert len(env_vars) == 2  # Only default variables


def test_environment_variable_merging():
    """Test that environment variables merge correctly"""
    # Override default variables
    env_vars = {"CCR_PROFILE": "custom"}
    config = generate("test-instance", 8443, env_vars, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]

    env_vars_dict = {item.split('=')[0]: item.split('=')[1] for item in service["environment"]}
    assert env_vars_dict["CCR_PROFILE"] == "custom"
    assert env_vars_dict["IDE_ADDRESS"] == "http://localhost:8443"


def test_volume_configuration():
    """Test volume configuration"""
    config = generate("test-instance", 8443, {}, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]

    # Should include Docker socket by default
    volumes = service["volumes"]
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes
    assert "test-instance-config:/config" in volumes
    assert "test-instance-workspace:/workspace" in volumes

    # Without Docker socket
    config = generate("test-instance", 8443, {}, include_docker_sock=False, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    assert "/var/run/docker.sock:/var/run/docker.sock" not in volumes


def test_port_mappings():
    """Test various port mapping configurations"""
    # Default configuration
    config = generate("test-instance", 8080, {}, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    assert service["ports"] == ["8080:8443"]

    # Custom container port
    config = generate("test-instance", 8080, {}, container_port=3000, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    assert service["ports"] == ["8080:3000"]

    # Additional ports
    config = generate("test-instance", 8080, {}, additional_ports=["9000:9000", "5000:5000"], enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    assert service["ports"] == ["8080:8443", "9000:9000", "5000:5000"]


def test_image_configuration():
    """Test image tag configuration"""
    config = generate("test-instance", 8443, {}, image_tag="v1.2.3", enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    assert service["image"] == "tylercollison2089/vscode-claude:v1.2.3"


def test_container_name_format():
    """Test container name formatting"""
    config = generate("my-instance", 8443, {}, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    assert service["container_name"] == "cconx-my-instance"

    config = generate("instance_1", 8443, {}, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    assert service["container_name"] == "cconx-instance_1"


def test_restart_policy_configuration():
    """Test restart policy configuration"""
    for policy in ["no", "always", "on-failure", "unless-stopped"]:
        config = generate("test-instance", 8443, {}, restart_policy=policy, enabled_volumes=["/config", "/workspace"])
        service = config["services"]["vscode-claude"]
        assert service["restart"] == policy


def test_validate_instance_name():
    """Test instance name validation"""
    # Valid names
    _validate_instance_name("valid-name")
    _validate_instance_name("valid_name")
    _validate_instance_name("valid123")
    _validate_instance_name("a")

    # Invalid names
    with pytest.raises(ValueError, match="instance_name must be a string"):
        _validate_instance_name(None)

    with pytest.raises(ValueError, match="instance_name cannot be empty"):
        _validate_instance_name("")

    with pytest.raises(ValueError, match="instance_name can only contain"):
        _validate_instance_name("invalid name")

    with pytest.raises(ValueError, match="instance_name can only contain"):
        _validate_instance_name("invalid@name")

    with pytest.raises(ValueError, match="instance_name cannot start or end with a hyphen"):
        _validate_instance_name("-invalid")

    with pytest.raises(ValueError, match="instance_name cannot start or end with a hyphen"):
        _validate_instance_name("invalid-")


def test_validate_port():
    """Test port validation"""
    # Valid ports
    _validate_port(1)
    _validate_port(8080)
    _validate_port(65535)

    # Invalid ports
    with pytest.raises(ValueError, match="port must be an integer"):
        _validate_port("8080")

    with pytest.raises(ValueError, match="port must be between 1 and 65535"):
        _validate_port(0)

    with pytest.raises(ValueError, match="port must be between 1 and 65535"):
        _validate_port(65536)

    with pytest.raises(ValueError, match="port must be between 1 and 65535"):
        _validate_port(-1)


def test_validate_restart_policy():
    """Test restart policy validation"""
    # Valid policies
    _validate_restart_policy("no")
    _validate_restart_policy("always")
    _validate_restart_policy("on-failure")
    _validate_restart_policy("unless-stopped")

    # Invalid policy
    with pytest.raises(ValueError, match="restart_policy must be one of"):
        _validate_restart_policy("invalid")


def test_integration_style_tests():
    """Test more complex integration-style scenarios"""
    # Complex environment setup
    complex_env = {
        "CCR_PROFILE": "production",
        "LOG_LEVEL": "debug",
        "CUSTOM_SETTING": "custom-value"
    }

    config = generate(
        instance_name="production-instance",
        port=443,
        environment_vars=complex_env,
        image_tag="stable",
        container_port=443,
        additional_ports=["80:80", "22:22"],
        restart_policy="always",
        enabled_volumes=["/config", "/workspace"]
    )

    service = config["services"]["vscode-claude"]
    assert service["image"] == "tylercollison2089/vscode-claude:stable"
    assert service["ports"] == ["443:443", "80:80", "22:22"]
    assert service["restart"] == "always"

    # Verify environment variables
    env_vars = {item.split('=')[0]: item.split('=')[1] for item in service["environment"]}
    assert env_vars["CCR_PROFILE"] == "production"
    assert env_vars["LOG_LEVEL"] == "debug"
    assert env_vars["CUSTOM_SETTING"] == "custom-value"
    assert env_vars["IDE_ADDRESS"] == "http://localhost:443"


def test_edge_cases():
    """Test edge cases and boundary conditions"""
    # Minimum valid port
    config = generate("edge-case", 1, {}, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    assert service["ports"] == ["1:8443"]

    # Maximum valid port
    config = generate("edge-case", 65535, {}, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    assert service["ports"] == ["65535:8443"]

    # Very long instance name (within valid chars)
    config = generate("a" * 50, 8443, {}, enabled_volumes=["/config", "/workspace"])
    service = config["services"]["vscode-claude"]
    assert service["container_name"] == f"cconx-{'a' * 50}"


def test_generate_with_custom_volumes():
    """Test generating configuration with custom volume paths"""
    config = generate(
        instance_name="test-instance",
        port=8443,
        environment_vars={},
        enabled_volumes=["/config", "/workspace", "/data"]
    )

    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    assert "test-instance-config:/config" in volumes
    assert "test-instance-workspace:/workspace" in volumes
    assert "test-instance-data:/data" in volumes

    # Check volume definitions
    assert "test-instance-config" in config["volumes"]
    assert "test-instance-workspace" in config["volumes"]
    assert "test-instance-data" in config["volumes"]


def test_generate_backward_compatibility():
    """Test that default behavior remains unchanged (backward compatibility)"""
    config = generate("test-instance", 8443, {})
    service = config["services"]["vscode-claude"]

    # Should include default volumes
    volumes = service["volumes"]
    assert "test-instance-config:/config" in volumes
    assert "test-instance-workspace:/workspace" in volumes
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes

    # Check volume definitions
    assert "test-instance-config" in config["volumes"]
    assert "test-instance-workspace" in config["volumes"]


def test_generate_with_empty_custom_volumes():
    """Test generating configuration with empty custom volumes list"""
    config = generate(
        instance_name="test-instance",
        port=8443,
        environment_vars={},
        enabled_volumes=[]
    )

    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]

    # Should only include Docker socket when enabled_volumes is empty
    assert len(volumes) == 1
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes

    # No volume definitions should be created
    assert config["volumes"] == {}


def test_generate_with_none_custom_volumes():
    """Test generating configuration with None custom volumes"""
    config = generate(
        instance_name="test-instance",
        port=8443,
        environment_vars={},
        enabled_volumes=None
    )

    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]

    # Should include default volumes when enabled_volumes is None
    assert "test-instance-config:/config" in volumes
    assert "test-instance-workspace:/workspace" in volumes
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes


def test_backward_compatibility():
    """Test that existing tests work with new volume system"""
    # Default behavior (no volumes specified) should result in default volumes
    config = generate("test-instance", 8443, {})
    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    # Should include default volumes and Docker socket
    assert "test-instance-config:/config" in volumes
    assert "test-instance-workspace:/workspace" in volumes
    assert "/var/run/docker.sock:/var/run/docker.sock" in volumes

    # Explicitly enable default volumes for backward compatibility
    config = generate(
        "test-instance",
        8443,
        {},
        enabled_volumes=["/config", "/workspace"]
    )
    service = config["services"]["vscode-claude"]
    volumes = service["volumes"]
    assert "test-instance-config:/config" in volumes
    assert "test-instance-workspace:/workspace" in volumes


def test_validate_image_name():
    """Test image name validation"""
    # Valid image names
    _validate_image_name("nginx")
    _validate_image_name("postgres")
    _validate_image_name("custom-image")
    _validate_image_name("custom_image")
    _validate_image_name("registry.example.com/image")
    _validate_image_name("registry/namespace/image")
    _validate_image_name("a" * 255)  # Maximum length

    # Invalid image names
    with pytest.raises(ValueError, match="image_name must be a string"):
        _validate_image_name(None)

    with pytest.raises(ValueError, match="image_name cannot be empty"):
        _validate_image_name("")

    with pytest.raises(ValueError, match="image_name cannot exceed 255 characters"):
        _validate_image_name("a" * 256)

    with pytest.raises(ValueError, match="image_name cannot contain uppercase letters"):
        _validate_image_name("InvalidImage")

    with pytest.raises(ValueError, match="image_name cannot start with"):
        _validate_image_name("-invalid")

    with pytest.raises(ValueError, match="image_name cannot end with"):
        _validate_image_name("invalid-")

    with pytest.raises(ValueError, match="image_name cannot contain consecutive"):
        _validate_image_name("invalid..name")

    with pytest.raises(ValueError, match="image_name components cannot be empty"):
        _validate_image_name("registry//image")

    with pytest.raises(ValueError, match="image_name components cannot start or end with hyphens"):
        _validate_image_name("registry/-invalid/image")

    with pytest.raises(ValueError, match="image_name can only contain"):
        _validate_image_name("invalid@image")


def test_generate_with_invalid_image_names():
    """Test generating configuration with invalid image names"""
    # Test various invalid image names
    invalid_names = [
        "",  # Empty
        "a" * 256,  # Too long
        "InvalidImage",  # Uppercase
        "-invalid",  # Starts with hyphen
        "invalid-",  # Ends with hyphen
        "invalid..name",  # Consecutive dots
        "registry//image",  # Empty component
        "invalid@image",  # Invalid character
    ]

    for invalid_name in invalid_names:
        with pytest.raises(ValueError):
            generate(
                instance_name="test-instance",
                port=8443,
                image_name=invalid_name,
                enabled_volumes=["/config", "/workspace"]
            )