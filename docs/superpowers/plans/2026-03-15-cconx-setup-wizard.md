# cconx Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an interactive setup wizard for cconx that allows users to configure the global configuration file through guided prompts.

**Architecture:** Modular FieldHandler classes for each configuration field, integrated with existing ConfigManager and CLI structure. Phased implementation starting with MVP covering core fields and essential environment variables.

**Tech Stack:** Python 3.8+, argparse for CLI, standard library for interactive prompts, pytest for testing.

---

## File Structure

### New Files
- `cconx/cconx/wizard/setup_wizard.py` - Main SetupWizard class
- `cconx/cconx/wizard/field_handlers.py` - FieldHandler implementations
- `cconx/cconx/wizard/__init__.py` - Package initialization
- `cconx/tests/test_setup_wizard.py` - Comprehensive test suite

### Modified Files
- `cconx/cconx/cli.py` - Add setup command and setup_command function
- `cconx/cconx/config.py` - Integrate with ConfigManager
- `cconx/tests/test_config.py` - Extend existing config tests

## Implementation Phases

### Phase 1: Core Framework & Essential Fields
- SetupWizard class with basic field handling
- Essential field handlers: port_range, default_image, ide_address_template, environment, enabled_volumes, include_docker_sock
- CLI integration with `cconx setup` command
- Comprehensive environment variable handling with special ClaudeConX variable prompts

### Phase 2: Advanced Features & Polish
- Complex field handlers: docker_network, dns_servers
- Enhanced environment variable subgroup management
- External validation and error handling improvements
- User experience refinements

---

## Chunk 1: Core SetupWizard Framework

### Task 1: Create Wizard Package Structure

**Files:**
- Create: `cconx/cconx/wizard/__init__.py`
- Create: `cconx/cconx/wizard/setup_wizard.py`
- Create: `cconx/cconx/wizard/field_handlers.py`
- Test: `cconx/tests/test_setup_wizard.py`

- [ ] **Step 1: Create package structure**

```bash
mkdir -p cconx/cconx/wizard
```

- [ ] **Step 2: Create __init__.py**

```python
# cconx/cconx/wizard/__init__.py
"""Setup wizard package for cconx configuration."""

from .setup_wizard import SetupWizard
from .field_handlers import FieldHandler

__all__ = ["SetupWizard", "FieldHandler"]
```

- [ ] **Step 3: Create base FieldHandler class**

```python
# cconx/cconx/wizard/field_handlers.py
"""Field handler classes for configuration wizard."""

from abc import ABC, abstractmethod
from typing import Any


class FieldHandler(ABC):
    """Abstract base class for field handlers."""

    def __init__(self, field_name: str):
        self.field_name = field_name

    @abstractmethod
    def prompt(self, current_value: Any) -> Any:
        """Show prompt and get user input."""
        pass

    @abstractmethod
    def validate(self, input_value: Any) -> bool:
        """Validate user input."""
        pass

    @abstractmethod
    def format(self, input_value: Any) -> Any:
        """Format input to appropriate data type."""
        pass

    @abstractmethod
    def get_default(self) -> Any:
        """Provide sensible default value."""
        pass

    @abstractmethod
    def get_explanation(self) -> str:
        """Provide field explanation for user."""
        pass
```

- [ ] **Step 4: Create SetupWizard class skeleton**

```python
# cconx/cconx/wizard/setup_wizard.py
"""Interactive setup wizard for cconx configuration."""

from typing import Dict, Any, List
from pathlib import Path
from .field_handlers import FieldHandler


class SetupWizard:
    """Interactive wizard for configuring cconx."""

    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.field_handlers: Dict[str, FieldHandler] = {}

    def register_field_handler(self, field_name: str, handler: FieldHandler):
        """Register a field handler."""
        self.field_handlers[field_name] = handler

    def run(self) -> Dict[str, Any]:
        """Run the interactive setup wizard."""
        print("Welcome to the cconx setup wizard!")
        print("This wizard will help you configure your global cconx settings.\n")

        # Load current configuration
        current_config = self.config_manager.load_global_config()
        new_config = current_config.copy()

        # Process each field
        for field_name, handler in self.field_handlers.items():
            current_value = current_config.get(field_name, handler.get_default())
            new_value = self._process_field(handler, current_value)
            if new_value is not None:
                new_config[field_name] = new_value

        return new_config

    def _process_field(self, handler: FieldHandler, current_value: Any) -> Any:
        """Process a single field with user interaction."""
        print(f"\n=== {handler.field_name.upper().replace('_', ' ')} ===")
        print(f"Description: {handler.get_explanation()}")
        print(f"Current value: {current_value}")

        while True:
            try:
                user_input = handler.prompt(current_value)
                if handler.validate(user_input):
                    return handler.format(user_input)
                else:
                    print("Invalid input. Please try again.")
            except KeyboardInterrupt:
                print("\nSetup cancelled.")
                return None
            except Exception as e:
                print(f"Error: {e}. Please try again.")
```

- [ ] **Step 5: Create initial test file**

```python
# cconx/tests/test_setup_wizard.py
"""Tests for cconx setup wizard."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_field_handler_abc():
    """Test FieldHandler abstract base class."""
    from cconx.wizard.field_handlers import FieldHandler

    # Should raise TypeError when instantiated directly
    try:
        FieldHandler("test")
        assert False, "Should not be able to instantiate ABC"
    except TypeError:
        pass


def test_setup_wizard_creation():
    """Test SetupWizard class creation."""
    from unittest.mock import MagicMock
    from cconx.wizard.setup_wizard import SetupWizard

    mock_config_manager = MagicMock()
    wizard = SetupWizard(mock_config_manager)

    assert wizard.config_manager == mock_config_manager
    assert isinstance(wizard.field_handlers, dict)
    assert len(wizard.field_handlers) == 0
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
cd /workspace/cconx
python -m pytest tests/test_setup_wizard.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'cconx.wizard'"

- [ ] **Step 7: Commit initial structure**

```bash
git add cconx/wizard/ tests/test_setup_wizard.py
git commit -m "feat: add setup wizard package structure"
```

---

## Chunk 2: Basic Field Handler Implementations

### Task 2: Implement Essential Field Handlers

**Files:**
- Modify: `cconx/cconx/wizard/field_handlers.py`
- Test: `cconx/tests/test_setup_wizard.py`

- [ ] **Step 1: Add StringFieldHandler**

```python
# Add to cconx/wizard/field_handlers.py

class StringFieldHandler(FieldHandler):
    """Handler for string fields."""

    def __init__(self, field_name: str, explanation: str, default_value: str = ""):
        super().__init__(field_name)
        self.explanation = explanation
        self.default_value = default_value

    def prompt(self, current_value: Any) -> Any:
        default_str = current_value if current_value else self.default_value
        return input(f"Enter value (default: {default_str}): ") or default_str

    def validate(self, input_value: Any) -> bool:
        return isinstance(input_value, str)

    def format(self, input_value: Any) -> Any:
        return str(input_value)

    def get_default(self) -> Any:
        return self.default_value

    def get_explanation(self) -> str:
        return self.explanation
```

- [ ] **Step 2: Add BooleanFieldHandler**

```python
# Add to cconx/wizard/field_handlers.py

class BooleanFieldHandler(FieldHandler):
    """Handler for boolean fields."""

    def __init__(self, field_name: str, explanation: str, default_value: bool = True):
        super().__init__(field_name)
        self.explanation = explanation
        self.default_value = default_value

    def prompt(self, current_value: Any) -> Any:
        default_bool = current_value if current_value is not None else self.default_value
        default_str = "yes" if default_bool else "no"
        response = input(f"Enable? (yes/no, default: {default_str}): ").lower().strip()

        if not response:
            return default_bool

        return response in ["yes", "y", "true", "1"]

    def validate(self, input_value: Any) -> bool:
        return isinstance(input_value, bool)

    def format(self, input_value: Any) -> Any:
        return bool(input_value)

    def get_default(self) -> Any:
        return self.default_value

    def get_explanation(self) -> str:
        return self.explanation
```

- [ ] **Step 3: Add PortRangeFieldHandler**

```python
# Add to cconx/wizard/field_handlers.py

class PortRangeFieldHandler(FieldHandler):
    """Handler for port range configuration."""

    def __init__(self, field_name: str = "port_range"):
        super().__init__(field_name)

    def prompt(self, current_value: Any) -> Any:
        default_min = current_value.get("min", 8000) if current_value else 8000
        default_max = current_value.get("max", 9000) if current_value else 9000

        print(f"Configure port range for instance allocation:")
        min_port = input(f"Minimum port (default: {default_min}): ") or default_min
        max_port = input(f"Maximum port (default: {default_max}): ") or default_max

        return {"min": min_port, "max": max_port}

    def validate(self, input_value: Any) -> bool:
        if not isinstance(input_value, dict):
            return False

        try:
            min_port = int(input_value.get("min", 0))
            max_port = int(input_value.get("max", 0))

            return (1 <= min_port <= 65535 and
                    1 <= max_port <= 65535 and
                    min_port < max_port)
        except (ValueError, TypeError):
            return False

    def format(self, input_value: Any) -> Any:
        return {
            "min": int(input_value["min"]),
            "max": int(input_value["max"])
        }

    def get_default(self) -> Any:
        return {"min": 8000, "max": 9000}

    def get_explanation(self) -> str:
        return "Defines the port range for automatically assigning ports to new instances"
```

- [ ] **Step 4: Add tests for field handlers**

```python
# Add to tests/test_setup_wizard.py

def test_string_field_handler():
    """Test StringFieldHandler functionality."""
    from cconx.wizard.field_handlers import StringFieldHandler

    handler = StringFieldHandler("test_field", "Test explanation", "default_value")

    assert handler.field_name == "test_field"
    assert handler.get_explanation() == "Test explanation"
    assert handler.get_default() == "default_value"
    assert handler.validate("test") == True
    assert handler.validate(123) == False
    assert handler.format("test") == "test"


def test_boolean_field_handler():
    """Test BooleanFieldHandler functionality."""
    from cconx.wizard.field_handlers import BooleanFieldHandler

    handler = BooleanFieldHandler("test_field", "Test explanation", True)

    assert handler.field_name == "test_field"
    assert handler.get_explanation() == "Test explanation"
    assert handler.get_default() == True
    assert handler.validate(True) == True
    assert handler.validate("string") == False
    assert handler.format(True) == True


def test_port_range_field_handler():
    """Test PortRangeFieldHandler functionality."""
    from cconx.wizard.field_handlers import PortRangeFieldHandler

    handler = PortRangeFieldHandler()

    assert handler.field_name == "port_range"
    assert "port range" in handler.get_explanation().lower()

    # Test validation
    assert handler.validate({"min": "8000", "max": "9000"}) == True
    assert handler.validate({"min": "9000", "max": "8000"}) == False  # min > max
    assert handler.validate({"min": "0", "max": "9000"}) == False     # min too low
    assert handler.validate({"min": "8000", "max": "70000"}) == False # max too high

    # Test formatting
    formatted = handler.format({"min": "8000", "max": "9000"})
    assert formatted == {"min": 8000, "max": 9000}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /workspace/cconx
python -m pytest tests/test_setup_wizard.py -v
```

Expected: PASS

- [ ] **Step 6: Commit field handlers**

```bash
git add cconx/wizard/field_handlers.py tests/test_setup_wizard.py
git commit -m "feat: add basic field handlers for setup wizard"
```

---

## Chunk 3: CLI Integration

### Task 3: Integrate Wizard with CLI

**Files:**
- Modify: `cconx/cconx/cli.py`
- Modify: `cconx/cconx/config.py`
- Test: `cconx/tests/test_setup_wizard.py`

- [ ] **Step 1: Add setup command to CLI**

```python
# Add to cconx/cli.py

def setup_command(args):
    """
    Interactive setup wizard for cconx configuration.

    This command walks users through configuring all aspects of the global
    configuration file with explanations and validation.

    Args:
        args: Command line arguments (no specific args needed)
    """
    from .config import ConfigManager
    from .wizard.setup_wizard import SetupWizard
    from .wizard.field_handlers import (
        PortRangeFieldHandler, StringFieldHandler, BooleanFieldHandler
    )

    config_manager = ConfigManager()
    wizard = SetupWizard(config_manager)

    # Register field handlers
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

    try:
        new_config = wizard.run()
        if new_config:
            config_manager._save_config(new_config)
            print("\n✅ Configuration saved successfully!")
            print("You can now use 'cconx start <name>' to create instances.")
        else:
            print("\nConfiguration cancelled.")
    except KeyboardInterrupt:
        print("\nSetup cancelled by user.")
    except Exception as e:
        print(f"\nError during setup: {e}")
```

- [ ] **Step 2: Add setup command to argument parser**

```python
# Add to cconx/cli.py main() function, after existing subparsers

# Setup command
setup_parser = subparsers.add_parser("setup", help="Interactive configuration wizard")

# Add to command dispatch section
elif args.command == "setup":
    setup_command(args)
```

- [ ] **Step 3: Add wizard integration to ConfigManager**

```python
# Add to cconx/config.py ConfigManager class

def run_setup_wizard(self):
    """Run the interactive setup wizard."""
    from .wizard.setup_wizard import SetupWizard
    from .wizard.field_handlers import (
        PortRangeFieldHandler, StringFieldHandler, BooleanFieldHandler
    )

    wizard = SetupWizard(self)

    # Register field handlers
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

    return wizard.run()
```

- [ ] **Step 4: Add CLI integration tests**

```python
# Add to tests/test_setup_wizard.py

def test_setup_command_integration():
    """Test setup command integration with CLI."""
    from cconx.cli import setup_command
    from unittest.mock import MagicMock, patch

    mock_args = MagicMock()

    with patch('cconx.cli.ConfigManager') as mock_config_manager:
        mock_instance = MagicMock()
        mock_config_manager.return_value = mock_instance

        # Test successful setup
        with patch('cconx.cli.SetupWizard') as mock_wizard:
            mock_wizard_instance = MagicMock()
            mock_wizard.return_value = mock_wizard_instance
            mock_wizard_instance.run.return_value = {"test": "config"}

            setup_command(mock_args)

            mock_wizard_instance.run.assert_called_once()
            mock_instance._save_config.assert_called_once_with({"test": "config"})
```

- [ ] **Step 5: Run integration tests**

```bash
cd /workspace/cconx
python -m pytest tests/test_setup_wizard.py::test_setup_command_integration -v
```

Expected: PASS

- [ ] **Step 6: Test CLI command manually**

```bash
cd /workspace/cconx
python -c "from cconx.cli import main; main()" setup --help
```

Expected: Shows setup command help

- [ ] **Step 7: Commit CLI integration**

```bash
git add cconx/cli.py cconx/config.py tests/test_setup_wizard.py
git commit -m "feat: integrate setup wizard with CLI"
```

---

## Chunk 4: Environment Variables Handling

### Task 4: Implement Environment Variable Field Handler

**Files:**
- Modify: `cconx/cconx/wizard/field_handlers.py`
- Test: `cconx/tests/test_setup_wizard.py`

- [ ] **Step 1: Add EnvironmentFieldHandler**

```python
# Add to cconx/wizard/field_handlers.py

class EnvironmentFieldHandler(FieldHandler):
    """Handler for environment variables configuration."""

    def __init__(self, field_name: str = "environment"):
        super().__init__(field_name)
        self.special_variables = {
            "NIM_API_KEY": "NVIDIA NIM API key",
            "GOOGLE_API_KEY": "Google AI Studio API key",
            "MISTRAL_API_KEY": "Mistral AI API key",
            "OPENROUTER_API_KEY": "OpenRouter API key",
            "CCR_PROFILE": "Claude Code Router profile",
            "PUID": "User ID for container processes",
            "PGID": "Group ID for container processes",
            "TZ": "Timezone configuration",
            "CLAUDE_CODE_PERMISSION_MODE": "Claude Code permission mode"
        }

    def prompt(self, current_value: Any) -> Any:
        env_vars = current_value.copy() if current_value else {}

        print("\n=== CONFIGURE ENVIRONMENT VARIABLES ===")
        print("The following special variables are commonly configured:")

        for var_name, description in self.special_variables.items():
            current_val = env_vars.get(var_name, "")
            print(f"\n{var_name}: {description}")
            if current_val:
                print(f"Current value: {current_val}")

            new_value = input(f"Enter value for {var_name} (leave empty to keep current): ")
            if new_value.strip():
                env_vars[var_name] = new_value.strip()
            elif var_name not in env_vars and new_value == "":
                # Skip if no current value and user enters empty
                continue

        # Allow adding arbitrary variables
        print("\n=== ADDITIONAL VARIABLES ===")
        print("You can add any additional environment variables.")
        print("Enter variables as KEY=VALUE pairs, one per line.")
        print("Enter an empty line when finished.\n")

        while True:
            user_input = input("Enter KEY=VALUE (or empty to finish): ").strip()
            if not user_input:
                break

            if "=" in user_input:
                key, value = user_input.split("=", 1)
                env_vars[key.strip()] = value.strip()
            else:
                print("Invalid format. Use KEY=VALUE format.")

        return env_vars

    def validate(self, input_value: Any) -> bool:
        if not isinstance(input_value, dict):
            return False

        # Basic validation - all keys should be strings
        return all(isinstance(key, str) for key in input_value.keys())

    def format(self, input_value: Any) -> Any:
        return dict(input_value)

    def get_default(self) -> Any:
        return {}

    def get_explanation(self) -> str:
        return "Environment variables passed to Docker containers"
```

- [ ] **Step 2: Add environment handler tests**

```python
# Add to tests/test_setup_wizard.py

def test_environment_field_handler():
    """Test EnvironmentFieldHandler functionality."""
    from cconx.wizard.field_handlers import EnvironmentFieldHandler

    handler = EnvironmentFieldHandler()

    assert handler.field_name == "environment"
    assert "environment variables" in handler.get_explanation().lower()

    # Test validation
    assert handler.validate({"KEY": "value"}) == True
    assert handler.validate({"KEY": 123}) == True  # Values can be any type
    assert handler.validate("not_a_dict") == False

    # Test formatting
    formatted = handler.format({"KEY": "value"})
    assert formatted == {"KEY": "value"}

    # Test special variables
    assert "NIM_API_KEY" in handler.special_variables
    assert "GOOGLE_API_KEY" in handler.special_variables
```

- [ ] **Step 3: Register environment handler in CLI**

```python
# Update setup_command in cconx/cli.py

from .wizard.field_handlers import (
    PortRangeFieldHandler, StringFieldHandler, BooleanFieldHandler, EnvironmentFieldHandler
)

# Add to field handler registration
wizard.register_field_handler("environment", EnvironmentFieldHandler())
```

- [ ] **Step 4: Run environment handler tests**

```bash
cd /workspace/cconx
python -m pytest tests/test_setup_wizard.py::test_environment_field_handler -v
```

Expected: PASS

- [ ] **Step 5: Test environment variable integration**

```bash
cd /workspace/cconx
python -c "from cconx.config import ConfigManager; cm = ConfigManager(); print('ConfigManager ready')"
```

Expected: No errors

- [ ] **Step 6: Commit environment variables support**

```bash
git add cconx/wizard/field_handlers.py cconx/cli.py tests/test_setup_wizard.py
git commit -m "feat: add environment variables field handler"
```

---

## Chunk 5: Volumes Configuration

### Task 5: Implement Volumes Field Handler

**Files:**
- Modify: `cconx/cconx/wizard/field_handlers.py`
- Test: `cconx/tests/test_setup_wizard.py`

- [ ] **Step 1: Add VolumesFieldHandler**

```python
# Add to cconx/wizard/field_handlers.py

class VolumesFieldHandler(FieldHandler):
    """Handler for volume paths configuration."""

    def __init__(self, field_name: str = "enabled_volumes"):
        super().__init__(field_name)

    def prompt(self, current_value: Any) -> Any:
        volumes = current_value.copy() if current_value else []

        print("\n=== CONFIGURE VOLUME PATHS ===")
        print("Configure volume paths to mount in containers.")
        print("Paths must start with '/' and be absolute paths.")
        print("Enter one path per line. Enter empty line when finished.\n")

        if volumes:
            print("Current volumes:")
            for vol in volumes:
                print(f"  - {vol}")
            print()

        new_volumes = []

        while True:
            user_input = input("Enter volume path (or empty to finish): ").strip()
            if not user_input:
                break

            if user_input.startswith("/"):
                new_volumes.append(user_input)
                print(f"Added: {user_input}")
            else:
                print("Invalid path. Path must start with '/'.")

        return new_volumes if new_volumes else volumes

    def validate(self, input_value: Any) -> bool:
        if not isinstance(input_value, list):
            return False

        return all(isinstance(path, str) and path.startswith("/") for path in input_value)

    def format(self, input_value: Any) -> Any:
        return list(input_value)

    def get_default(self) -> Any:
        return []

    def get_explanation(self) -> str:
        return "List of volume paths to mount in Docker containers"
```

- [ ] **Step 2: Add volumes handler tests**

```python
# Add to tests/test_setup_wizard.py

def test_volumes_field_handler():
    """Test VolumesFieldHandler functionality."""
    from cconx.wizard.field_handlers import VolumesFieldHandler

    handler = VolumesFieldHandler()

    assert handler.field_name == "enabled_volumes"
    assert "volume paths" in handler.get_explanation().lower()

    # Test validation
    assert handler.validate(["/path1", "/path2"]) == True
    assert handler.validate(["relative/path"]) == False  # Must start with /
    assert handler.validate([""]) == False  # Empty path
    assert handler.validate("not_a_list") == False

    # Test formatting
    formatted = handler.format(["/path1", "/path2"])
    assert formatted == ["/path1", "/path2"]
```

- [ ] **Step 3: Register volumes handler in CLI**

```python
# Update setup_command in cconx/cli.py

from .wizard.field_handlers import (
    PortRangeFieldHandler, StringFieldHandler, BooleanFieldHandler,
    EnvironmentFieldHandler, VolumesFieldHandler
)

# Add to field handler registration
wizard.register_field_handler("enabled_volumes", VolumesFieldHandler())
```

- [ ] **Step 4: Run volumes handler tests**

```bash
cd /workspace/cconx
python -m pytest tests/test_setup_wizard.py::test_volumes_field_handler -v
```

Expected: PASS

- [ ] **Step 5: Commit volumes support**

```bash
git add cconx/wizard/field_handlers.py cconx/cli.py tests/test_setup_wizard.py
git commit -m "feat: add volumes configuration field handler"
```

---

## Chunk 6: Integration Testing

### Task 6: Comprehensive Integration Testing

**Files:**
- Modify: `cconx/tests/test_setup_wizard.py`
- Modify: `cconx/tests/test_config.py`

- [ ] **Step 1: Add end-to-end integration test**

```python
# Add to tests/test_setup_wizard.py

import tempfile
import json


def test_end_to_end_wizard_flow():
    """Test complete wizard flow with actual file operations."""
    from cconx.config import ConfigManager
    from cconx.wizard.setup_wizard import SetupWizard
    from cconx.wizard.field_handlers import (
        PortRangeFieldHandler, StringFieldHandler, BooleanFieldHandler,
        EnvironmentFieldHandler, VolumesFieldHandler
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create config manager with temp directory
        config_manager = ConfigManager(tmpdir)

        # Create wizard
        wizard = SetupWizard(config_manager)

        # Register all field handlers
        wizard.register_field_handler("port_range", PortRangeFieldHandler())
        wizard.register_field_handler(
            "default_image",
            StringFieldHandler(
                "default_image",
                "Default Docker image",
                "tylercollison2089/vscode-claude:latest"
            )
        )
        wizard.register_field_handler(
            "include_docker_sock",
            BooleanFieldHandler("include_docker_sock", "Mount Docker socket", True)
        )
        wizard.register_field_handler("environment", EnvironmentFieldHandler())
        wizard.register_field_handler("enabled_volumes", VolumesFieldHandler())

        # Mock user input for testing
        def mock_input(prompt):
            if "Minimum port" in prompt:
                return "8000"
            elif "Maximum port" in prompt:
                return "9000"
            elif "Default Docker image" in prompt:
                return "test-image:latest"
            elif "Enable?" in prompt:
                return "yes"
            elif "NIM_API_KEY" in prompt:
                return "test-nim-key"
            elif "empty to finish" in prompt:
                return ""
            else:
                return ""

        # Test wizard execution
        with patch('builtins.input', mock_input):
            with patch('builtins.print'):  # Suppress output
                result = wizard.run()

        # Verify result structure
        assert "port_range" in result
        assert "default_image" in result
        assert "include_docker_sock" in result
        assert "environment" in result
        assert "enabled_volumes" in result

        # Verify specific values
        assert result["port_range"] == {"min": 8000, "max": 9000}
        assert result["default_image"] == "test-image:latest"
        assert result["include_docker_sock"] == True
        assert "NIM_API_KEY" in result["environment"]
        assert result["environment"]["NIM_API_KEY"] == "test-nim-key"
```

- [ ] **Step 2: Add CLI command test**

```python
# Add to tests/test_setup_wizard.py

def test_cli_setup_command():
    """Test CLI setup command execution."""
    import argparse
    from cconx.cli import setup_command
    from unittest.mock import patch, MagicMock

    # Create mock args
    mock_args = MagicMock()

    with patch('cconx.cli.ConfigManager') as mock_config_manager_class:
        mock_config_manager = MagicMock()
        mock_config_manager_class.return_value = mock_config_manager
        mock_config_manager.load_global_config.return_value = {}

        with patch('cconx.cli.SetupWizard') as mock_wizard_class:
            mock_wizard = MagicMock()
            mock_wizard_class.return_value = mock_wizard
            mock_wizard.run.return_value = {"test": "config"}

            # Mock user input
            with patch('builtins.input', lambda x: ""):
                setup_command(mock_args)

            # Verify wizard was called
            mock_wizard.run.assert_called_once()
            mock_config_manager._save_config.assert_called_once_with({"test": "config"})
```

- [ ] **Step 3: Extend existing config tests**

```python
# Add to tests/test_config.py

def test_config_manager_setup_wizard_integration():
    """Test ConfigManager integration with setup wizard."""
    import tempfile
    from cconx.config import ConfigManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_manager = ConfigManager(tmpdir)

        # Test that setup wizard method exists
        assert hasattr(config_manager, 'run_setup_wizard')

        # Test method returns a dictionary
        with patch('cconx.config.SetupWizard') as mock_wizard:
            mock_instance = MagicMock()
            mock_wizard.return_value = mock_instance
            mock_instance.run.return_value = {"test": "value"}

            result = config_manager.run_setup_wizard()
            assert result == {"test": "value"}
```

- [ ] **Step 4: Run comprehensive tests**

```bash
cd /workspace/cconx
python -m pytest tests/test_setup_wizard.py tests/test_config.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Final commit for integration testing**

```bash
git add tests/test_setup_wizard.py tests/test_config.py
git commit -m "test: add comprehensive integration tests for setup wizard"
```

---

## Next Steps

After completing Phase 1 (Chunks 1-6), the setup wizard will be functional with:
- ✅ Core framework with FieldHandler classes
- ✅ Essential field handlers (port_range, default_image, environment, enabled_volumes, include_docker_sock)
- ✅ CLI integration with `cconx setup` command
- ✅ Comprehensive testing suite
- ✅ Environment variables with special ClaudeConX variable support

**Phase 2** would then focus on:
- Advanced field handlers (docker_network, dns_servers)
- Enhanced environment variable subgroup management
- External validation (Docker network checking)
- User experience improvements

**Ready for implementation!**