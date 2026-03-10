#!/usr/bin/env python3
"""Comprehensive integration tests for Docker image configuration"""

import tempfile
import json
import os
import sys

# Add module path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_config_manager_default_image():
    """Test ConfigManager default image configuration"""
    from vsclaude.vsclaude.config import ConfigManager
    from vsclaude.vsclaude.compose import generate

    # Use temporary directory to avoid conflicts
    with tempfile.TemporaryDirectory() as temp_dir:
        config_manager = ConfigManager(config_dir=temp_dir)

        # Test default image
        default_image = config_manager.get_default_image()
        assert default_image == "tylercollison2089/vscode-claude:latest"

        # Test generating compose config with default image
        config = generate(
            "test-instance",
            8080,
            {},
            enabled_volumes=["/config", "/workspace"]
        )

        service = config["services"]["vscode-claude"]
        assert service["image"] == "tylercollison2089/vscode-claude:latest"

        # Test custom default image
        global_config = config_manager.load_global_config()
        global_config["default_image"] = "custom-registry/image:tag"
        config_manager._save_config(global_config)

        custom_image = config_manager.get_default_image()
        assert custom_image == "custom-registry/image:tag"


def test_compose_generate_with_custom_image():
    """Test compose.generate() with custom image parameters"""
    from vsclaude.vsclaude.compose import generate

    # Test full image string
    config = generate(
        "test-instance",
        8080,
        {},
        image_name="custom-registry/my-image",
        image_tag="v1.2.3",
        enabled_volumes=["/config", "/workspace"]
    )

    service = config["services"]["vscode-claude"]
    assert service["image"] == "custom-registry/my-image:v1.2.3"

    # Test without tag (should use default)
    config2 = generate(
        "test-instance",
        8080,
        {},
        image_name="custom-registry/my-image",
        enabled_volumes=["/config", "/workspace"]
    )

    service2 = config2["services"]["vscode-claude"]
    assert service2["image"] == "custom-registry/my-image:latest"

    # Test image string without tag separator
    config3 = generate(
        "test-instance",
        8080,
        {},
        image_name="custom-registry/my-image",
        image_tag="",
        enabled_volumes=["/config", "/workspace"]
    )

    service3 = config3["services"]["vscode-claude"]
    assert service3["image"] == "custom-registry/my-image"


def test_cli_image_flag_integration():
    """Test CLI --image flag integration with compose.generate()"""
    import argparse
    from unittest.mock import patch, MagicMock

    # Mock yaml module
    import sys
    from unittest.mock import MagicMock
    mock_yaml = MagicMock()
    sys.modules['yaml'] = mock_yaml

    from vsclaude.vsclaude.cli import start_command

    # Test argument parsing
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("name")
    start_parser.add_argument("--port", type=int)
    start_parser.add_argument("--env", action="append")
    start_parser.add_argument("--env-append", action="append")
    start_parser.add_argument("--image")

    # Test with image flag
    args = parser.parse_args(['start', 'test-instance', '--image', 'custom-registry/my-image:v1.2.3'])
    assert args.image == "custom-registry/my-image:v1.2.3"

    # Test without image flag
    args2 = parser.parse_args(['start', 'test-instance'])
    assert args2.image is None

    # Mock dependencies and test start_command integration
    with patch('vsclaude.vsclaude.config.ConfigManager', create=True) as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager', create=True) as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager', create=True) as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate, \
         patch('vsclaude.vsclaude.docker.DockerClient', create=True) as MockDockerClient:

        # Setup mocks
        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": ["/config", "/workspace"]
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = ["/config", "/workspace"]
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.format_ide_address.return_value = "http://localhost:8080"

        mock_port_manager = MockPortManager.return_value

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {}

        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        # Test start_command with image flag
        args_with_image = argparse.Namespace(
            name="test-instance",
            port=8080,
            env=None,
            env_append=None,
            image="custom-registry/my-image:v1.2.3"
        )

        start_command(args_with_image)

        # Verify generate was called with correct image parameters
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args.kwargs

        # Check image parameters
        assert 'image_name' in call_kwargs
        assert call_kwargs['image_name'] == 'custom-registry/my-image'
        assert 'image_tag' in call_kwargs
        assert call_kwargs['image_tag'] == 'v1.2.3'


def test_backward_compatibility():
    """Test that existing functionality continues to work"""
    from vsclaude.vsclaude.compose import generate

    # Test default behavior (no image_name parameter)
    config = generate(
        "test-instance",
        8080,
        {},
        enabled_volumes=["/config", "/workspace"]
    )

    service = config["services"]["vscode-claude"]
    assert service["image"] == "tylercollison2089/vscode-claude:latest"

    # Test with image_tag only (backward compatibility)
    config2 = generate(
        "test-instance",
        8080,
        {},
        image_tag="v1.0.0",
        enabled_volumes=["/config", "/workspace"]
    )

    service2 = config2["services"]["vscode-claude"]
    assert service2["image"] == "tylercollison2089/vscode-claude:v1.0.0"


def test_image_parsing_logic():
    """Test image name/tag parsing logic"""
    import argparse

    # Test CLI argument parsing
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("name")
    start_parser.add_argument("--image")

    # Test various image string formats
    test_cases = [
        ("custom-registry/my-image:v1.2.3", ("custom-registry/my-image", "v1.2.3")),
        ("custom-registry/my-image", ("custom-registry/my-image", "latest")),
        ("my-image:tag", ("my-image", "tag")),
        ("my-image", ("my-image", "latest")),
    ]

    for image_string, expected in test_cases:
        args = parser.parse_args(['start', 'test', '--image', image_string])
        assert args.image == image_string

        # Test parsing logic
        if args.image:
            if ':' in args.image:
                image_name, image_tag = args.image.rsplit(':', 1)
            else:
                image_name = args.image
                image_tag = "latest"

            assert image_name == expected[0]
            assert image_tag == expected[1]


def test_end_to_end_flow():
    """Test complete end-to-end flow"""
    from vsclaude.vsclaude.config import ConfigManager
    from vsclaude.vsclaude.compose import generate
    import tempfile

    # Use temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        config_manager = ConfigManager(config_dir=temp_dir)

        # Set custom default image
        global_config = config_manager.load_global_config()
        global_config["default_image"] = "custom-registry/default-image:stable"
        config_manager._save_config(global_config)

        # Generate compose config using config manager's default image
        default_image = config_manager.get_default_image()

        # Parse image string
        if ':' in default_image:
            image_name, image_tag = default_image.rsplit(':', 1)
        else:
            image_name = default_image
            image_tag = "latest"

        config = generate(
            "test-instance",
            8080,
            {},
            image_name=image_name,
            image_tag=image_tag,
            enabled_volumes=["/config", "/workspace"]
        )

        service = config["services"]["vscode-claude"]
        assert service["image"] == "custom-registry/default-image:stable"


if __name__ == "__main__":
    # Run tests
    test_config_manager_default_image()
    print("✓ ConfigManager default image test passed")

    test_compose_generate_with_custom_image()
    print("✓ Compose generate with custom image test passed")

    test_cli_image_flag_integration()
    print("✓ CLI image flag integration test passed")

    test_backward_compatibility()
    print("✓ Backward compatibility test passed")

    test_image_parsing_logic()
    print("✓ Image parsing logic test passed")

    test_end_to_end_flow()
    print("✓ End-to-end flow test passed")

    print("\n✅ All integration tests passed!")