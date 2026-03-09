"""Pytest configuration file for vsclaude tests."""
import sys

def pytest_configure(config):
    """Mock docker module before tests run."""
    # Create a mock docker module
    mock_docker_module = type('MockDocker', (), {})
    mock_docker_module.errors = type('MockDockerErrors', (), {})
    sys.modules['docker'] = mock_docker_module
    sys.modules['docker.errors'] = mock_docker_module.errors

    # Mock specific exception classes that are used in the code
    mock_docker_module.errors.NotFound = type('NotFound', (Exception,), {})
    mock_docker_module.errors.APIError = type('APIError', (Exception,), {})
    mock_docker_module.errors.DockerException = type('DockerException', (Exception,), {})