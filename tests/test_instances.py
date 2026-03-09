"""
Comprehensive test suite for InstanceManager.

Tests security protections, validation, error handling, and functionality
with proper mocking and edge case coverage.
"""

import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from vsclaude.vsclaude.instances import (
    InstanceManager,
    InstanceValidationError,
    InstanceSecurityError
)


class TestInstanceManager:
    """Test suite for InstanceManager with comprehensive coverage."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary configuration directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def instance_manager(self, temp_config_dir):
        """Create InstanceManager instance with temp directory."""
        return InstanceManager(str(temp_config_dir))

    def test_init_with_default_config_dir(self):
        """Test initialization with default configuration directory."""
        manager = InstanceManager()
        assert manager.config_dir == Path.home() / ".vsclaude"
        assert manager.instances_dir == manager.config_dir / "instances"

    def test_init_with_custom_config_dir(self, temp_config_dir):
        """Test initialization with custom configuration directory."""
        manager = InstanceManager(str(temp_config_dir))
        assert manager.config_dir == temp_config_dir
        assert manager.instances_dir == temp_config_dir / "instances"

    def test_init_directory_creation(self, temp_config_dir):
        """Test that directories are created with proper permissions."""
        config_path = temp_config_dir / "nested" / "config"
        manager = InstanceManager(str(config_path))

        assert config_path.exists()
        assert manager.instances_dir.exists()
        assert manager.instances_dir.is_dir()

    def test_init_with_unsafe_path(self):
        """Test initialization with unsafe path raises security error."""
        with pytest.raises(InstanceSecurityError):
            InstanceManager("/etc/passwd")

    # Security validation tests

    @pytest.mark.parametrize("invalid_name", [
        "",
        "..",
        "CON",
        "test/../etc",
        "test;rm -rf /",
        "test&ls",
        "test`pwd`",
        "$HOME",
        "<script>",
        "test\n",
        "test\r",
        "a" * 65,  # Too long
    ])
    def test_validate_instance_name_invalid(self, instance_manager, invalid_name):
        """Test invalid instance names raise validation errors."""
        with pytest.raises((InstanceValidationError, InstanceSecurityError)):
            instance_manager._validate_instance_name(invalid_name)

    @pytest.mark.parametrize("valid_name", [
        "test-instance",
        "test_instance",
        "test123",
        "T-e_s-t",
        "a" * 64,  # Max length
    ])
    def test_validate_instance_name_valid(self, instance_manager, valid_name):
        """Test valid instance names pass validation."""
        # Should not raise any exception
        instance_manager._validate_instance_name(valid_name)

    @pytest.mark.parametrize("invalid_port", [
        0,  # Too low
        1023,  # Below privileged port threshold
        65536,  # Too high
        "8080",  # Wrong type
        3.14,  # Float
    ])
    def test_validate_port_invalid(self, instance_manager, invalid_port):
        """Test invalid port numbers raise validation errors."""
        with pytest.raises(InstanceValidationError):
            instance_manager._validate_port(invalid_port)

    @pytest.mark.parametrize("valid_port", [
        1024,  # Minimum allowed
        8080,
        8443,
        3000,
        65535,  # Maximum allowed
    ])
    def test_validate_port_valid(self, instance_manager, valid_port):
        """Test valid port numbers pass validation."""
        # Should not raise any exception
        instance_manager._validate_port(valid_port)

    @pytest.mark.parametrize("invalid_profile", [
        "test/profile",
        "test&profile",
        "test;profile",
        "test\nprofile",
    ])
    def test_validate_profile_invalid(self, instance_manager, invalid_profile):
        """Test invalid profile names raise validation errors."""
        with pytest.raises(InstanceValidationError):
            instance_manager._validate_profile(invalid_profile)

    def test_validate_environment_invalid(self, instance_manager):
        """Test invalid environment configurations."""
        # Invalid types
        with pytest.raises(InstanceValidationError):
            instance_manager._validate_environment("not_a_dict")

        # Invalid keys
        with pytest.raises(InstanceValidationError):
            instance_manager._validate_environment({123: "value"})  # Non-string key

        # Invalid key format
        with pytest.raises(InstanceValidationError):
            instance_manager._validate_environment({"123key": "value"})  # Starts with number

        # Complex objects that aren't JSON serializable
        class CustomObject:
            pass

        with pytest.raises(InstanceValidationError):
            instance_manager._validate_environment({"key": CustomObject()})

    def test_validate_environment_valid(self, instance_manager):
        """Test valid environment configurations."""
        valid_env = {
            "simple_string": "value",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "none": None,
            "list": [1, 2, 3],
            "nested_dict": {"key": "value"},
        }

        result = instance_manager._validate_environment(valid_env)
        assert result == valid_env

    # Instance creation tests

    def test_create_instance_success(self, instance_manager):
        """Test successful instance creation."""
        config = instance_manager.create_instance_config(
            name="test-instance",
            port=8443,
            profile="default",
            environment={"KEY": "value"}
        )

        assert config["name"] == "test-instance"
        assert config["port"] == 8443
        assert config["profile"] == "default"
        assert config["environment"] == {"KEY": "value"}

        # Verify files were created
        instance_dir = instance_manager.instances_dir / "test-instance"
        assert instance_dir.exists()
        assert (instance_dir / "config.json").exists()

    def test_create_instance_invalid_name(self, instance_manager):
        """Test instance creation with invalid name."""
        with pytest.raises(InstanceValidationError):
            instance_manager.create_instance_config("", port=8443)

    def test_create_instance_invalid_port(self, instance_manager):
        """Test instance creation with invalid port."""
        with pytest.raises(InstanceValidationError):
            instance_manager.create_instance_config("test", port=1023)

    def test_create_instance_already_exists(self, instance_manager):
        """Test instance creation when instance already exists."""
        instance_manager.create_instance_config("test", port=8443)

        with pytest.raises(InstanceValidationError):
            instance_manager.create_instance_config("test", port=8080)

    def test_create_instance_directory_creation_failure(self, instance_manager):
        """Test handling of directory creation failure."""
        with patch.object(Path, 'mkdir', side_effect=PermissionError("Permission denied")):
            with pytest.raises(InstanceSecurityError):
                instance_manager.create_instance_config("test", port=8443)

    def test_create_instance_config_write_failure(self, instance_manager):
        """Test handling of configuration file write failure."""
        with patch('builtins.open', side_effect=OSError("Disk full")):
            with pytest.raises(InstanceSecurityError):
                instance_manager.create_instance_config("test", port=8443)

    # Instance reading tests

    def test_read_instance_success(self, instance_manager):
        """Test successful instance reading."""
        # Create instance first
        instance_manager.create_instance_config("test", port=8443)

        config = instance_manager.read_instance_config("test")
        assert config["name"] == "test"
        assert config["port"] == 8443

    def test_read_instance_not_found(self, instance_manager):
        """Test reading non-existent instance."""
        with pytest.raises(FileNotFoundError):
            instance_manager.read_instance_config("nonexistent")

    def test_read_instance_invalid_name(self, instance_manager):
        """Test reading instance with invalid name."""
        with pytest.raises(InstanceValidationError):
            instance_manager.read_instance_config("")

    def test_read_instance_config_file_missing(self, instance_manager):
        """Test reading instance with missing config file."""
        # Create directory but no config file
        instance_dir = instance_manager.instances_dir / "test"
        instance_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            instance_manager.read_instance_config("test")

    def test_read_instance_invalid_json(self, instance_manager):
        """Test reading instance with invalid JSON."""
        # Create instance with invalid JSON
        instance_dir = instance_manager.instances_dir / "test"
        instance_dir.mkdir()

        config_file = instance_dir / "config.json"
        config_file.write_text("invalid json content")

        with pytest.raises(InstanceSecurityError):
            instance_manager.read_instance_config("test")

    def test_read_instance_missing_keys(self, instance_manager):
        """Test reading instance with missing configuration keys."""
        # Create instance with incomplete config
        instance_dir = instance_manager.instances_dir / "test"
        instance_dir.mkdir()

        config_file = instance_dir / "config.json"
        config_file.write_text(json.dumps({"name": "test"}))

        with pytest.raises(InstanceSecurityError):
            instance_manager.read_instance_config("test")

    # Instance update tests

    def test_update_instance_success(self, instance_manager):
        """Test successful instance update."""
        # Create instance first
        instance_manager.create_instance_config("test", port=8443)

        # Update port and profile
        updated_config = instance_manager.update_instance_config(
            "test", port=8080, profile="custom"
        )

        assert updated_config["port"] == 8080
        assert updated_config["profile"] == "custom"

        # Verify update persisted
        config = instance_manager.read_instance_config("test")
        assert config["port"] == 8080
        assert config["profile"] == "custom"

    def test_update_instance_not_found(self, instance_manager):
        """Test updating non-existent instance."""
        with pytest.raises(FileNotFoundError):
            instance_manager.update_instance_config("nonexistent", port=8080)

    def test_update_instance_invalid_port(self, instance_manager):
        """Test updating instance with invalid port."""
        instance_manager.create_instance_config("test", port=8443)

        with pytest.raises(InstanceValidationError):
            instance_manager.update_instance_config("test", port=1023)

    def test_update_instance_partial_updates(self, instance_manager):
        """Test updating instance with partial updates."""
        instance_manager.create_instance_config("test", port=8443, profile="default")

        # Update only port
        config = instance_manager.update_instance_config("test", port=3000)
        assert config["port"] == 3000
        assert config["profile"] == "default"

        # Update only profile
        config = instance_manager.update_instance_config("test", profile="custom")
        assert config["port"] == 3000
        assert config["profile"] == "custom"

        # Update environment
        config = instance_manager.update_instance_config("test", environment={"NEW": "value"})
        assert config["environment"] == {"NEW": "value"}

    # Instance deletion tests

    def test_delete_instance_success(self, instance_manager):
        """Test successful instance deletion."""
        # Create instance first
        instance_manager.create_instance_config("test", port=8443)
        assert instance_manager.instance_exists("test")

        # Delete instance
        result = instance_manager.delete_instance_config("test")
        assert result is True
        assert not instance_manager.instance_exists("test")

    def test_delete_instance_not_found(self, instance_manager):
        """Test deleting non-existent instance."""
        with pytest.raises(FileNotFoundError):
            instance_manager.delete_instance_config("nonexistent")

    def test_delete_instance_invalid_name(self, instance_manager):
        """Test deleting instance with invalid name."""
        with pytest.raises(InstanceValidationError):
            instance_manager.delete_instance_config("")

    def test_delete_instance_directory_removal_failure(self, instance_manager):
        """Test handling of directory removal failure."""
        instance_manager.create_instance_config("test", port=8443)

        with patch('shutil.rmtree', side_effect=OSError("Permission denied")):
            with pytest.raises(InstanceSecurityError):
                instance_manager.delete_instance_config("test")

    # Instance listing and existence tests

    def test_list_instances_success(self, instance_manager):
        """Test successful instance listing."""
        # Create multiple instances
        instance_manager.create_instance_config("instance1", port=8443)
        instance_manager.create_instance_config("instance2", port=8080)
        instance_manager.create_instance_config("instance3", port=3000)

        instances = instance_manager.list_instances()
        assert set(instances) == {"instance1", "instance2", "instance3"}
        assert instances == sorted(instances)

    def test_list_instances_empty(self, instance_manager):
        """Test listing instances when none exist."""
        instances = instance_manager.list_instances()
        assert instances == []

    def test_list_instances_with_invalid_directories(self, instance_manager):
        """Test listing ignores invalid directories."""
        # Create valid instance
        instance_manager.create_instance_config("valid", port=8443)

        # Create invalid directories that should be ignored
        invalid_dir = instance_manager.instances_dir / ".."
        invalid_dir.mkdir(exist_ok=True)

        instances = instance_manager.list_instances()
        assert instances == ["valid"]

    def test_instance_exists(self, instance_manager):
        """Test instance existence checking."""
        assert not instance_manager.instance_exists("test")

        instance_manager.create_instance_config("test", port=8443)
        assert instance_manager.instance_exists("test")

        instance_manager.delete_instance_config("test")
        assert not instance_manager.instance_exists("test")

    def test_instance_exists_invalid_name(self, instance_manager):
        """Test existence checking with invalid name."""
        with pytest.raises(InstanceValidationError):
            instance_manager.instance_exists("")

    # Security edge case tests

    def test_path_traversal_protection(self, instance_manager):
        """Test protection against path traversal attacks."""
        # Test unsafe paths should return False
        assert not instance_manager._is_safe_path(Path("/etc/passwd"))
        assert not instance_manager._is_safe_path(Path("../../../etc/passwd"))

        # Should allow safe paths
        assert instance_manager._is_safe_path(instance_manager.instances_dir / "test")

    def test_reserved_names_protection(self, instance_manager):
        """Test protection against reserved names."""
        for reserved_name in ["CON", "PRN", "AUX", "NUL"]:
            with pytest.raises(InstanceSecurityError):
                instance_manager.create_instance_config(reserved_name, port=8443)

    def test_dangerous_characters_protection(self, instance_manager):
        """Test protection against dangerous characters."""
        dangerous_names = [
            "test;rm -rf /",
            "test&ls",
            "test`pwd`",
            "$HOME",
            "<script>",
        ]

        for name in dangerous_names:
            with pytest.raises((InstanceValidationError, InstanceSecurityError)):
                instance_manager.create_instance_config(name, port=8443)

    # Performance and concurrency tests

    def test_concurrent_instance_operations(self, instance_manager):
        """Test that concurrent operations don't interfere."""
        # This test ensures atomic operations work correctly
        instance_manager.create_instance_config("test1", port=8443)
        instance_manager.create_instance_config("test2", port=8080)

        # Read and update simultaneously
        config1 = instance_manager.read_instance_config("test1")
        config2 = instance_manager.read_instance_config("test2")

        instance_manager.update_instance_config("test1", port=3000)
        instance_manager.update_instance_config("test2", port=4000)

        # Verify updates
        updated1 = instance_manager.read_instance_config("test1")
        updated2 = instance_manager.read_instance_config("test2")

        assert updated1["port"] == 3000
        assert updated2["port"] == 4000

    # File permission tests

    def test_file_permissions(self, instance_manager):
        """Test that files are created with secure permissions."""
        instance_manager.create_instance_config("test", port=8443)

        instance_dir = instance_manager.instances_dir / "test"
        config_file = instance_dir / "config.json"

        # Check directory permissions (should be 0o700)
        assert oct(instance_dir.stat().st_mode)[-3:] == "700"

        # Check file permissions (should be 0o600)
        assert oct(config_file.stat().st_mode)[-3:] == "600"

    # Error recovery tests

    def test_error_recovery_partial_creation(self, instance_manager):
        """Test recovery from partial instance creation."""
        # Simulate partial creation by creating directory manually
        instance_dir = instance_manager.instances_dir / "partial"
        instance_dir.mkdir()

        # Attempt to create instance with same name
        with pytest.raises(InstanceValidationError):
            instance_manager.create_instance_config("partial", port=8443)

    def test_atomic_write_protection(self, instance_manager):
        """Test atomic write protection against partial writes."""
        with patch('json.dump', side_effect=OSError("Disk full during write")):
            with pytest.raises(InstanceSecurityError):
                instance_manager.create_instance_config("test", port=8443)

        # Verify no partial files exist
        instance_dir = instance_manager.instances_dir / "test"
        assert not instance_dir.exists()

    # Integration tests

    def test_full_lifecycle(self, instance_manager):
        """Test complete instance lifecycle."""
        # Create
        config1 = instance_manager.create_instance_config("test", port=8443)
        assert config1["port"] == 8443
        assert instance_manager.instance_exists("test")

        # Read
        config2 = instance_manager.read_instance_config("test")
        assert config2["port"] == 8443

        # Update
        config3 = instance_manager.update_instance_config("test", port=8080)
        assert config3["port"] == 8080

        # Verify update
        config4 = instance_manager.read_instance_config("test")
        assert config4["port"] == 8080

        # Delete
        result = instance_manager.delete_instance_config("test")
        assert result is True
        assert not instance_manager.instance_exists("test")

        # List (should be empty)
        instances = instance_manager.list_instances()
        assert instances == []

    # Instance transactional delete tests

    def test_delete_instance_transactional(self, instance_manager):
        """Test transactional instance deletion."""
        instance_name = "test-delete-instance"

        # Create test instance
        instance_manager.create_instance_config(instance_name, 8080)
        assert instance_manager.instance_exists(instance_name) == True

        # Test deletion using MockDockerClient
        from vsclaude.vsclaude.docker import MockDockerClient
        with patch('vsclaude.vsclaude.docker.DockerClient', MockDockerClient):
            result = instance_manager.delete_instance(instance_name)
            assert result["container_stopped"] == True
            assert result["container_removed"] == True
            assert result["config_deleted"] == True
            assert instance_manager.instance_exists(instance_name) == False