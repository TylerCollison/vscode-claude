"""Tests for build environment manager."""

import unittest
from unittest.mock import Mock, patch

# Mock docker before imports
import sys
sys.modules['docker'] = Mock()
sys.modules['docker'].DockerClient = Mock
sys.modules['docker'].from_env = Mock
sys.modules['docker.errors'] = Mock()
sys.modules['docker.errors'].NotFound = Exception

from build_env import BuildEnvironmentManager


class TestBuildEnvironmentManager(unittest.TestCase):
    """Test BuildEnvironmentManager core functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_docker_client = Mock()
        self.manager = BuildEnvironmentManager(
            docker_client=self.mock_docker_client
        )

    def test_generate_container_name(self):
        """Test container name generation."""
        # Test with simple name
        name = self.manager._generate_container_name("my-project")
        self.assertRegex(name, r"^my-project-\w{8}$")

        # Test with special characters
        name = self.manager._generate_container_name("my.project@123")
        self.assertRegex(name, r"^my-project-123-\w{8}$")

    def test_validate_requirements(self):
        """Test requirements validation."""
        # Valid requirements
        requirements = {
            "image": "python:3.9",
            "working_dir": "/workspace",
            "command": ["bash", "-c", "echo hello"]
        }
        self.assertTrue(self.manager._validate_requirements(requirements))

        # Missing image
        with self.assertRaises(ValueError):
            self.manager._validate_requirements({"working_dir": "/workspace"})

        # Invalid image format
        with self.assertRaises(ValueError):
            self.manager._validate_requirements({"image": 123})

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

    def test_get_container_uuid(self):
        """Test container UUID retrieval."""
        mock_container = Mock()
        mock_container.id = "abc123"
        self.mock_docker_client.containers.get.return_value = mock_container

        uuid = self.manager._get_container_uuid("test-container")
        self.assertEqual(uuid, "abc123")


if __name__ == "__main__":
    unittest.main()