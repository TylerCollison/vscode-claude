"""Pytest configuration file for cconx tests."""
import sys
import os

def pytest_configure(config):
    """Mock docker module before tests run."""
    # Add module path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cconx'))

    # Create a mock docker module
    mock_docker_module = type('MockDocker', (), {})
    mock_docker_module.errors = type('MockDockerErrors', (), {})
    sys.modules['docker'] = mock_docker_module
    sys.modules['docker.errors'] = mock_docker_module.errors

    # Mock specific exception classes that are used in the code
    mock_docker_module.errors.NotFound = type('NotFound', (Exception,), {})
    mock_docker_module.errors.APIError = type('APIError', (Exception,), {})
    mock_docker_module.errors.DockerException = type('DockerException', (Exception,), {})