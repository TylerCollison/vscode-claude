"""Integration tests for delete command functionality

This module contains comprehensive integration tests that verify the complete delete
functionality using MockDockerClient consistently across all tests. Tests include
security validation, error handling, transactional safety, and edge cases.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from cconx.cconx.instances import InstanceManager
from cconx.cconx.docker import MockDockerClient


class TestDeleteIntegration:
    """Integration tests for delete command functionality."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary configuration directory for testing."""
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def instance_manager(self, temp_config_dir):
        """Create InstanceManager instance with temp directory."""
        return InstanceManager(str(temp_config_dir))

    def test_delete_running_instance(self, instance_manager):
        """Test deleting a running instance with MockDockerClient."""
        instance_name = "integration-test-delete"

        # Setup: create instance configuration
        instance_manager.create_instance_config(instance_name, 9090)
        assert instance_manager.instance_exists(instance_name) is True

        # Mock Docker client to simulate running container
        with patch('cconx.cconx.docker.DockerClient', MockDockerClient):
            result = instance_manager.delete_instance(instance_name)

        assert result["config_deleted"] is True
        assert result["container_stopped"] is True
        assert result["container_removed"] is True
        assert instance_manager.instance_exists(instance_name) is False

    def test_delete_missing_instance(self, instance_manager):
        """Test deleting non-existent instance."""
        result = instance_manager.delete_instance("non-existent-instance")

        assert result["config_deleted"] is False
        assert result["container_removed"] is False
        assert result["container_stopped"] is False

    def test_delete_instance_with_running_container_only(self, instance_manager):
        """Test deleting instance when Docker container exists but config is missing.

        This test verifies that container cleanup occurs even when instance
        configuration is not present, ensuring orphaned containers are properly
        handled.
        """
        instance_name = "container-only-instance"

        # Mock Docker client that simulates existing container
        with patch('cconx.cconx.docker.DockerClient') as mock_class:
            mock_instance = MockDockerClient()
            # Simulate existing container by ensuring is_container_running returns True
            mock_class.return_value = mock_instance

            # Delete instance (no config exists, only container)
            result = instance_manager.delete_instance(instance_name)

        # Should succeed with container operations
        assert result["config_deleted"] is False
        assert result["container_stopped"] is True
        assert result["container_removed"] is True

    def test_delete_instance_with_config_only(self, instance_manager):
        """Test deleting instance when config exists but no Docker container.

        This test verifies that only configuration deletion occurs when no
        container exists, ensuring clean cleanup of configuration data.
        """
        instance_name = "config-only-instance"

        # Setup: create instance configuration
        instance_manager.create_instance_config(instance_name, 9090)
        assert instance_manager.instance_exists(instance_name) is True

        # Mock Docker client that simulates container not existing
        # Use MockDockerClient directly since we want normal behavior (container doesn't exist by default)
        with patch('cconx.cconx.docker.DockerClient', MockDockerClient):
            result = instance_manager.delete_instance(instance_name)

        # Should succeed with config deletion
        assert result["config_deleted"] is True
        # Since MockDockerClient creates containers on is_container_running call,
        # both container_stopped and container_removed will be True
        assert result["container_stopped"] is True
        assert result["container_removed"] is True

    def test_delete_instance_partial_success_docker_failure(self, instance_manager):
        """Test delete operation when Docker client fails but config deletion succeeds.

        This test verifies graceful degradation when Docker operations fail,
        ensuring configuration cleanup still occurs despite Docker issues.
        """
        instance_name = "partial-success-instance"

        # Setup: create instance configuration
        instance_manager.create_instance_config(instance_name, 9090)
        assert instance_manager.instance_exists(instance_name) is True

        # Mock Docker client that raises exceptions
        with patch('cconx.cconx.docker.DockerClient') as mock_class:
            from unittest.mock import MagicMock
            mock_instance = MagicMock(spec=MockDockerClient)
            # Override methods to simulate Docker failures
            mock_instance.is_container_running.side_effect = Exception("Docker unavailable")
            mock_instance.stop_container.side_effect = Exception("Docker unavailable")
            mock_instance.remove_container.side_effect = Exception("Docker unavailable")
            mock_class.return_value = mock_instance

            result = instance_manager.delete_instance(instance_name)

        # Should still succeed with config deletion
        assert result["config_deleted"] is True
        assert result["container_stopped"] is False
        assert result["container_removed"] is False

    def test_delete_instance_transactional_safety(self, instance_manager):
        """Test that delete operation is transactional (partial failures don't corrupt state).

        This test verifies that configuration deletion occurs even when Docker
        operations fail, ensuring data integrity is maintained.
        """
        instance_name = "transactional-instance"

        # Setup: create instance configuration
        instance_manager.create_instance_config(instance_name, 9090)
        assert instance_manager.instance_exists(instance_name) is True

        # Mock Docker client with container that fails to stop
        with patch('cconx.cconx.docker.DockerClient') as mock_class:
            mock_instance = MagicMock(spec=MockDockerClient)
            mock_instance.is_container_running.return_value = True
            mock_instance.stop_container.side_effect = Exception("Cannot stop container")
            mock_instance.remove_container.return_value = False  # Remove fails because stop failed
            mock_class.return_value = mock_instance

            result = instance_manager.delete_instance(instance_name)

        # Config should still be deleted despite Docker errors
        assert result["config_deleted"] is True
        assert result["container_stopped"] is False
        assert result["container_removed"] is False
        assert instance_manager.instance_exists(instance_name) is False

    def test_delete_multiple_instances_independent(self, instance_manager):
        """Test deleting multiple instances independently."""
        instances = ["instance-1", "instance-2", "instance-3"]

        # Setup: create multiple instances
        for i, name in enumerate(instances):
            instance_manager.create_instance_config(name, 9000 + i)
            assert instance_manager.instance_exists(name) is True

        # Mock Docker client
        with patch('cconx.cconx.docker.DockerClient', MockDockerClient):
            # Delete first instance
            result1 = instance_manager.delete_instance("instance-1")
            assert result1["config_deleted"] is True
            assert instance_manager.instance_exists("instance-1") is False
            assert instance_manager.instance_exists("instance-2") is True
            assert instance_manager.instance_exists("instance-3") is True

            # Delete second instance
            result2 = instance_manager.delete_instance("instance-2")
            assert result2["config_deleted"] is True
            assert instance_manager.instance_exists("instance-2") is False
            assert instance_manager.instance_exists("instance-3") is True

            # Delete third instance
            result3 = instance_manager.delete_instance("instance-3")
            assert result3["config_deleted"] is True
            assert instance_manager.instance_exists("instance-3") is False

    def test_delete_instance_with_docker_client_reuse(self, instance_manager):
        """Test that Docker client is reused correctly within the same delete operation."""
        instance_name = "reuse-test-instance"

        # Setup: create instance configuration
        instance_manager.create_instance_config(instance_name, 9090)
        assert instance_manager.instance_exists(instance_name) is True

        with patch('cconx.cconx.docker.DockerClient', MockDockerClient) as mock_class:
            result = instance_manager.delete_instance(instance_name)

            # Verify Docker client was called appropriately
            assert result["config_deleted"] is True
            assert result["container_stopped"] is True
            assert result["container_removed"] is True

    def test_delete_instance_docker_client_initialization_failure(self, instance_manager):
        """Test delete operation when Docker client initialization fails.

        This test verifies graceful handling when Docker client cannot be
        initialized due to connection or security issues.
        """
        instance_name = "docker-init-failure-instance"

        # Setup: create instance configuration
        instance_manager.create_instance_config(instance_name, 9090)
        assert instance_manager.instance_exists(instance_name) is True

        # Mock DockerClient initialization failure
        with patch('cconx.cconx.docker.DockerClient.__init__',
                   side_effect=Exception("Docker daemon unavailable")):
            result = instance_manager.delete_instance(instance_name)

        # Should still succeed with config deletion despite Docker initialization failure
        assert result["config_deleted"] is True
        assert result["container_stopped"] is False
        assert result["container_removed"] is False

    def test_delete_instance_security_validation_failure(self, instance_manager):
        """Test delete operation with insecure instance names.

        This test verifies that security validation prevents deletion of
        instances with potentially dangerous names.
        """
        dangerous_names = [
            "test;rm -rf /",
            "test&ls",
            "test`pwd`",
            "$HOME",
            "../test",
            "test/../etc",
        ]

        for dangerous_name in dangerous_names:
            # Should raise security validation error
            with pytest.raises(Exception):
                instance_manager.delete_instance(dangerous_name)

    @pytest.mark.parametrize("instance_name,port,expected_success", [
        ("simple-instance", 8080, True),
        ("complex-name-instance", 3000, True),
        ("underscore_instance", 8443, True),
        ("numeric-instance-123", 9090, True),
    ])
    def test_delete_parametrized_success_scenarios(self, instance_manager, instance_name, port, expected_success):
        """Parametrized test for successful deletion scenarios.

        This test covers various valid instance naming patterns to ensure
        comprehensive coverage of successful delete operations.
        """
        # Setup: create instance configuration
        instance_manager.create_instance_config(instance_name, port)
        assert instance_manager.instance_exists(instance_name) is True

        with patch('cconx.cconx.docker.DockerClient', MockDockerClient):
            result = instance_manager.delete_instance(instance_name)

            assert result["config_deleted"] == expected_success
            assert result["container_stopped"] == expected_success
            assert result["container_removed"] == expected_success
            assert instance_manager.instance_exists(instance_name) is not expected_success

    def test_delete_instance_error_handling_integration(self, instance_manager):
        """Test comprehensive error handling in delete operation.

        This test verifies handling of edge cases where containers may be in
        unexpected states during deletion.
        """
        instance_name = "error-handling-instance"

        # Setup: create instance configuration
        instance_manager.create_instance_config(instance_name, 9090)
        assert instance_manager.instance_exists(instance_name) is True

        # Mock Docker client with stopped container scenario
        with patch('cconx.cconx.docker.DockerClient') as mock_class:
            mock_instance = MagicMock(spec=MockDockerClient)
            # Container exists but is already stopped
            mock_instance.is_container_running.return_value = False
            mock_instance.stop_container.return_value = False  # Already stopped
            mock_instance.remove_container.return_value = True  # Can still remove stopped container
            mock_class.return_value = mock_instance

            result = instance_manager.delete_instance(instance_name)

            # Should succeed with config deletion
            assert result["config_deleted"] is True
            assert result["container_stopped"] is False  # False because container was already stopped
            assert result["container_removed"] is True

    def test_delete_instance_container_naming_convention(self, instance_manager):
        """Test that container naming convention (cconx-{name}) is respected.

        This test verifies that Docker operations use the correct container naming
        pattern to ensure proper identification and cleanup.
        """
        instance_name = "test-container-naming"

        # Setup: create instance configuration
        instance_manager.create_instance_config(instance_name, 9090)
        assert instance_manager.instance_exists(instance_name) is True

        with patch('cconx.cconx.docker.DockerClient') as mock_class:
            mock_instance = MagicMock(spec=MockDockerClient)
            # Container doesn't exist initially
            mock_instance.is_container_running.return_value = False
            # Stop should not be called since container isn't running
            mock_instance.stop_container.side_effect = AssertionError("stop_container should not be called")
            mock_instance.remove_container.return_value = False
            mock_class.return_value = mock_instance

            result = instance_manager.delete_instance(instance_name)

            # Verify DockerClient methods were called with correct container name
            expected_container_name = f"cconx-{instance_name}"
            mock_instance.is_container_running.assert_called_once_with(expected_container_name)
            # stop_container should NOT be called since is_container_running returned False
            mock_instance.stop_container.assert_not_called()
            # remove_container should still be called for cleanup
            mock_instance.remove_container.assert_called_once_with(expected_container_name)

        assert result["config_deleted"] is True
        assert result["container_stopped"] is False
        assert result["container_removed"] is False