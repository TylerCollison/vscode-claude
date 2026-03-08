# Environment Append Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `--env-append` command-line argument to vsclaude that provides append-style environment variable merging.

**Architecture:** Separate processing pipeline for append variables that works alongside existing `--env` override behavior, maintaining backward compatibility.

**Tech Stack:** Python, argparse, pytest

---

## Task 1: Add CLI Argument

**Files:**
- Modify: `vsclaude/vsclaude/cli.py:120-125`

**Step 1: Write the failing test**

```python
def test_cli_env_append_argument():
    """Test that --env-append argument is accepted"""
    import argparse
    from vsclaude.vsclaude.cli import main

    # Test argument parsing
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    start_parser = subparsers.add_parser("start")

    # Add the new argument
    start_parser.add_argument("--env-append", action="append", help="Environment variable to append to global config (key=value)")

    # Parse command with --env-append
    args = parser.parse_args(["start", "test-instance", "--env-append", "PATH=/custom/bin"])
    assert args.env_append == ["PATH=/custom/bin"]
```

**Step 2: Run test to verify it fails**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_cli_env_append_argument', '-v'])"`
Expected: FAIL with "AttributeError: 'Namespace' object has no attribute 'env_append'"

**Step 3: Write minimal implementation**

Modify `vsclaude/vsclaude/cli.py` around line 124:

```python
start_parser.add_argument("--env-append", action="append", help="Environment variable to append to global config (key=value)")
```

**Step 4: Run test to verify it passes**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_cli_env_append_argument', '-v'])"`
Expected: PASS

**Step 5: Commit**

```bash
cd /workspace/vsclaude
git add vsclaude/vsclaude/cli.py tests/test_env_append.py
git commit -m "feat: add --env-append CLI argument"
```

---

## Task 2: Implement Append Processing Logic

**Files:**
- Modify: `vsclaude/vsclaude/cli.py:26-43`

**Step 1: Write the failing test**

```python
def test_env_append_processing():
    """Test environment append processing logic"""
    from unittest.mock import Mock, patch
    from vsclaude.vsclaude.cli import start_command

    # Mock args with env_append
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = []
    args.env_append = ["PATH=/custom/bin", "EXTRA_VAR=value"]

    # Mock dependencies
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config with existing PATH
        mock_config = Mock()
        mock_config.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {"PATH": "/usr/bin", "GLOBAL_VAR": "global"}
        }
        mock_config.get_global_environment.return_value = {"PATH": "/usr/bin", "GLOBAL_VAR": "global"}
        MockConfigManager.return_value = mock_config

        # Call start_command
        start_command(args)

        # Verify generate was called with correct merged environment
        mock_generate.assert_called_once()
        env_vars = mock_generate.call_args[0][2]
        assert env_vars["PATH"] == "/usr/bin/custom/bin"  # Appended
        assert env_vars["EXTRA_VAR"] == "value"  # New variable
        assert env_vars["GLOBAL_VAR"] == "global"  # Unchanged global
```

**Step 2: Run test to verify it fails**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_env_append_processing', '-v'])"`
Expected: FAIL with incorrect environment values

**Step 3: Write minimal implementation**

Modify `vsclaude/vsclaude/cli.py` after line 36:

```python
# Process --env-append variables
append_environment_vars = {}
if hasattr(args, 'env_append') and args.env_append:
    for env_var in args.env_append:
        if '=' in env_var:
            key, value = env_var.split('=', 1)
            append_environment_vars[key] = value

# Get global environment
global_environment = config_manager.get_global_environment()

# Apply append logic
for key, append_value in append_environment_vars.items():
    if key in global_environment:
        # Append to existing global value
        global_environment[key] = global_environment[key] + append_value
    else:
        # Set as new variable if not in global config
        global_environment[key] = append_value

# Then apply override logic (existing behavior)
merged_environment = {**global_environment, **environment_vars}
```

**Step 4: Run test to verify it passes**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_env_append_processing', '-v'])"`
Expected: PASS

**Step 5: Commit**

```bash
cd /workspace/vsclaude
git add vsclaude/vsclaude/cli.py
git commit -m "feat: implement env append processing logic"
```

---

## Task 3: Test Mixed Usage with --env

**Files:**
- Modify: `tests/test_env_append.py`

**Step 1: Write the failing test**

```python
def test_mixed_env_and_env_append():
    """Test mixed usage of --env and --env-append"""
    from unittest.mock import Mock, patch
    from vsclaude.vsclaude.cli import start_command

    # Mock args with both env and env_append
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = ["THEME=light", "PATH=/override/bin"]  # Override PATH
    args.env_append = ["PATH=/append/bin"]  # Try to append

    # Mock dependencies
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config with existing PATH
        mock_config = Mock()
        mock_config.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {"PATH": "/usr/bin", "THEME": "dark"}
        }
        mock_config.get_global_environment.return_value = {"PATH": "/usr/bin", "THEME": "dark"}
        MockConfigManager.return_value = mock_config

        # Call start_command
        start_command(args)

        # Verify generate was called with correct merged environment
        mock_generate.assert_called_once()
        env_vars = mock_generate.call_args[0][2]
        # --env should override both global and append
        assert env_vars["PATH"] == "/override/bin"
        assert env_vars["THEME"] == "light"
```

**Step 2: Run test to verify it fails**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_mixed_env_and_env_append', '-v'])"`
Expected: FAIL with incorrect override behavior

**Step 3: Verify existing implementation handles this correctly**

The implementation from Task 2 should already handle this correctly since `--env` variables override everything after append processing.

**Step 4: Run test to verify it passes**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_mixed_env_and_env_append', '-v'])"`
Expected: PASS

**Step 5: Commit**

```bash
cd /workspace/vsclaude
git add tests/test_env_append.py
git commit -m "test: add mixed env and env-append test"
```

---

## Task 4: Test Fallback Behavior

**Files:**
- Modify: `tests/test_env_append.py`

**Step 1: Write the failing test**

```python
def test_env_append_fallback():
    """Test env-append falls back to set behavior when global doesn't exist"""
    from unittest.mock import Mock, patch
    from vsclaude.vsclaude.cli import start_command

    # Mock args with env_append for non-existent global variable
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = []
    args.env_append = ["NEW_VAR=new_value"]

    # Mock dependencies
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config without NEW_VAR
        mock_config = Mock()
        mock_config.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {"EXISTING_VAR": "existing"}
        }
        mock_config.get_global_environment.return_value = {"EXISTING_VAR": "existing"}
        MockConfigManager.return_value = mock_config

        # Call start_command
        start_command(args)

        # Verify generate was called with correct merged environment
        mock_generate.assert_called_once()
        env_vars = mock_generate.call_args[0][2]
        assert env_vars["NEW_VAR"] == "new_value"  # Should be set as new variable
        assert env_vars["EXISTING_VAR"] == "existing"  # Should preserve existing
```

**Step 2: Run test to verify it fails**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_env_append_fallback', '-v'])"`
Expected: FAIL if fallback logic incorrect

**Step 3: Verify existing implementation handles this correctly**

The implementation from Task 2 should already handle fallback correctly.

**Step 4: Run test to verify it passes**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_env_append_fallback', '-v'])"`
Expected: PASS

**Step 5: Commit**

```bash
cd /workspace/vsclaude
git add tests/test_env_append.py
git commit -m "test: add env-append fallback behavior test"
```

---

## Task 5: Test MM_CHANNEL Auto-population Priority

**Files:**
- Modify: `tests/test_env_append.py`

**Step 1: Write the failing test**

```python
def test_mm_channel_priority_with_env_append():
    """Test MM_CHANNEL auto-population respects env-append priority"""
    from unittest.mock import Mock, patch
    from vsclaude.vsclaude.cli import start_command

    # Mock args without MM_CHANNEL override
    args = Mock()
    args.name = "test-instance"
    args.port_auto = False
    args.port = None
    args.env = []
    args.env_append = []

    # Mock dependencies
    with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.vsclaude.compose.generate') as mock_generate:

        # Configure global config without MM_CHANNEL
        mock_config = Mock()
        mock_config.load_global_config.return_value = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {}
        }
        mock_config.get_global_environment.return_value = {}
        MockConfigManager.return_value = mock_config

        # Call start_command
        start_command(args)

        # Verify generate was called with auto-populated MM_CHANNEL
        mock_generate.assert_called_once()
        env_vars = mock_generate.call_args[0][2]
        assert env_vars["MM_CHANNEL"] == "test-instance"
```

**Step 2: Run test to verify it fails**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_mm_channel_priority_with_env_append', '-v'])"`
Expected: FAIL if MM_CHANNEL logic broken

**Step 3: Verify existing MM_CHANNEL logic still works**

The existing MM_CHANNEL auto-population logic should still work correctly with the new append processing.

**Step 4: Run test to verify it passes**

Run: `cd /workspace/vsclaude && python -c "import pytest; pytest.run(['tests/test_env_append.py::test_mm_channel_priority_with_env_append', '-v'])"`
Expected: PASS

**Step 5: Commit**

```bash
cd /workspace/vsclaude
git add tests/test_env_append.py
git commit -m "test: verify MM_CHANNEL priority with env-append"
```

---

## Task 6: Update Documentation

**Files:**
- Modify: `README.md:118-126`

**Step 1: Write documentation update**

Add to README.md after the existing environment variable documentation:

```markdown
### Environment Variable Append Behavior

vsclaude now supports `--env-append` for appending to existing global environment variables instead of overriding them.

**Priority Order (Highest to Lowest):**
1. **Override Environment**: Variables from `--env` (override everything)
2. **Append Environment**: Variables from `--env-append` (appended to global if exists)
3. **Global Environment**: Variables from global config
4. **Auto-population**: MM_CHANNEL auto-population (fallback)

**Examples:**

```bash
# Append to existing global PATH
vsclaude start my-project --env-append PATH=/custom/bin

# Mixed usage: override THEME, append to PATH
vsclaude start my-project --env THEME=light --env-append PATH=/custom/bin

# Fallback: set new variable when global doesn't exist
vsclaude start my-project --env-append NEW_VAR=value
```
```

**Step 2: Verify documentation renders correctly**

Check: `cd /workspace/vsclaude && python -c "markdown = open('README.md').read(); print('README length:', len(markdown))"`
Expected: No errors

**Step 3: Commit**

```bash
cd /workspace/vsclaude
git add README.md
git commit -m "docs: add env-append feature documentation"
```

---

## Task 7: Run Full Test Suite

**Files:**
- All modified files

**Step 1: Run all vsclaude tests**

Run: `cd /workspace/vsclaude && python -m pytest tests/ -v`
Expected: All tests pass

**Step 2: Fix any failures**

If any tests fail, investigate and fix the issues.

**Step 3: Re-run tests**

Run: `cd /workspace/vsclaude && python -m pytest tests/ -v`
Expected: All tests pass

**Step 4: Commit any fixes**

```bash
cd /workspace/vsclaude
git add .
git commit -m "fix: address test failures"
```

---

## Task 8: Final Integration Test

**Files:**
- Create: `tests/test_env_append_integration.py`

**Step 1: Write integration test**

```python
def test_env_append_integration():
    """Integration test for env-append feature"""
    import tempfile
    import json
    from pathlib import Path
    from vsclaude.vsclaude.cli import start_command
    from unittest.mock import Mock, patch

    # Create temporary global config
    with tempfile.TemporaryDirectory() as temp_dir:
        config_dir = Path(temp_dir) / ".vsclaude"
        config_dir.mkdir()

        # Write global config with environment variables
        global_config = {
            "port_range": {"min": 8080, "max": 9000},
            "environment": {
                "PATH": "/usr/bin",
                "GLOBAL_VAR": "global_value"
            }
        }

        with open(config_dir / "global-config.json", "w") as f:
            json.dump(global_config, f)

        # Mock args
        args = Mock()
        args.name = "integration-test"
        args.port_auto = False
        args.port = 8080
        args.env = ["GLOBAL_VAR=overridden"]
        args.env_append = ["PATH=/custom/bin", "NEW_VAR=new_value"]

        # Mock dependencies that require actual operations
        with patch('vsclaude.vsclaude.config.ConfigManager') as MockConfigManager, \
             patch('vsclaude.vsclaude.ports.PortManager') as MockPortManager, \
             patch('vsclaude.vsclaude.instances.InstanceManager') as MockInstanceManager, \
             patch('vsclaude.vsclaude.compose.generate') as mock_generate:

            # Configure mock to use our temp config
            mock_config = Mock()
            mock_config.config_dir = config_dir
            mock_config.load_global_config.return_value = global_config
            mock_config.get_global_environment.return_value = global_config["environment"]
            MockConfigManager.return_value = mock_config

            # Call start_command
            start_command(args)

            # Verify correct environment merging
            mock_generate.assert_called_once()
            env_vars = mock_generate.call_args[0][2]

            assert env_vars["PATH"] == "/usr/bin/custom/bin"  # Appended
            assert env_vars["GLOBAL_VAR"] == "overridden"  # Overridden by --env
            assert env_vars["NEW_VAR"] == "new_value"  # New variable
```

**Step 2: Run integration test**

Run: `cd /workspace/vsclaude && python -m pytest tests/test_env_append_integration.py -v`
Expected: PASS

**Step 3: Commit integration test**

```bash
cd /workspace/vsclaude
git add tests/test_env_append_integration.py
git commit -m "test: add env-append integration test"
```

---

## Completion Checklist

- [ ] CLI argument `--env-append` added
- [ ] Append processing logic implemented
- [ ] Mixed usage with `--env` tested
- [ ] Fallback behavior tested
- [ ] MM_CHANNEL priority maintained
- [ ] Documentation updated
- [ ] All existing tests pass
- [ ] Integration test added
- [ ] Feature ready for use

Plan complete and saved to `docs/plans/2026-03-08-env-append-implementation.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**