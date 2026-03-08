# MM_CHANNEL Auto-population Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically populate MM_CHANNEL environment variable with instance name unless overridden

**Architecture:** Inject MM_CHANNEL during environment variable merging in cli.py, respecting priority order (--env → global config → auto-population)

**Tech Stack:** Python 3.8+, pytest, argparse, Docker Compose

---

## Task 1: Add MM_CHANNEL Auto-population Logic

**Files:**
- Modify: `vsclaude/vsclaude/cli.py:36-37`

**Step 1: Write the failing test**

Create: `tests/test_mm_channel_auto_population.py`

```python
import pytest
from unittest.mock import patch, MagicMock
from vsclaude.cli import start_command

class TestMMChannelAutoPopulation:
    def test_mm_channel_auto_populated_when_not_set(self):
        """Test MM_CHANNEL is auto-populated with instance name when not set"""
        args = MagicMock()
        args.name = "test-project"
        args.port_auto = False
        args.port = 8080
        args.env = []

        with patch('vsclaude.cli.ConfigManager') as MockConfigManager, \
             patch('vsclaude.cli.PortManager') as MockPortManager, \
             patch('vsclaude.cli.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.cli.generate') as mock_generate:

            # Mock global config with empty environment
            mock_config_manager = MockConfigManager.return_value
            mock_config_manager.load_global_config.return_value = {
                "port_range": {"min": 8000, "max": 9000},
                "environment": {}
            }
            mock_config_manager.get_global_environment.return_value = {}
            mock_config_manager.format_ide_address.return_value = "http://localhost:8080"

            # Mock port manager
            mock_port_manager = MockPortManager.return_value
            mock_port_manager.find_available_port.return_value = 8080

            # Mock instance manager
            mock_instance_manager = MockInstanceManager.return_value
            mock_instance_manager.create_instance_config.return_value = {
                "name": "test-project", "port": 8080, "environment": {}
            }

            # Execute start command
            result = start_command(args)

            # Verify MM_CHANNEL was added to environment
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args
            environment_vars = call_args[1]['environment_vars']
            assert 'MM_CHANNEL' in environment_vars
            assert environment_vars['MM_CHANNEL'] == 'test-project'

    def test_mm_channel_respects_env_override(self):
        """Test MM_CHANNEL respects --env override"""
        args = MagicMock()
        args.name = "test-project"
        args.port_auto = False
        args.port = 8080
        args.env = ["MM_CHANNEL=custom-channel"]

        with patch('vsclaude.cli.ConfigManager') as MockConfigManager, \
             patch('vsclaude.cli.PortManager') as MockPortManager, \
             patch('vsclaude.cli.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.cli.generate') as mock_generate:

            mock_config_manager = MockConfigManager.return_value
            mock_config_manager.load_global_config.return_value = {
                "port_range": {"min": 8000, "max": 9000},
                "environment": {}
            }
            mock_config_manager.get_global_environment.return_value = {}
            mock_config_manager.format_ide_address.return_value = "http://localhost:8080"

            mock_port_manager = MockPortManager.return_value
            mock_port_manager.find_available_port.return_value = 8080

            mock_instance_manager = MockInstanceManager.return_value
            mock_instance_manager.create_instance_config.return_value = {
                "name": "test-project", "port": 8080, "environment": {}
            }

            result = start_command(args)

            mock_generate.assert_called_once()
            call_args = mock_generate.call_args
            environment_vars = call_args[1]['environment_vars']
            assert environment_vars['MM_CHANNEL'] == 'custom-channel'

    def test_mm_channel_respects_global_config(self):
        """Test MM_CHANNEL respects global config setting"""
        args = MagicMock()
        args.name = "test-project"
        args.port_auto = False
        args.port = 8080
        args.env = []

        with patch('vsclaude.cli.ConfigManager') as MockConfigManager, \
             patch('vsclaude.cli.PortManager') as MockPortManager, \
             patch('vsclaude.cli.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.cli.generate') as mock_generate:

            mock_config_manager = MockConfigManager.return_value
            mock_config_manager.load_global_config.return_value = {
                "port_range": {"min": 8000, "max": 9000},
                "environment": {"MM_CHANNEL": "global-channel"}
            }
            mock_config_manager.get_global_environment.return_value = {"MM_CHANNEL": "global-channel"}
            mock_config_manager.format_ide_address.return_value = "http://localhost:8080"

            mock_port_manager = MockPortManager.return_value
            mock_port_manager.find_available_port.return_value = 8080

            mock_instance_manager = MockInstanceManager.return_value
            mock_instance_manager.create_instance_config.return_value = {
                "name": "test-project", "port": 8080, "environment": {}
            }

            result = start_command(args)

            mock_generate.assert_called_once()
            call_args = mock_generate.call_args
            environment_vars = call_args[1]['environment_vars']
            assert environment_vars['MM_CHANNEL'] == 'global-channel'
```

**Step 2: Run test to verify it fails**

Run: `cd /workspace/vsclaude && python -m pytest tests/test_mm_channel_auto_population.py -v`
Expected: FAIL with "MM_CHANNEL not found in environment"

**Step 3: Write minimal implementation**

Modify: `vsclaude/vsclaude/cli.py:36-37`

```python
# Current line 36:
merged_environment = {**global_environment, **environment_vars}

# Add after line 36:
# Auto-populate MM_CHANNEL with instance name, respecting priority
if 'MM_CHANNEL' not in environment_vars:  # Not overridden by user
    if 'MM_CHANNEL' not in global_environment:  # Not set globally
        merged_environment['MM_CHANNEL'] = args.name  # Auto-populate
    # Else: use global config value (already merged)
```

**Step 4: Run test to verify it passes**

Run: `cd /workspace/vsclaude && python -m pytest tests/test_mm_channel_auto_population.py -v`
Expected: PASS

**Step 5: Commit**

```bash
cd /workspace/vsclaude
git add vsclaude/vsclaude/cli.py tests/test_mm_channel_auto_population.py
git commit -m "feat: add MM_CHANNEL auto-population with instance name"
```

---

## Task 2: Add Integration Test

**Files:**
- Create: `tests/test_mm_channel_integration.py`

**Step 1: Write integration test**

```python
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from vsclaude.cli import start_command

class TestMMChannelIntegration:
    def test_mm_channel_flows_to_compose_generation(self):
        """Test MM_CHANNEL flows correctly to Docker Compose generation"""
        args = MagicMock()
        args.name = "integration-test"
        args.port_auto = False
        args.port = 9090
        args.env = []

        with patch('vsclaude.cli.ConfigManager') as MockConfigManager, \
             patch('vsclaude.cli.PortManager') as MockPortManager, \
             patch('vsclaude.cli.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.cli.generate') as mock_generate:

            mock_config_manager = MockConfigManager.return_value
            mock_config_manager.load_global_config.return_value = {
                "port_range": {"min": 8000, "max": 9000},
                "environment": {}
            }
            mock_config_manager.get_global_environment.return_value = {}
            mock_config_manager.format_ide_address.return_value = "http://localhost:9090"

            mock_port_manager = MockPortManager.return_value
            mock_port_manager.find_available_port.return_value = 9090

            mock_instance_manager = MockInstanceManager.return_value
            mock_instance_manager.create_instance_config.return_value = {
                "name": "integration-test", "port": 9090, "environment": {}
            }

            # Mock compose generation
            mock_generate.return_value = {
                "services": {
                    "vscode-claude": {
                        "environment": ["MM_CHANNEL=integration-test"]
                    }
                }
            }

            result = start_command(args)

            # Verify compose was called with correct MM_CHANNEL
            mock_generate.assert_called_once()
            call_args = mock_generate.call_args
            environment_vars = call_args[1]['environment_vars']
            assert 'MM_CHANNEL' in environment_vars
            assert environment_vars['MM_CHANNEL'] == 'integration-test'

    def test_priority_order_env_trumps_global_trumps_auto(self):
        """Test priority order: --env → global → auto-population"""
        # Test 1: --env flag should win
        args = MagicMock()
        args.name = "priority-test"
        args.port_auto = False
        args.port = 9091
        args.env = ["MM_CHANNEL=env-override"]

        with patch('vsclaude.cli.ConfigManager') as MockConfigManager, \
             patch('vsclaude.cli.PortManager') as MockPortManager, \
             patch('vsclaude.cli.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.cli.generate') as mock_generate:

            mock_config_manager = MockConfigManager.return_value
            mock_config_manager.load_global_config.return_value = {
                "port_range": {"min": 8000, "max": 9000},
                "environment": {"MM_CHANNEL": "global-value"}
            }
            mock_config_manager.get_global_environment.return_value = {"MM_CHANNEL": "global-value"}
            mock_config_manager.format_ide_address.return_value = "http://localhost:9091"

            mock_port_manager = MockPortManager.return_value
            mock_port_manager.find_available_port.return_value = 9091

            mock_instance_manager = MockInstanceManager.return_value
            mock_instance_manager.create_instance_config.return_value = {
                "name": "priority-test", "port": 9091, "environment": {}
            }

            result = start_command(args)

            mock_generate.assert_called_once()
            environment_vars = mock_generate.call_args[1]['environment_vars']
            assert environment_vars['MM_CHANNEL'] == 'env-override'
```

**Step 2: Run integration test**

Run: `cd /workspace/vsclaude && python -m pytest tests/test_mm_channel_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
cd /workspace/vsclaude
git add tests/test_mm_channel_integration.py
git commit -m "test: add MM_CHANNEL integration tests"
```

---

## Task 3: Update Documentation

**Files:**
- Modify: `README.md`

**Step 1: Update README.md**

Add to README.md after "Global Environment Configuration" section:

```markdown
### MM_CHANNEL Auto-population

vsclaude automatically populates the `MM_CHANNEL` environment variable with the instance name, unless overridden by higher priority settings:

**Priority Order (Highest to Lowest):**
1. `--env MM_CHANNEL=value` (user override via CLI)
2. Global config `MM_CHANNEL` setting
3. Instance name auto-population (fallback)

**Examples:**

```bash
# Auto-population: MM_CHANNEL="my-project"
vsclaude start my-project

# User override: MM_CHANNEL="custom-channel"
vsclaude start my-project --env MM_CHANNEL=custom-channel

# Global config: MM_CHANNEL="global-channel" (if set in global-config.json)
vsclaude start my-project
```
```

**Step 2: Verify documentation**

Run: `cd /workspace/vsclaude && python -c "print(open('README.md').read())" | grep -A 10 "MM_CHANNEL Auto-population"`
Expected: See the new documentation section

**Step 3: Commit**

```bash
cd /workspace/vsclaude
git add README.md
git commit -m "docs: document MM_CHANNEL auto-population feature"
```

---

## Task 4: Run Full Test Suite

**Step 1: Run all tests**

Run: `cd /workspace/vsclaude && python -m pytest tests/ -v`
Expected: All tests pass

**Step 2: Final verification**

Run: `cd /workspace/vsclaude && python -c "from vsclaude.cli import start_command; print('Import successful')"`
Expected: "Import successful"

**Step 3: Final commit**

```bash
cd /workspace/vsclaude
git add .
git commit -m "feat: complete MM_CHANNEL auto-population implementation"
```

---

## Success Criteria

- [ ] MM_CHANNEL auto-populated when not set
- [ ] --env flag override works correctly
- [ ] Global config MM_CHANNEL respected
- [ ] Priority order maintained
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Backward compatibility maintained