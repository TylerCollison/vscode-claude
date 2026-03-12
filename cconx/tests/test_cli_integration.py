import pytest
from unittest.mock import patch, MagicMock, mock_open
import argparse
import json
import sys
import os

# Add path to import modules correctly
sys.path.insert(0, os.path.join(os.getcwd(), 'cconx'))


def test_start_command_with_valid_custom_image():
    """Test start command with valid custom image via --image flag"""
    from cconx.cconx.cli import start_command

    # Create mock arguments with custom image
    args = argparse.Namespace(
        name="test-instance",
        port=None,
        env=[],
        env_append=[],
        image="custom-registry/my-image:v1.2.3"
    )

    # Mock all dependencies
    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager, \
         patch('cconx.cconx.compose.generate') as mock_generate, \
         patch('cconx.cconx.docker.DockerClient') as MockDockerClient:

        # Mock ConfigManager
        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.format_ide_address.return_value = "http://localhost:8000"

        # Mock PortManager
        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        # Mock InstanceManager
        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "test-instance", "port": 8000
        }

        # Mock Docker client
        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        # Mock compose generation
        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "custom-registry/my-image:v1.2.3",
                    "ports": ["8000:8000"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        # Capture print output
        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify image validation was called
            mock_generate.assert_called_once()
            call_args, call_kwargs = mock_generate.call_args

            # Check if image_name and image_tag were passed correctly
            if 'image_name' in call_kwargs:
                assert call_kwargs['image_name'] == "custom-registry/my-image"
                assert call_kwargs['image_tag'] == "v1.2.3"
            else:
                # Check positional arguments
                assert call_args[0] == "test-instance"  # instance_name
                assert call_args[1] == 8000             # port
                # Image parameters would be in kwargs

            # Verify success messages
            mock_print.assert_any_call("Container 'cconx-test-instance' started successfully")
            mock_print.assert_any_call("Instance 'test-instance' configured on port 8000")


def test_start_command_with_default_image():
    """Test start command using default image from ConfigManager"""
    from cconx.cconx.cli import start_command

    # Create mock arguments without --image flag
    args = argparse.Namespace(
        name="test-instance",
        port=None,
        env=[],
        env_append=[],
        image=None
    )

    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager, \
         patch('cconx.cconx.compose.generate') as mock_generate, \
         patch('cconx.cconx.docker.DockerClient') as MockDockerClient:

        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.get_default_image.return_value = "tylercollison2089/vscode-claude:latest"
        mock_config_manager.format_ide_address.return_value = "http://localhost:8000"

        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "test-instance", "port": 8000
        }

        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "tylercollison2089/vscode-claude:latest",
                    "ports": ["8000:8000"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify ConfigManager.get_default_image was called
            mock_config_manager.get_default_image.assert_called_once()

            # Verify default image was used
            call_kwargs = mock_generate.call_args[1]
            assert call_kwargs['image_name'] == "tylercollison2089/vscode-claude"
            assert call_kwargs['image_tag'] == "latest"


def test_start_command_with_invalid_image_format():
    """Test start command with invalid image format that fails validation"""
    from cconx.cconx.cli import start_command
    from cconx.cconx.compose import _validate_image_name

    # Create mock arguments with invalid image
    args = argparse.Namespace(
        name="test-instance",
        port=None,
        env=[],
        env_append=[],
        image="InvalidImage"  # Contains uppercase letters
    )

    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager:

        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True
        }
        mock_config_manager.get_global_environment.return_value = {}

        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "test-instance", "port": 8000
        }

        # Expect ValueError from _validate_image_name
        with pytest.raises(ValueError, match="image_name cannot contain uppercase letters"):
            start_command(args)


def test_start_command_image_validation_error_handling():
    """Test that image validation errors are properly propagated"""
    from cconx.cconx.cli import start_command

    args = argparse.Namespace(
        name="test-instance",
        port=None,
        env=[],
        env_append=[],
        image="-invalid-image"  # Invalid starting character
    )

    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager:

        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True
        }
        mock_config_manager.get_global_environment.return_value = {}

        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "test-instance", "port": 8000
        }

        # Expect ValueError for invalid image name format
        with pytest.raises(ValueError, match="image_name cannot start with"):
            start_command(args)


def test_start_command_with_image_no_tag():
    """Test start command with image name but no tag (should default to 'latest')"""
    from cconx.cconx.cli import start_command

    args = argparse.Namespace(
        name="test-instance",
        port=None,
        env=[],
        env_append=[],
        image="custom-image"  # No tag specified
    )

    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager, \
         patch('cconx.cconx.compose.generate') as mock_generate, \
         patch('cconx.cconx.docker.DockerClient') as MockDockerClient:

        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.format_ide_address.return_value = "http://localhost:8000"

        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "test-instance", "port": 8000
        }

        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "custom-image:latest",
                    "ports": ["8000:8000"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify image parsing and default tag
            call_kwargs = mock_generate.call_args[1]
            assert call_kwargs['image_name'] == "custom-image"
            assert call_kwargs['image_tag'] == "latest"


def test_start_command_validate_image_called():
    """Test that _validate_image_name is actually called for custom images"""
    from cconx.cconx.cli import start_command

    args = argparse.Namespace(
        name="test-instance",
        port=None,
        env=[],
        env_append=[],
        image="valid-image:v1.0"
    )

    with patch('cconx.cconx.config.ConfigManager') as MockConfigManager, \
         patch('cconx.cconx.ports.PortManager') as MockPortManager, \
         patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager, \
         patch('cconx.cconx.compose.generate') as mock_generate, \
         patch('cconx.cconx.docker.DockerClient') as MockDockerClient, \
         patch('cconx.cconx.compose._validate_image_name') as mock_validate:

        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.format_ide_address.return_value = "http://localhost:8000"

        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8000

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "test-instance", "port": 8000
        }

        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "valid-image:v1.0",
                    "ports": ["8000:8000"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify validation was called with correct image name
            mock_validate.assert_called_once_with("valid-image")


def test_status_command_with_images():
    """Test status command showing instances with custom images"""
    from cconx.cconx.cli import status_command

    args = argparse.Namespace()

    with patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager, \
         patch('cconx.cconx.docker.DockerClient') as MockDockerClient, \
         patch('cconx.cconx.config.ConfigManager') as MockConfigManager:

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.instances_dir.exists.return_value = True

        # Mock instance directory structure
        mock_instance_dir = MagicMock()
        mock_instance_dir.is_dir.return_value = True
        mock_instance_dir.name = "test-instance"

        mock_config_file = MagicMock()
        mock_config_file.exists.return_value = True
        mock_instance_dir.__truediv__.return_value = mock_config_file

        mock_instance_manager.instances_dir.iterdir.return_value = [mock_instance_dir]

        mock_docker_client = MockDockerClient.return_value
        mock_docker_client.is_container_running.return_value = True

        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.format_ide_address.return_value = "http://localhost:8000"

        # Mock config content
        mock_config_content = {
            "name": "test-instance",
            "port": 8000,
            "image": "custom-image:v1.0"  # Include image info
        }
        mock_file_content = json.dumps(mock_config_content)

        with patch('builtins.open', mock_open(read_data=mock_file_content)), \
             patch('builtins.print') as mock_print:
            status_command(args)

            # Verify status includes IDE address
            mock_print.assert_called_with("test-instance: RUNNING - http://localhost:8000")


def test_stop_command():
    """Test stop command functionality"""
    from cconx.cconx.cli import stop_command
    import docker.errors

    args = argparse.Namespace(name="test-instance")

    with patch('cconx.cconx.docker.DockerClient') as MockDockerClient:
        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.get.return_value = mock_container

        with patch('builtins.print') as mock_print:
            stop_command(args)

            # Verify container stop was called
            mock_docker_client.client.containers.get.assert_called_with("cconx-test-instance")
            mock_container.stop.assert_called_once()
            mock_print.assert_called_with("Stopped instance 'test-instance'")


def test_stop_command_instance_not_found():
    """Test stop command when instance doesn't exist"""
    from cconx.cconx.cli import stop_command
    import docker.errors

    args = argparse.Namespace(name="nonexistent-instance")

    with patch('cconx.cconx.docker.DockerClient') as MockDockerClient:
        mock_docker_client = MockDockerClient.return_value
        mock_docker_client.client.containers.get.side_effect = docker.errors.NotFound("Container not found")

        with patch('builtins.print') as mock_print:
            stop_command(args)

            mock_print.assert_called_with("Instance 'nonexistent-instance' not found")


def test_delete_command_success():
    """Test successful deletion scenario with mocked Docker operations"""
    from cconx.cconx.cli import delete_command
    from cconx.cconx.instances import InstanceManager
    from unittest.mock import patch, MagicMock
    import argparse

    # Create mock arguments
    args = argparse.Namespace(name="test-instance")

    # Mock Docker operations and InstanceManager
    with patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager:
        mock_manager = MockInstanceManager.return_value
        mock_manager.delete_instance.return_value = {
            "container_stopped": True,
            "container_removed": True,
            "config_deleted": True
        }

        # Capture print output
        with patch('builtins.print') as mock_print:
            result = delete_command(args)

            # Verify InstanceManager.delete_instance was called
            mock_manager.delete_instance.assert_called_once_with("test-instance")

            # Verify success message was printed
            mock_print.assert_called_once_with(
                "Deleted instance 'test-instance': stopped container and removed container and deleted configuration"
            )


def test_delete_command_partial_success():
    """Test deletion when only some operations succeed"""
    from cconx.cconx.cli import delete_command
    from cconx.cconx.instances import InstanceManager
    from unittest.mock import patch
    import argparse

    args = argparse.Namespace(name="test-instance")

    with patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager:
        mock_manager = MockInstanceManager.return_value
        mock_manager.delete_instance.return_value = {
            "container_stopped": False,
            "container_removed": False,
            "config_deleted": True
        }

        with patch('builtins.print') as mock_print:
            delete_command(args)

            mock_print.assert_called_once_with(
                "Deleted instance 'test-instance': deleted configuration"
            )


def test_delete_command_instance_not_found():
    """Test deletion when instance doesn't exist"""
    from cconx.cconx.cli import delete_command
    from cconx.cconx.instances import InstanceManager
    from unittest.mock import patch
    import argparse

    args = argparse.Namespace(name="nonexistent-instance")

    with patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager:
        mock_manager = MockInstanceManager.return_value
        mock_manager.delete_instance.return_value = {
            "container_stopped": False,
            "container_removed": False,
            "config_deleted": False
        }

        with patch('builtins.print') as mock_print:
            delete_command(args)

            mock_print.assert_called_once_with(
                "Instance 'nonexistent-instance' not found or already deleted"
            )


def test_delete_command_docker_unavailable():
    """Test deletion when Docker is unavailable"""
    from cconx.cconx.cli import delete_command
    from cconx.cconx.instances import InstanceManager
    from unittest.mock import patch
    import argparse

    args = argparse.Namespace(name="test-instance")

    with patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager:
        mock_manager = MockInstanceManager.return_value
        # Simulate Docker error by returning partial success
        mock_manager.delete_instance.return_value = {
            "container_stopped": False,
            "container_removed": False,
            "config_deleted": True  # Config deletion succeeded despite Docker issues
        }

        with patch('builtins.print') as mock_print:
            delete_command(args)

            mock_print.assert_called_once_with(
                "Deleted instance 'test-instance': deleted configuration"
            )


def test_delete_command_error_handling():
    """Test error handling when unexpected exceptions occur"""
    from cconx.cconx.cli import delete_command
    from cconx.cconx.instances import InstanceManager
    from unittest.mock import patch
    import argparse

    args = argparse.Namespace(name="test-instance")

    with patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager:
        mock_manager = MockInstanceManager.return_value
        # Simulate unexpected exception during deletion
        mock_manager.delete_instance.side_effect = Exception("Unexpected error")

        with patch('builtins.print') as mock_print:
            delete_command(args)

            # Verify error message was printed
            mock_print.assert_called_once_with(
                "Error deleting instance 'test-instance': Unexpected error"
            )


def test_delete_command_status_message_variations():
    """Test different status message combinations"""
    from cconx.cconx.cli import delete_command
    from cconx.cconx.instances import InstanceManager
    from unittest.mock import patch
    import argparse

    args = argparse.Namespace(name="test-instance")

    test_cases = [
        ({"container_stopped": True, "container_removed": False, "config_deleted": False},
         "stopped container"),
        ({"container_stopped": False, "container_removed": True, "config_deleted": False},
         "removed container"),
        ({"container_stopped": False, "container_removed": False, "config_deleted": True},
         "deleted configuration"),
        ({"container_stopped": True, "container_removed": True, "config_deleted": False},
         "stopped container and removed container"),
        ({"container_stopped": True, "container_removed": False, "config_deleted": True},
         "stopped container and deleted configuration"),
        ({"container_stopped": False, "container_removed": True, "config_deleted": True},
         "removed container and deleted configuration"),
    ]

    for result, expected_message in test_cases:
        with patch('cconx.cconx.instances.InstanceManager') as MockInstanceManager:
            mock_manager = MockInstanceManager.return_value
            mock_manager.delete_instance.return_value = result

            with patch('builtins.print') as mock_print:
                delete_command(args)

                expected_full_message = f"Deleted instance 'test-instance': {expected_message}"
                mock_print.assert_called_once_with(expected_full_message)

                # Reset mock for next iteration
                mock_print.reset_mock()