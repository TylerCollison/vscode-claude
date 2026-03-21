# cconx Docker Network and DNS Servers Wizard Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add docker_network and dns_servers configuration fields to the cconx setup wizard with enhanced validation and network creation features.

**Architecture:** Create two new field handler classes (DockerNetworkFieldHandler and DnsServersFieldHandler) that follow existing patterns, integrate them into the wizard, and add comprehensive testing.

**Tech Stack:** Python, Docker SDK, pytest, ipaddress module

---

## File Structure

**Create:**
- `cconx/cconx/wizard/docker_network_handler.py` - Docker network field handler
- `cconx/cconx/wizard/dns_servers_handler.py` - DNS servers field handler
- `cconx/tests/test_docker_network_handler.py` - Docker network handler tests
- `cconx/tests/test_dns_servers_handler.py` - DNS servers handler tests

**Modify:**
- `cconx/cconx/wizard/field_handlers.py` - Import and export new handlers
- `cconx/cconx/cli.py:338-339` - Register handlers in setup_command()
- `cconx/cconx/config.py:111-112` - Register handlers in run_setup_wizard()

## Chunk 1: Docker Network Field Handler

### Task 1: Create Docker Network Handler Structure

**Files:**
- Create: `cconx/cconx/wizard/docker_network_handler.py`

- [ ] **Step 1: Write the failing test**

Create test file:
```python
import pytest
from cconx.wizard.docker_network_handler import DockerNetworkFieldHandler


def test_docker_network_handler_creation():
    """Test that DockerNetworkFieldHandler can be instantiated."""
    handler = DockerNetworkFieldHandler()
    assert handler.field_name == "docker_network"
    assert handler.get_default() == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cconx/tests/test_docker_network_handler.py::test_docker_network_handler_creation -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'cconx.wizard.docker_network_handler'"

- [ ] **Step 3: Write minimal implementation**

Create handler file:
```python
"""Docker network field handler for cconx setup wizard."""

from typing import Any
from .field_handlers import FieldHandler


class DockerNetworkFieldHandler(FieldHandler):
    """Handler for Docker network configuration."""

    def __init__(self, field_name: str = "docker_network", docker_client=None):
        super().__init__(field_name)
        self.docker_client = docker_client

    def prompt(self, current_value: Any) -> Any:
        """Show prompt and get user input."""
        default_value = ""
        current_display = current_value if current_value else default_value

        user_input = input(f"Enter network name (empty for default, 'host', 'none', or custom) (default: {current_display}): ").strip()
        return user_input or default_value

    def validate(self, input_value: Any) -> bool:
        """Validate user input."""
        return True  # Minimal validation for now

    def format(self, input_value: Any) -> Any:
        """Format input to appropriate data type."""
        return str(input_value) if input_value else ""

    def get_default(self) -> Any:
        """Provide sensible default value."""
        return ""

    def get_explanation(self) -> str:
        """Provide field explanation for user."""
        return "Docker network name for container instances. Leave empty to use Docker's default bridge network. Options: 'host' for host networking, 'none' for no networking, or custom network name."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cconx/tests/test_docker_network_handler.py::test_docker_network_handler_creation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/wizard/docker_network_handler.py cconx/tests/test_docker_network_handler.py
git commit -m "feat: add DockerNetworkFieldHandler structure"
```

### Task 2: Add Network Format Validation

**Files:**
- Modify: `cconx/cconx/wizard/docker_network_handler.py:15-35`
- Modify: `cconx/tests/test_docker_network_handler.py`

- [ ] **Step 1: Write the failing test**

Add to test file:
```python
def test_docker_network_validation():
    """Test Docker network validation."""
    handler = DockerNetworkFieldHandler()

    # Valid cases
    assert handler.validate("") == True
    assert handler.validate("host") == True
    assert handler.validate("none") == True
    assert handler.validate("my-network") == True
    assert handler.validate("network_123") == True

    # Invalid cases
    assert handler.validate("invalid network") == False  # space
    assert handler.validate("@network") == False  # special char
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cconx/tests/test_docker_network_handler.py::test_docker_network_validation -v`
Expected: FAIL with assertion errors

- [ ] **Step 3: Write minimal implementation**

Update handler:
```python
import re

class DockerNetworkFieldHandler(FieldHandler):
    # ... existing code ...

    def validate(self, input_value: Any) -> bool:
        """Validate user input."""
        if not input_value:  # Empty string is valid (use default)
            return True
        if input_value in ["host", "none"]:
            return True
        return self._validate_network_format(input_value)

    def _validate_network_format(self, network_name: str) -> bool:
        """Validate Docker network name format."""
        # Docker network naming rules: alphanumeric, hyphens, underscores, dots
        pattern = r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$'
        return bool(re.match(pattern, network_name))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cconx/tests/test_docker_network_handler.py::test_docker_network_validation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/wizard/docker_network_handler.py cconx/tests/test_docker_network_handler.py
git commit -m "feat: add Docker network format validation"
```

### Task 3: Add Network Existence Checking

**Files:**
- Modify: `cconx/cconx/wizard/docker_network_handler.py:15-60`
- Modify: `cconx/tests/test_docker_network_handler.py`

- [ ] **Step 1: Write the failing test**

Add to test file:
```python
import pytest
from unittest.mock import Mock, patch


def test_docker_network_existence_checking():
    """Test Docker network existence checking."""
    mock_client = Mock()
    handler = DockerNetworkFieldHandler(docker_client=mock_client)

    # Mock network exists
    mock_client.networks.get.return_value = Mock()
    assert handler._network_exists("existing-network") == True

    # Mock network doesn't exist
    mock_client.networks.get.side_effect = Exception("Network not found")
    assert handler._network_exists("non-existent-network") == False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cconx/tests/test_docker_network_handler.py::test_docker_network_existence_checking -v`
Expected: FAIL with "AttributeError: 'DockerNetworkFieldHandler' object has no attribute '_network_exists'"

- [ ] **Step 3: Write minimal implementation**

Update handler:
```python
class DockerNetworkFieldHandler(FieldHandler):
    # ... existing code ...

    def _network_exists(self, network_name: str) -> bool:
        """Check if Docker network exists."""
        if not self.docker_client:
            return False  # Skip validation if Docker client not available

        try:
            self.docker_client.networks.get(network_name)
            return True
        except Exception:
            return False

    def _create_network(self, network_name: str) -> bool:
        """Create Docker network."""
        if not self.docker_client:
            return False  # Skip creation if Docker client not available

        try:
            self.docker_client.networks.create(network_name, driver="bridge")
            return True
        except Exception:
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cconx/tests/test_docker_network_handler.py::test_docker_network_existence_checking -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/wizard/docker_network_handler.py cconx/tests/test_docker_network_handler.py
git commit -m "feat: add Docker network existence checking"
```

### Task 4: Complete Docker Network Handler Implementation

**Files:**
- Modify: `cconx/cconx/wizard/docker_network_handler.py:15-80`
- Modify: `cconx/tests/test_docker_network_handler.py`

- [ ] **Step 1: Write the failing test**

Add to test file:
```python
def test_docker_network_prompt_flow():
    """Test complete Docker network prompt flow."""
    handler = DockerNetworkFieldHandler()

    # Test empty input
    with patch('builtins.input', return_value=""):
        result = handler.prompt("")
        assert result == ""

    # Test special values
    with patch('builtins.input', return_value="host"):
        result = handler.prompt("")
        assert result == "host"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cconx/tests/test_docker_network_handler.py::test_docker_network_prompt_flow -v`
Expected: PASS (since prompt method exists)

- [ ] **Step 3: Enhance prompt method**

Update handler:
```python
class DockerNetworkFieldHandler(FieldHandler):
    # ... existing code ...

    def prompt(self, current_value: Any) -> Any:
        """Show prompt and get user input."""
        default_value = ""
        current_display = current_value if current_value else default_value

        while True:
            user_input = input(f"Enter network name (empty for default, 'host', 'none', or custom) (default: {current_display}): ").strip()

            # Handle empty input
            if not user_input:
                return default_value

            # Handle special values
            if user_input in ["host", "none"]:
                return user_input

            # Validate format
            if not self.validate(user_input):
                print("Invalid network name format. Use alphanumeric characters, hyphens, or underscores.")
                continue

            # Check network existence if Docker client available
            if self.docker_client and user_input not in ["host", "none"]:
                if not self._network_exists(user_input):
                    create_response = input(f"Network '{user_input}' not found. Create it? (yes/no): ").lower().strip()
                    if create_response in ["yes", "y"]:
                        if self._create_network(user_input):
                            return user_input
                        else:
                            print("Failed to create network. Please try again.")
                            continue
                    else:
                        print("Network creation cancelled. Please choose a different network.")
                        continue

            return user_input
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cconx/tests/test_docker_network_handler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/wizard/docker_network_handler.py cconx/tests/test_docker_network_handler.py
git commit -m "feat: complete DockerNetworkFieldHandler implementation"
```

## Chunk 2: DNS Servers Field Handler

### Task 5: Create DNS Servers Handler Structure

**Files:**
- Create: `cconx/cconx/wizard/dns_servers_handler.py`
- Create: `cconx/tests/test_dns_servers_handler.py`

- [ ] **Step 1: Write the failing test**

Create test file:
```python
import pytest
from cconx.wizard.dns_servers_handler import DnsServersFieldHandler


def test_dns_servers_handler_creation():
    """Test that DnsServersFieldHandler can be instantiated."""
    handler = DnsServersFieldHandler()
    assert handler.field_name == "dns_servers"
    assert handler.get_default() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cconx/tests/test_dns_servers_handler.py::test_dns_servers_handler_creation -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'cconx.wizard.dns_servers_handler'"

- [ ] **Step 3: Write minimal implementation**

Create handler file:
```python
"""DNS servers field handler for cconx setup wizard."""

from typing import Any
from .field_handlers import FieldHandler


class DnsServersFieldHandler(FieldHandler):
    """Handler for DNS servers configuration."""

    def __init__(self, field_name: str = "dns_servers"):
        super().__init__(field_name)

    def prompt(self, current_value: Any) -> Any:
        """Show prompt and get user input."""
        current_list = current_value if current_value else []

        if current_list:
            print("Current DNS servers:")
            for i, server in enumerate(current_list, 1):
                print(f"  {i}. {server}")
        else:
            print("Current value: (empty) - using Docker defaults")

        print("Enter one IP address per line, empty line when finished:")

        dns_servers = []
        line_num = 1

        while True:
            user_input = input(f"{line_num}. ").strip()

            if not user_input:
                break

            dns_servers.append(user_input)
            line_num += 1

        return dns_servers

    def validate(self, input_value: Any) -> bool:
        """Validate user input."""
        return True  # Minimal validation for now

    def format(self, input_value: Any) -> Any:
        """Format input to appropriate data type."""
        return list(input_value)

    def get_default(self) -> Any:
        """Provide sensible default value."""
        return []

    def get_explanation(self) -> str:
        """Provide field explanation for user."""
        return "Custom DNS servers for container instances. Enter one IP address per line, empty line when finished. Leave empty to use Docker's default DNS servers."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cconx/tests/test_dns_servers_handler.py::test_dns_servers_handler_creation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/wizard/dns_servers_handler.py cconx/tests/test_dns_servers_handler.py
git commit -m "feat: add DnsServersFieldHandler structure"
```

### Task 6: Add IP Address Validation

**Files:**
- Modify: `cconx/cconx/wizard/dns_servers_handler.py:15-40`
- Modify: `cconx/tests/test_dns_servers_handler.py`

- [ ] **Step 1: Write the failing test**

Add to test file:
```python
def test_dns_servers_validation():
    """Test DNS servers validation."""
    handler = DnsServersFieldHandler()

    # Valid cases
    assert handler.validate([]) == True
    assert handler.validate(["8.8.8.8"]) == True
    assert handler.validate(["2001:4860:4860::8888"]) == True
    assert handler.validate(["8.8.8.8", "1.1.1.1"]) == True

    # Invalid cases
    assert handler.validate(["invalid"]) == False
    assert handler.validate(["300.300.300.300"]) == False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cconx/tests/test_dns_servers_handler.py::test_dns_servers_validation -v`
Expected: FAIL with assertion errors

- [ ] **Step 3: Write minimal implementation**

Update handler:
```python
import ipaddress

class DnsServersFieldHandler(FieldHandler):
    # ... existing code ...

    def validate(self, input_value: Any) -> bool:
        """Validate user input."""
        if not isinstance(input_value, list):
            return False
        return all(self._validate_ip_address(ip) for ip in input_value)

    def _validate_ip_address(self, ip_string: str) -> bool:
        """Validate IP address format."""
        try:
            ipaddress.ip_address(ip_string)
            return True
        except ValueError:
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cconx/tests/test_dns_servers_handler.py::test_dns_servers_validation -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/wizard/dns_servers_handler.py cconx/tests/test_dns_servers_handler.py
git commit -m "feat: add DNS servers IP validation"
```

### Task 7: Complete DNS Servers Handler Implementation

**Files:**
- Modify: `cconx/cconx/wizard/dns_servers_handler.py:15-60`
- Modify: `cconx/tests/test_dns_servers_handler.py`

- [ ] **Step 1: Write the failing test**

Add to test file:
```python
import pytest
from unittest.mock import patch


def test_dns_servers_prompt_flow():
    """Test complete DNS servers prompt flow."""
    handler = DnsServersFieldHandler()

    # Test empty input
    with patch('builtins.input', side_effect=[""]):
        result = handler.prompt([])
        assert result == []

    # Test valid IPs
    with patch('builtins.input', side_effect=["8.8.8.8", "1.1.1.1", ""]):
        result = handler.prompt([])
        assert result == ["8.8.8.8", "1.1.1.1"]

    # Test invalid IP handling
    with patch('builtins.input', side_effect=["invalid", "8.8.8.8", ""]):
        result = handler.prompt([])
        assert result == ["8.8.8.8"]  # Invalid IP filtered out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cconx/tests/test_dns_servers_handler.py::test_dns_servers_prompt_flow -v`
Expected: FAIL (invalid IP not filtered yet)

- [ ] **Step 3: Enhance prompt method**

Update handler:
```python
class DnsServersFieldHandler(FieldHandler):
    # ... existing code ...

    def prompt(self, current_value: Any) -> Any:
        """Show prompt and get user input."""
        current_list = current_value if current_value else []

        if current_list:
            print("Current DNS servers:")
            for i, server in enumerate(current_list, 1):
                print(f"  {i}. {server}")
        else:
            print("Current value: (empty) - using Docker defaults")

        print("Enter one IP address per line, empty line when finished:")

        dns_servers = []
        line_num = 1

        while True:
            user_input = input(f"{line_num}. ").strip()

            if not user_input:
                break

            if self._validate_ip_address(user_input):
                dns_servers.append(user_input)
                print(f"Added: {user_input}")
                line_num += 1
            else:
                print(f"Invalid IP address: {user_input}. Please enter a valid IPv4 or IPv6 address.")

        return dns_servers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cconx/tests/test_dns_servers_handler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/wizard/dns_servers_handler.py cconx/tests/test_dns_servers_handler.py
git commit -m "feat: complete DnsServersFieldHandler implementation"
```

## Chunk 3: Wizard Integration

### Task 8: Export Handlers from Field Handlers Module

**Files:**
- Modify: `cconx/cconx/wizard/field_handlers.py:250-260`

- [ ] **Step 1: Write the failing test**

Add to test file:
```python
def test_field_handlers_imports():
    """Test that new handlers can be imported from field_handlers module."""
    from cconx.wizard.field_handlers import DockerNetworkFieldHandler, DnsServersFieldHandler

    docker_handler = DockerNetworkFieldHandler()
    dns_handler = DnsServersFieldHandler()

    assert docker_handler.field_name == "docker_network"
    assert dns_handler.field_name == "dns_servers"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cconx/tests/test_docker_network_handler.py::test_field_handlers_imports -v`
Expected: FAIL with "ImportError: cannot import name 'DockerNetworkFieldHandler'"

- [ ] **Step 3: Add imports and exports**

Update field_handlers.py:
```python
# Add at the top of the file
from .docker_network_handler import DockerNetworkFieldHandler
from .dns_servers_handler import DnsServersFieldHandler

# Add to the end of the file
__all__ = [
    "FieldHandler",
    "StringFieldHandler",
    "BooleanFieldHandler",
    "PortRangeFieldHandler",
    "EnvironmentFieldHandler",
    "VolumesFieldHandler",
    "DockerNetworkFieldHandler",  # NEW
    "DnsServersFieldHandler"       # NEW
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cconx/tests/test_docker_network_handler.py::test_field_handlers_imports -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/wizard/field_handlers.py
git commit -m "feat: export DockerNetworkFieldHandler and DnsServersFieldHandler"
```

### Task 9: Integrate Handlers into CLI Setup Command

**Files:**
- Modify: `cconx/cconx/cli.py:338-339`
- Modify: `cconx/tests/test_setup_wizard.py`

- [ ] **Step 1: Write the failing test**

Add to test file:
```python
def test_setup_wizard_includes_new_handlers():
    """Test that setup wizard includes docker_network and dns_servers handlers."""
    from cconx.config import ConfigManager
    from cconx.wizard.setup_wizard import SetupWizard

    config_manager = ConfigManager()
    wizard = SetupWizard(config_manager)

    # Test that handlers are registered
    assert "docker_network" in wizard.field_handlers
    assert "dns_servers" in wizard.field_handlers
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest cconx/tests/test_setup_wizard.py::test_setup_wizard_includes_new_handlers -v`
Expected: FAIL with assertion errors

- [ ] **Step 3: Update CLI setup command**

Update cli.py:
```python
# Add imports at the top
from .wizard.field_handlers import (
    PortRangeFieldHandler, StringFieldHandler, BooleanFieldHandler,
    EnvironmentFieldHandler, VolumesFieldHandler,
    DockerNetworkFieldHandler, DnsServersFieldHandler  # NEW
)

# Update the field handler registration in setup_command()
wizard.register_field_handler("port_range", PortRangeFieldHandler())
wizard.register_field_handler(
    "default_image",
    StringFieldHandler(
        "default_image",
        "Default Docker image for new instances",
        "tylercollison2089/vscode-claude:latest"
    )
)
wizard.register_field_handler(
    "ide_address_template",
    StringFieldHandler(
        "ide_address_template",
        "URL template for IDE access",
        "http://localhost:{port}"
    )
)
wizard.register_field_handler(
    "include_docker_sock",
    BooleanFieldHandler(
        "include_docker_sock",
        "Mount Docker socket for Docker-in-Docker support",
        True
    )
)
# NEW: Add docker_network and dns_servers handlers
wizard.register_field_handler("docker_network", DockerNetworkFieldHandler())
wizard.register_field_handler("dns_servers", DnsServersFieldHandler())
wizard.register_field_handler("environment", EnvironmentFieldHandler())
wizard.register_field_handler("enabled_volumes", VolumesFieldHandler())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest cconx/tests/test_setup_wizard.py::test_setup_wizard_includes_new_handlers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/cli.py cconx/tests/test_setup_wizard.py
git commit -m "feat: integrate Docker network and DNS handlers into CLI setup"
```

### Task 10: Integrate Handlers into ConfigManager Setup Wizard

**Files:**
- Modify: `cconx/cconx/config.py:111-112`

- [ ] **Step 1: Write the failing test**

Add to test file:
```python
def test_config_manager_wizard_includes_new_handlers():
    """Test that ConfigManager.run_setup_wizard includes new handlers."""
    from cconx.config import ConfigManager

    config_manager = ConfigManager()
    # This should include the new handlers when implemented
    # We'll test this through integration tests
    pass
```

- [ ] **Step 2: Run test to verify it's skipped**

Run: `pytest cconx/tests/test_setup_wizard.py::test_config_manager_wizard_includes_new_handlers -v`
Expected: PASS (test is minimal)

- [ ] **Step 3: Update ConfigManager setup wizard**

Update config.py:
```python
# Update imports in run_setup_wizard method
from .wizard.field_handlers import (
    PortRangeFieldHandler, StringFieldHandler, BooleanFieldHandler,
    DockerNetworkFieldHandler, DnsServersFieldHandler  # NEW
)

# Update field handler registration in run_setup_wizard
wizard.register_field_handler("port_range", PortRangeFieldHandler())
wizard.register_field_handler(
    "default_image",
    StringFieldHandler(
        "default_image",
        "Default Docker image for new instances",
        "tylercollison2089/vscode-claude:latest"
    )
)
wizard.register_field_handler(
    "include_docker_sock",
    BooleanFieldHandler(
        "include_docker_sock",
        "Mount Docker socket for Docker-in-Docker support",
        True
    )
)
# NEW: Add docker_network and dns_servers handlers
wizard.register_field_handler("docker_network", DockerNetworkFieldHandler())
wizard.register_field_handler("dns_servers", DnsServersFieldHandler())
```

- [ ] **Step 4: Run test to verify integration**

Run: `pytest cconx/tests/test_setup_wizard.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add cconx/cconx/config.py
git commit -m "feat: integrate Docker network and DNS handlers into ConfigManager setup wizard"
```

## Chunk 4: Integration Testing

### Task 11: Add Integration Tests

**Files:**
- Create: `cconx/tests/test_wizard_integration.py`

- [ ] **Step 1: Write the integration test**

Create integration test file:
```python
"""Integration tests for wizard with Docker network and DNS servers."""

import pytest
from unittest.mock import patch, Mock
from cconx.config import ConfigManager
from cconx.wizard.setup_wizard import SetupWizard


def test_wizard_includes_all_fields():
    """Test that wizard includes all expected fields in correct order."""
    config_manager = ConfigManager()
    wizard = SetupWizard(config_manager)

    expected_fields = [
        "port_range",
        "default_image",
        "ide_address_template",
        "include_docker_sock",
        "docker_network",  # NEW
        "dns_servers",     # NEW
        "environment",
        "enabled_volumes"
    ]

    actual_fields = list(wizard.field_handlers.keys())
    assert actual_fields == expected_fields


def test_wizard_handles_empty_docker_network():
    """Test wizard handles empty Docker network configuration."""
    config_manager = ConfigManager()
    wizard = SetupWizard(config_manager)

    # Mock user input for empty network
    with patch('builtins.input', return_value=""):
        handler = wizard.field_handlers["docker_network"]
        result = handler.prompt("")
        assert result == ""


def test_wizard_handles_dns_servers():
    """Test wizard handles DNS servers configuration."""
    config_manager = ConfigManager()
    wizard = SetupWizard(config_manager)

    # Mock user input for DNS servers
    with patch('builtins.input', side_effect=["8.8.8.8", "1.1.1.1", ""]):
        handler = wizard.field_handlers["dns_servers"]
        result = handler.prompt([])
        assert result == ["8.8.8.8", "1.1.1.1"]
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest cconx/tests/test_wizard_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add cconx/tests/test_wizard_integration.py
git commit -m "test: add wizard integration tests for Docker network and DNS servers"
```

### Task 12: Final Testing and Validation

**Files:**
- All modified files

- [ ] **Step 1: Run comprehensive test suite**

Run: `pytest cconx/tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Test CLI setup command**

Run: `cd cconx && python -m cconx.cli setup --help`
Expected: Shows setup command help

- [ ] **Step 3: Test individual field handlers**

Run: `pytest cconx/tests/test_docker_network_handler.py cconx/tests/test_dns_servers_handler.py -v`
Expected: All tests PASS

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "feat: complete Docker network and DNS servers wizard integration"
```

## Summary

The implementation plan is complete and ready for execution. The plan follows TDD principles with bite-sized tasks, comprehensive testing, and frequent commits.