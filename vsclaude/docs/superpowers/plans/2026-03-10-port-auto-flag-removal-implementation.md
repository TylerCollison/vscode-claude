# Port Auto Flag Removal Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove --port-auto flag from vsclaude CLI and make port auto-allocation the default behavior

**Architecture:** Modify CLI argument parsing and port selection logic to eliminate --port-auto flag while preserving --port functionality

**Tech Stack:** Python, argparse, Docker SDK

---

## Chunk 1: CLI Argument Parsing Changes

### Task 1: Remove --port-auto flag from CLI argument parser

**Files:**
- Modify: `vsclaude/cli.py:279-280`

- [ ] **Step 1: Remove --port-auto argument definition**

```python
# Remove this line:
start_parser.add_argument("--port-auto", action="store_true", help="Auto-allocate port")
```

- [ ] **Step 2: Run CLI help to verify flag removal**

Run: `cd /workspace/vsclaude && python -c "from vsclaude.cli import main; main()" start --help`
Expected: Help output should NOT contain "--port-auto" flag

- [ ] **Step 3: Commit CLI changes**

```bash
cd /workspace/vsclaude
git add vsclaude/cli.py
git commit -m "feat: remove --port-auto flag from CLI argument parser"
```

### Task 2: Update port selection logic

**Files:**
- Modify: `vsclaude/cli.py:36-41`

- [ ] **Step 1: Update port selection logic**

```python
# Current logic (lines 36-41):
if args.port_auto:
    port = port_manager.find_available_port()
elif args.port:
    port = args.port
else:
    port = global_config["port_range"]["min"]

# Replace with:
if args.port:
    port = args.port
else:
    port = port_manager.find_available_port()
```

- [ ] **Step 2: Run basic CLI test to verify no syntax errors**

Run: `cd /workspace/vsclaude && python -c "from vsclaude.cli import main; print('CLI imports successfully')"`
Expected: "CLI imports successfully" with no errors

- [ ] **Step 3: Commit port logic changes**

```bash
cd /workspace/vsclaude
git add vsclaude/cli.py
git commit -m "feat: update port selection logic to auto-allocate by default"
```

## Chunk 2: Test Updates

### Task 3: Update CLI integration tests

**Files:**
- Modify: `tests/test_cli_integration.py`

- [ ] **Step 1: Remove port_auto=True from all test arguments**

Search and replace all occurrences of `port_auto=True` with `port=None` in test arguments:

```python
# Before:
args = argparse.Namespace(
    name="test-instance",
    port_auto=True,
    port=None,
    # ...
)

# After:
args = argparse.Namespace(
    name="test-instance",
    port=None,
    # ...
)
```

- [ ] **Step 2: Run tests to verify they still work with new logic**

Run: `cd /workspace/vsclaude && python -m pytest tests/test_cli_integration.py -v`
Expected: All tests should pass with auto-allocation behavior

- [ ] **Step 3: Commit test updates**

```bash
cd /workspace/vsclaude
git add tests/test_cli_integration.py
git commit -m "test: update CLI integration tests for port auto-allocation default"
```

### Task 4: Add test for new default behavior

**Files:**
- Modify: `tests/test_cli_integration.py`

- [ ] **Step 1: Add test for default auto-allocation behavior**

Add this test function to the end of the file:

```python
def test_start_command_default_port_auto_allocation():
    """Test that start command auto-allocates port by default when no port flags provided"""
    from vsclaude.cli import start_command

    # Create mock arguments without any port flags
    args = argparse.Namespace(
        name="test-instance",
        port=None,  # No --port flag
        env=[],
        env_append=[],
        image=None
    )

    with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.compose.generate') as mock_generate, \
         patch('vsclaude.docker.DockerClient') as MockDockerClient:

        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.format_ide_address.return_value = "http://localhost:8080"

        mock_port_manager = MockPortManager.return_value
        mock_port_manager.find_available_port.return_value = 8080  # Auto-allocated port

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "test-instance", "port": 8080
        }

        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "tylercollison2089/vscode-claude:latest",
                    "ports": ["8080:8080"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify auto-allocation was used
            mock_port_manager.find_available_port.assert_called_once()
            mock_print.assert_any_call("Instance 'test-instance' configured on port 8080")
```

- [ ] **Step 2: Run the new test**

Run: `cd /workspace/vsclaude && python -m pytest tests/test_cli_integration.py::test_start_command_default_port_auto_allocation -v`
Expected: Test should pass

- [ ] **Step 3: Commit new test**

```bash
cd /workspace/vsclaude
git add tests/test_cli_integration.py
git commit -m "test: add test for default port auto-allocation behavior"
```

### Task 5: Verify port-specific flag still works

**Files:**
- Modify: `tests/test_cli_integration.py`

- [ ] **Step 1: Add test for --port flag functionality**

Add this test function:

```python
def test_start_command_with_port_flag():
    """Test that --port flag still works correctly after --port-auto removal"""
    from vsclaude.cli import start_command

    # Create mock arguments with --port flag
    args = argparse.Namespace(
        name="test-instance",
        port=9090,  # Specific port
        env=[],
        env_append=[],
        image=None
    )

    with patch('vsclaude.config.ConfigManager') as MockConfigManager, \
         patch('vsclaude.ports.PortManager') as MockPortManager, \
         patch('vsclaude.instances.InstanceManager') as MockInstanceManager, \
         patch('vsclaude.compose.generate') as mock_generate, \
         patch('vsclaude.docker.DockerClient') as MockDockerClient:

        mock_config_manager = MockConfigManager.return_value
        mock_config_manager.load_global_config.return_value = {
            "port_range": {"min": 8000, "max": 9000},
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True
        }
        mock_config_manager.get_global_environment.return_value = {}
        mock_config_manager.get_enabled_volumes.return_value = []
        mock_config_manager.get_include_docker_sock.return_value = True
        mock_config_manager.format_ide_address.return_value = "http://localhost:9090"

        mock_port_manager = MockPortManager.return_value
        # Port manager should NOT be called for auto-allocation

        mock_instance_manager = MockInstanceManager.return_value
        mock_instance_manager.create_instance_config.return_value = {
            "name": "test-instance", "port": 9090
        }

        mock_docker_client = MockDockerClient.return_value
        mock_container = MagicMock()
        mock_docker_client.client.containers.create.return_value = mock_container

        mock_generate.return_value = {
            "services": {
                "vscode-claude": {
                    "image": "tylercollison2089/vscode-claude:latest",
                    "ports": ["9090:9090"],
                    "environment": ["KEY=VALUE"],
                    "volumes": []
                }
            }
        }

        with patch('builtins.print') as mock_print:
            result = start_command(args)

            # Verify specific port was used (not auto-allocation)
            mock_port_manager.find_available_port.assert_not_called()
            mock_print.assert_any_call("Instance 'test-instance' configured on port 9090")
```

- [ ] **Step 2: Run the port flag test**

Run: `cd /workspace/vsclaude && python -m pytest tests/test_cli_integration.py::test_start_command_with_port_flag -v`
Expected: Test should pass

- [ ] **Step 3: Commit port flag test**

```bash
cd /workspace/vsclaude
git add tests/test_cli_integration.py
git commit -m "test: add test for --port flag functionality preservation"
```

## Chunk 3: Final Verification

### Task 6: Run comprehensive test suite

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `cd /workspace/vsclaude && python -m pytest tests/ -v`
Expected: All tests should pass

- [ ] **Step 2: Verify CLI help output**

Run: `cd /workspace/vsclaude && python -c "from vsclaude.cli import main; main()" start --help`
Expected: Help should show only --port flag, no --port-auto

- [ ] **Step 3: Create final commit with all changes**

```bash
cd /workspace/vsclaude
git add .
git commit -m "feat: complete port auto flag removal - auto-allocation now default behavior"
```

## Chunk 4: Documentation Update (Optional)

### Task 7: Update README if needed

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Check README for --port-auto references**

Run: `cd /workspace/vsclaude && grep -n "port-auto" README.md`
If matches found, update documentation

- [ ] **Step 2: Update documentation if necessary**

If README mentions --port-auto flag, remove those references and update examples:

```markdown
# Before:
vsclaude start my-instance --port-auto

# After:
vsclaude start my-instance  # Auto-allocates port by default
```

- [ ] **Step 3: Commit documentation updates**

```bash
cd /workspace/vsclaude
git add README.md
git commit -m "docs: update README for port auto flag removal"
```

---

## Implementation Notes

- This is a breaking change - scripts using --port-auto will need to be updated
- The migration is simple: remove --port-auto flag from existing scripts
- Auto-allocation behavior is preserved, just becomes the default
- --port flag functionality remains unchanged

## Success Criteria

- [ ] --port-auto flag removed from CLI help
- [ ] Default behavior auto-allocates ports
- [ ] --port flag continues to work
- [ ] All tests pass
- [ ] No regression in existing functionality