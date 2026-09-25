"""Pytest configuration file for cconx tests.

Installs a single canonical mock of the ``docker`` module before any test
runs. Individual test files used to install their own mocks with varying
fidelity, and whichever file ran last clobbered the others (a bare
``MagicMock`` for ``docker.errors`` makes ``except docker.errors.NotFound``
raise TypeError). Keeping the mock here makes the suite order-independent.

Also adds the repository root to sys.path so package imports
(``from cconx.cconx... import``) resolve regardless of how pytest is
invoked (``python -m pytest`` adds the cwd, a bare ``pytest`` does not).
"""
import os
import sys
from unittest.mock import MagicMock

# Parent directory of the cconx package (the repository root)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def pytest_configure(config):
    """Install the canonical docker module mock."""
    mock_docker_module = MagicMock()
    mock_docker_errors = type('MockDockerErrors', (), {})

    # Exception classes used by cconx/cconx/docker.py
    mock_docker_errors.NotFound = type('NotFound', (Exception,), {})
    mock_docker_errors.APIError = type('APIError', (Exception,), {})
    mock_docker_errors.DockerException = type('DockerException', (Exception,), {})

    mock_docker_module.errors = mock_docker_errors
    sys.modules['docker'] = mock_docker_module
    sys.modules['docker.errors'] = mock_docker_errors
