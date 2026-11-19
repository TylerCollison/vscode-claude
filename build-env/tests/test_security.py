#!/usr/bin/env python3
"""Tests for the build-env security validation module."""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security import (
    validate_image_name,
    validate_uuid,
    generate_container_uuid,
    SecurityError,
    filter_environment_variables,
    SAFE_ENV_VARS,
    DANGEROUS_ENV_PATTERNS
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


def test_filter_environment_variables_whitelist():
    """Test that whitelisted environment variables are allowed."""
    # BUILD_* is whitelisted
    env_vars = {
        "BUILD_TEST_VAR": "test_value",
        "BUILD_ANOTHER_VAR": "another_value",
        "PATH": "/usr/bin",
        "HOME": "/home/user",
        "USER": "testuser",
        "PWD": "/workspace",
        "SHELL": "/bin/bash",
        "TERM": "xterm",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "BUILD_CONTAINER": "python:3.11",
        "DEFAULT_WORKSPACE": "/workspace",
    }

    filtered = filter_environment_variables(env_vars)

    # All whitelisted vars should be present
    assert filtered == env_vars


def test_filter_environment_variables_blacklist():
    """Test that dangerous environment variables are filtered out."""
    env_vars = {
        "AWS_ACCESS_KEY_ID": "AKIA...",
        "AWS_SECRET_ACCESS_KEY": "secret...",
        "GITHUB_TOKEN": "ghp_...",
        "API_KEY": "api_key...",
        "SECRET": "secret...",
        "PASSWORD": "password...",
        "TOKEN": "token...",
        "DOCKER_HOST": "unix:///var/run/docker.sock",
        "_PRIVATE_VAR": "private",
    }

    filtered = filter_environment_variables(env_vars)

    # All dangerous vars should be filtered out
    assert filtered == {}


def test_filter_environment_variables_mixed():
    """Test mixed whitelisted and dangerous variables."""
    env_vars = {
        "BUILD_SAFE_VAR": "safe_value",  # Whitelisted (BUILD_*)
        "AWS_SECRET_ACCESS_KEY": "secret",  # Dangerous
        "PATH": "/usr/bin",  # Whitelisted
        "GITHUB_TOKEN": "token",  # Dangerous
        "HOME": "/home/user",  # Whitelisted
        "DOCKER_CONFIG": "/root/.docker",  # Dangerous (DOCKER_*)
        "CUSTOM_VAR": "custom",  # Not whitelisted, not explicitly dangerous
    }

    filtered = filter_environment_variables(env_vars)

    # Only whitelisted vars should remain
    assert filtered == {
        "BUILD_SAFE_VAR": "safe_value",
        "PATH": "/usr/bin",
        "HOME": "/home/user",
    }


def test_filter_environment_variables_deny_takes_precedence():
    """Test that deny list takes precedence over allow list."""
    # If a variable matches both whitelist and blacklist patterns,
    # deny should win. The exact matches in deny list are:
    # AWS_SECRET_ACCESS_KEY, GITHUB_TOKEN, API_KEY, SECRET, PASSWORD, TOKEN
    env_vars = {
        "AWS_SECRET_ACCESS_KEY": "should_be_filtered",  # Exact match in deny list
        "SECRET": "also_filtered",  # Exact match in deny list
        "PASSWORD": "also_filtered",  # Exact match in deny list
    }

    filtered = filter_environment_variables(env_vars)

    # Dangerous exact matches should win
    assert filtered == {}


def test_filter_environment_variables_unknown_vars_filtered():
    """Test that unknown variables (not in whitelist) are filtered out."""
    env_vars = {
        "UNKNOWN_VAR": "unknown",
        "ANOTHER_CUSTOM_VAR": "custom",
    }

    filtered = filter_environment_variables(env_vars)

    # Unknown vars should be filtered out (whitelist approach)
    assert filtered == {}