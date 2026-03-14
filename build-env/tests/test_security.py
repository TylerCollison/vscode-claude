#!/usr/bin/env python3
"""Tests for the build-env security validation module."""

import pytest
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


def test_validate_image_name_success():
    """Test valid image names pass validation."""
    valid_images = [
        "python:3.11",
        "node:18-alpine",
        "golang:1.21",
        "redis:latest",
        "custom/repo:tag"
    ]
    for image in valid_images:
        assert validate_image_name(image) is True


def test_validate_image_name_failure():
    """Test invalid image names raise appropriate errors."""
    invalid_images = [
        "../malicious",
        "; rm -rf /",
        "image with spaces",
        ""
    ]
    for image in invalid_images:
        with pytest.raises(SecurityError):
            validate_image_name(image)


def test_filter_environment_variables():
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

    assert "PATH" in filtered
    assert "HOME" in filtered
    assert "BUILD_CONTAINER" in filtered
    assert "DOCKER_HOST" not in filtered
    assert "AWS_ACCESS_KEY_ID" not in filtered
    assert "_SECRET" not in filtered


def test_validate_uuid():
    """Test UUID validation."""
    valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
    invalid_uuid = "not-a-uuid"

    assert validate_uuid(valid_uuid) is True
    with pytest.raises(SecurityError):
        validate_uuid(invalid_uuid)


def test_generate_container_uuid():
    """Test UUID generation."""
    uuid1 = generate_container_uuid()
    uuid2 = generate_container_uuid()

    assert uuid1 != uuid2
    assert validate_uuid(uuid1) is True
    assert validate_uuid(uuid2) is True