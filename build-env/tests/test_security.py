#!/usr/bin/env python3
"""Tests for the build-env security validation module."""

import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security import (
    validate_image_name,
    filter_environment_variables,
    validate_uuid,
    generate_container_uuid,
    SecurityError
)


class TestSecurityValidation(unittest.TestCase):
    """Test cases for security validation functionality."""

    def test_validate_image_name_success(self):
        """Test valid image names pass validation."""
        valid_images = [
            "ubuntu:20.04",
            "python:3.11",
            "node:18-alpine",
            "golang:1.19",
            "alpine:latest"
        ]

        for image in valid_images:
            with self.subTest(image=image):
                self.assertTrue(validate_image_name(image))

    def test_validate_image_name_failure(self):
        """Test invalid image names raise appropriate errors."""
        invalid_images = [
            "../malicious",
            "; rm -rf /",
            "image with spaces",
            ""
        ]

        for image in invalid_images:
            with self.subTest(image=image):
                with self.assertRaises(SecurityError):
                    validate_image_name(image)

    def test_filter_environment_variables(self):
        """Test environment variable filtering."""
        env_vars = {
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "DOCKER_HOST": "unix:///var/run/docker.sock",
            "AWS_ACCESS_KEY_ID": "secret",
            "BUILD_CONTAINER": "python:3.11",
            "_SECRET": "hidden"
        }

        filtered = filter_environment_variables(env_vars)

        self.assertIn("PATH", filtered)
        self.assertIn("HOME", filtered)
        self.assertIn("BUILD_CONTAINER", filtered)
        self.assertNotIn("DOCKER_HOST", filtered)
        self.assertNotIn("AWS_ACCESS_KEY_ID", filtered)
        self.assertNotIn("_SECRET", filtered)

    def test_validate_uuid(self):
        """Test UUID validation."""
        valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
        invalid_uuid = "not-a-uuid"

        self.assertTrue(validate_uuid(valid_uuid))
        with self.assertRaises(SecurityError):
            validate_uuid(invalid_uuid)

    def test_generate_container_uuid(self):
        """Test UUID generation."""
        uuid1 = generate_container_uuid()
        uuid2 = generate_container_uuid()

        self.assertNotEqual(uuid1, uuid2)
        self.assertTrue(validate_uuid(uuid1))
        self.assertTrue(validate_uuid(uuid2))


if __name__ == "__main__":
    unittest.main()