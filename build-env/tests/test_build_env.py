"""Tests for build environment manager."""

import os
import unittest
from unittest.mock import Mock, patch

# Mock docker before imports
import sys
sys.modules['docker'] = Mock()
sys.modules['docker'].DockerClient = Mock
sys.modules['docker'].from_env = Mock
sys.modules['docker.errors'] = Mock()
sys.modules['docker.errors'].NotFound = Exception

# Mock security module with proper mocking
sys.modules['build_env.security'] = Mock()
sys.modules['build_env.security'].validate_image_name = Mock()
sys.modules['build_env.security'].filter_environment_variables = Mock()
sys.modules['build_env.security'].generate_container_uuid = Mock()
sys.modules['build_env.security'].SecurityError = Exception

# Set default behavior for mocks
sys.modules['build_env.security'].validate_image_name.return_value = True
sys.modules['build_env.security'].filter_environment_variables.return_value = {}
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
        self.assertTrue(name.startswith("build-"))
        self.assertEqual(len(name), 42)  # build- + UUIDv4

    def test_validate_requirements(self):
        """Test requirements validation."""
        # Set required environment variables
        os.environ["BUILD_CONTAINER"] = "test-container"
        os.environ["DEFAULT_WORKSPACE"] = "/workspace"

        # Valid requirements
        requirements = {
            "image": "python:3.9",
            "working_dir": "/workspace",
            "command": ["bash", "-c", "echo hello"]
        }
        self.assertTrue(self.manager._validate_requirements(requirements))

    def test_validate_requirements_missing_image(self):
        """Test requirements validation with missing image."""
        os.environ["BUILD_CONTAINER"] = "test-container"
        os.environ["DEFAULT_WORKSPACE"] = "/workspace"

        with self.assertRaises(BuildEnvironmentError) as cm:
            self.manager._validate_requirements({"working_dir": "/workspace"})
        self.assertIn("Docker image is required", str(cm.exception))

    def test_validate_requirements_missing_env_vars(self):
        """Test requirements validation with missing environment variables."""
        # Ensure environment variables are not set
        if "BUILD_CONTAINER" in os.environ:
            del os.environ["BUILD_CONTAINER"]
        if "DEFAULT_WORKSPACE" in os.environ:
            del os.environ["DEFAULT_WORKSPACE"]

        requirements = {"image": "python:3.9"}

        with self.assertRaises(BuildEnvironmentError) as cm:
            self.manager._validate_requirements(requirements)
        self.assertIn("BUILD_CONTAINER environment variable is required", str(cm.exception))

    def test_validate_requirements_invalid_image(self):
        """Test requirements validation with invalid image."""
        os.environ["BUILD_CONTAINER"] = "test-container"
        os.environ["DEFAULT_WORKSPACE"] = "/workspace"

        # Set the mock to raise an exception
        sys.modules['build_env.security'].validate_image_name.side_effect = Exception("Invalid image")

        try:
            with self.assertRaises(BuildEnvironmentError) as cm:
                self.manager._validate_requirements({"image": "invalid-image"})
            self.assertIn("Invalid image name", str(cm.exception))
        finally:
            # Reset side effect
            sys.modules['build_env.security'].validate_image_name.side_effect = None

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

    def test_get_container_uuid(self):
        """Test container UUID retrieval."""
        mock_container = Mock()
        mock_container.id = "abc123"
        self.mock_docker_client.containers.get.return_value = mock_container

        uuid = self.manager._get_container_uuid("test-container")
        self.assertEqual(uuid, "abc123")

    def test_get_container_uuid_not_found(self):
        """Test container UUID retrieval when container doesn't exist."""
        self.mock_docker_client.containers.get.side_effect = Exception("Not found")

        with self.assertRaises(BuildEnvironmentError) as cm:
            self.manager._get_container_uuid("non-existent-container")
        self.assertIn("does not exist", str(cm.exception))


if __name__ == "__main__":
    unittest.main()