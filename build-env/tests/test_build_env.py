"""Tests for build environment manager."""

import os
import unittest
from unittest.mock import Mock

# Mock docker before imports
import sys
sys.modules['docker'] = Mock()
sys.modules['docker'].DockerClient = Mock
sys.modules['docker'].from_env = Mock
sys.modules['docker.errors'] = Mock()
sys.modules['docker.errors'].NotFound = Exception

# Mock security module with proper mocking
sys.modules['build_env.security'] = Mock()
sys.modules['build_env.security'].generate_container_uuid = Mock()

# Set default behavior for mocks
sys.modules['build_env.security'].generate_container_uuid.return_value = "12345678-1234-5678-1234-567812345678"

from build_env import BuildEnvironmentManager, BuildEnvironmentError


class TestBuildEnvironmentManager(unittest.TestCase):
    """Test BuildEnvironmentManager core functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_docker_client = Mock()
        self.manager = BuildEnvironmentManager(
            docker_client=self.mock_docker_client
        )

    def tearDown(self):
        """Clean up after tests."""
        # Clean up environment variables
        for var in ["BUILD_CONTAINER", "DEFAULT_WORKSPACE"]:
            if var in os.environ:
                del os.environ[var]

    def test_generate_container_name(self):
        """Test container name generation."""
        name = self.manager._generate_container_name()
        self.assertTrue(name.startswith("build-env-"))
        self.assertEqual(len(name), 46)  # build-env- + UUIDv4

    def test_validate_requirements_success(self):
        """Test requirements validation success."""
        # Set required environment variables
        os.environ["BUILD_CONTAINER"] = "test-container"
        os.environ["DEFAULT_WORKSPACE"] = "/workspace"

        # Should not raise any exception
        env_vars = {"TEST_VAR": "test_value"}
        self.manager._validate_requirements(env_vars)

    def test_validate_requirements_missing_build_container(self):
        """Test requirements validation with missing BUILD_CONTAINER."""
        # Ensure BUILD_CONTAINER is not set
        if "BUILD_CONTAINER" in os.environ:
            del os.environ["BUILD_CONTAINER"]

        # Set DEFAULT_WORKSPACE
        os.environ["DEFAULT_WORKSPACE"] = "/workspace"

        env_vars = {"TEST_VAR": "test_value"}

        with self.assertRaises(BuildEnvironmentError) as cm:
            self.manager._validate_requirements(env_vars)
        self.assertIn("BUILD_CONTAINER environment variable is required", str(cm.exception))

    def test_validate_requirements_missing_default_workspace(self):
        """Test requirements validation with missing DEFAULT_WORKSPACE."""
        # Set BUILD_CONTAINER
        os.environ["BUILD_CONTAINER"] = "test-container"

        # Ensure DEFAULT_WORKSPACE is not set
        if "DEFAULT_WORKSPACE" in os.environ:
            del os.environ["DEFAULT_WORKSPACE"]

        env_vars = {"TEST_VAR": "test_value"}

        with self.assertRaises(BuildEnvironmentError) as cm:
            self.manager._validate_requirements(env_vars)
        self.assertIn("DEFAULT_WORKSPACE environment variable is required", str(cm.exception))

    def test_get_container_uuid(self):
        """Test workspace UUID generation."""
        uuid = self.manager._get_container_uuid("/workspace/test")
        self.assertEqual(uuid, "12345678-1234-5678-1234-567812345678")

    def test_container_exists(self):
        """Test container existence check."""
        # Container exists
        self.mock_docker_client.containers.get.return_value = Mock()
        self.assertTrue(self.manager._container_exists("my-container"))

        # Container does not exist
        self.mock_docker_client.containers.get.side_effect = Exception("Not found")
        self.assertFalse(self.manager._container_exists("non-existent-container"))

    def test_container_running(self):
        """Test container running status check."""
        # Container is running
        mock_container = Mock()
        mock_container.status = "running"
        self.mock_docker_client.containers.get.return_value = mock_container
        self.assertTrue(self.manager._container_running("running-container"))

        # Container is not running
        mock_container.status = "exited"
        self.assertFalse(self.manager._container_running("exited-container"))

        # Container does not exist
        self.mock_docker_client.containers.get.side_effect = Exception("Not found")
        self.assertFalse(self.manager._container_running("non-existent-container"))

    def test_get_container_uuid_calls_security_module(self):
        """Test that get_container_uuid calls the security module."""
        # Reset the mock call count
        sys.modules['build_env.security'].generate_container_uuid.reset_mock()
        uuid = self.manager._get_container_uuid("/workspace/test")
        self.assertEqual(uuid, "12345678-1234-5678-1234-567812345678")
        sys.modules['build_env.security'].generate_container_uuid.assert_called_once()


if __name__ == "__main__":
    unittest.main()