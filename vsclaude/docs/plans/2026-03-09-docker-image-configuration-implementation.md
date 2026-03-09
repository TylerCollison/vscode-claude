# Docker Image Configuration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable configuration of docker image (and tag) for VSClaude instances with global defaults and per-instance overrides.

**Architecture:** Extend existing compose system with image_name parameter, add CLI --image flag, maintain backward compatibility.

**Tech Stack:** Python, Docker SDK, argparse, pytest

---

## Task 1: Extend ConfigManager with default_image support

**Files:**
- Modify: `vsclaude/config.py:17-25`
- Test: `tests/test_config.py`

**Step 1: Write the failing test**

```python
def test_get_default_image():
    config_manager = ConfigManager()
    config = config_manager.load_global_config()

    # Test default value
    default_image = config_manager.get_default_image()
    assert default_image == "tylercollison2089/vscode-claude:latest"

    # Test custom value
    config["default_image"] = "custom-registry/image:tag"
    config_manager._save_config(config)
    custom_image = config_manager.get_default_image()
    assert custom_image == "custom-registry/image:tag"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_get_default_image -v`
Expected: FAIL with "AttributeError: 'ConfigManager' object has no attribute 'get_default_image'"

**Step 3: Write minimal implementation**

```python
class ConfigManager:
    # ... existing code ...

    def get_default_image(self) -> str:
        """Get default docker image from global config"""
        config = self.load_global_config()
        return config.get("default_image", "tylercollison2089/vscode-claude:latest")

    def _default_global_config(self):
        return {
            "port_range": {"min": 8000, "max": 9000},
            "default_profile": "default",
            "ide_address_template": "http://{host}:{port}",
            "environment": {},
            "enabled_volumes": [],
            "include_docker_sock": True,
            "default_image": "tylercollison2089/vscode-claude:latest"  # NEW
        }
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_get_default_image -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vsclaude/config.py tests/test_config.py
git commit -m "feat: add default_image support to ConfigManager"
```

---

## Task 2: Extend compose.generate() with image_name parameter

**Files:**
- Modify: `vsclaude/compose.py:5-15` (function signature)
- Modify: `vsclaude/compose.py:75-89` (image selection)
- Test: `tests/test_compose.py`

**Step 1: Write the failing test**

```python
def test_generate_with_custom_image():
    # Test custom image override
    config = generate(
        instance_name="test-instance",
        port=8080,
        image_name="custom-registry/vscode-claude:dev"
    )
    assert config["services"]["vscode-claude"]["image"] == "custom-registry/vscode-claude:dev"

def test_generate_with_default_image():
    # Test default image behavior
    config = generate(
        instance_name="test-instance",
        port=8080
    )
    assert config["services"]["vscode-claude"]["image"] == "tylercollison2089/vscode-claude:latest"

def test_generate_with_image_tag_backward_compat():
    # Test backward compatibility
    config = generate(
        instance_name="test-instance",
        port=8080,
        image_tag="stable"
    )
    assert config["services"]["vscode-claude"]["image"] == "tylercollison2089/vscode-claude:stable"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_compose.py::test_generate_with_custom_image -v`
Expected: FAIL with "TypeError: generate() got an unexpected keyword argument 'image_name'"

**Step 3: Write minimal implementation**

```python
def generate(
    instance_name: str,
    port: int,
    environment_vars: Optional[Dict[str, str]] = None,
    image_tag: str = "latest",
    container_port: int = 8443,
    additional_ports: Optional[List[str]] = None,
    restart_policy: str = "unless-stopped",
    include_docker_sock: bool = True,
    enabled_volumes: Optional[List[str]] = None,
    image_name: Optional[str] = None  # NEW
) -> Dict[str, Any]:
    # ... existing validation code ...

    # Determine final image
    if image_name:
        final_image = image_name
    else:
        final_image = f"tylercollison2089/vscode-claude:{image_tag}"

    compose_config = {
        "services": {
            "vscode-claude": {
                "image": final_image,  # UPDATED
                "container_name": f"vsclaude-{instance_name}",
                "ports": ports,
                "environment": [f"{k}={v}" for k, v in environment.items()],
                "volumes": volumes,
                "restart": restart_policy
            }
        },
        "volumes": volume_definitions
    }

    return compose_config
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_compose.py::test_generate_with_custom_image -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vsclaude/compose.py tests/test_compose.py
git commit -m "feat: extend compose.generate() with image_name parameter"
```

---

## Task 3: Add --image flag to CLI start command

**Files:**
- Modify: `vsclaude/cli.py:195-201` (argument parser)
- Modify: `vsclaude/cli.py:64-79` (start_command image selection)
- Test: `tests/test_integration.py`

**Step 1: Write the failing test**

```python
def test_cli_start_with_image_flag():
    # Test CLI with --image flag
    runner = CliRunner()
    result = runner.invoke(main, ["start", "test-instance", "--image", "custom/image:tag"])
    assert result.exit_code == 0
    assert "custom/image:tag" in result.output

def test_cli_start_without_image_flag():
    # Test CLI without --image flag (should use default)
    runner = CliRunner()
    result = runner.invoke(main, ["start", "test-instance"])
    assert result.exit_code == 0
    assert "tylercollison2089/vscode-claude:latest" in result.output
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_integration.py::test_cli_start_with_image_flag -v`
Expected: FAIL with "error: unrecognized arguments: --image"

**Step 3: Write minimal implementation**

```python
# In start command argument parser (around line 195)
start_parser.add_argument("--image", help="Custom docker image (registry/image:tag)")

# In start_command function (around line 64)
def start_command(args):
    # ... existing code ...

    # Image selection logic
    if args.image:
        selected_image = args.image
    else:
        # Use global default or fallback
        selected_image = config_manager.get_default_image()

    compose_config = generate(
        args.name,
        port,
        merged_environment,
        enabled_volumes=enabled_volumes,
        include_docker_sock=include_docker_sock,
        image_name=selected_image  # NEW
    )

    # ... rest of existing code ...
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_integration.py::test_cli_start_with_image_flag -v`
Expected: PASS

**Step 5: Commit**

```bash
git add vsclaude/cli.py tests/test_integration.py
git commit -m "feat: add --image flag to CLI start command"
```

---

## Task 4: Add comprehensive integration tests

**Files:**
- Create: `tests/test_docker_image_config.py`
- Modify: `tests/test_integration.py`

**Step 1: Write comprehensive test file**

```python
import pytest
from vsclaude.config import ConfigManager
from vsclaude.compose import generate
from vsclaude.cli import start_command
from unittest.mock import Mock, patch

class TestDockerImageConfiguration:
    def test_image_selection_priority(self):
        """Test image selection priority: CLI > global > fallback"""
        # Test CLI flag highest priority
        config = generate("test", 8080, image_name="cli-image")
        assert config["services"]["vscode-claude"]["image"] == "cli-image"

        # Test global config second priority
        config = generate("test", 8080)
        assert config["services"]["vscode-claude"]["image"].startswith("tylercollison2089/vscode-claude")

    def test_backward_compatibility(self):
        """Test that existing image_tag parameter still works"""
        config = generate("test", 8080, image_tag="stable")
        assert config["services"]["vscode-claude"]["image"] == "tylercollison2089/vscode-claude:stable"

    def test_image_name_overrides_tag(self):
        """Test that image_name overrides image_tag"""
        config = generate("test", 8080, image_tag="stable", image_name="custom/image:dev")
        assert config["services"]["vscode-claude"]["image"] == "custom/image:dev"

    @patch('vsclaude.cli.DockerClient')
    @patch('vsclaude.cli.generate')
    def test_cli_image_flag_integration(self, mock_generate, mock_docker):
        """Test CLI integration with --image flag"""
        from vsclaude.cli import start_command

        # Mock args
        args = Mock()
        args.name = "test-instance"
        args.port_auto = False
        args.port = 8080
        args.env = None
        args.env_append = None
        args.image = "custom-registry/image:tag"

        # Mock dependencies
        mock_docker.return_value.client.containers.create.return_value.start.return_value = None

        start_command(args)

        # Verify generate was called with custom image
        mock_generate.assert_called_once()
        call_kwargs = mock_generate.call_args[1]
        assert call_kwargs["image_name"] == "custom-registry/image:tag"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_docker_image_config.py -v`
Expected: Various failures depending on implementation progress

**Step 3: Ensure all tests pass**

Run: `pytest tests/test_docker_image_config.py tests/test_integration.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add tests/test_docker_image_config.py tests/test_integration.py
git commit -m "test: add comprehensive docker image configuration tests"
```

---

## Task 5: Update documentation

**Files:**
- Modify: `README.md`
- Create: `docs/docker-image-configuration.md`

**Step 1: Update README with usage examples**

Add to README.md:

```markdown
## Docker Image Configuration

VSClaude now supports custom docker images:

```bash
# Use custom image
vsclaude start my-instance --image custom-registry/vscode-claude:dev

# Set global default in ~/.vsclaude/global-config.json
{
  "default_image": "my-registry/vscode-claude:stable"
}

# Backward compatible (uses default image with tag)
vsclaude start my-instance --image tylercollison2089/vscode-claude:latest
```
```

**Step 2: Create detailed documentation**

Create `docs/docker-image-configuration.md`:

```markdown
# Docker Image Configuration Guide

## Overview
VSClaude allows you to configure which docker image is used for instances.

## Configuration Priority
1. CLI `--image` flag (highest priority)
2. Global config `default_image`
3. Fallback to `tylercollison2089/vscode-claude:{image_tag}`

## Examples

### Global Configuration
Edit `~/.vsclaude/global-config.json`:

```json
{
  "default_image": "my-registry/custom-image:tag"
}
```

### Per-Instance Override
```bash
vsclaude start dev --image my-registry/dev-image:latest
vsclaude start prod --image my-registry/prod-image:stable
```

### Backward Compatibility
Existing commands continue to work:
```bash
vsclaude start instance  # Uses tylercollison2089/vscode-claude:latest
```
```

**Step 3: Commit documentation**

```bash
git add README.md docs/docker-image-configuration.md
git commit -m "docs: add docker image configuration documentation"
```

---

## Task 6: Final validation and cleanup

**Files:**
- Run: All tests
- Verify: Backward compatibility

**Step 1: Run complete test suite**

```bash
pytest tests/ -v
```
Expected: All tests PASS

**Step 2: Verify backward compatibility**

```bash
# Test existing commands still work
python -m vsclaude.cli start test-instance --port-auto
python -m vsclaude.cli status
```
Expected: No errors, normal operation

**Step 3: Final commit**

```bash
git add .
git commit -m "feat: complete docker image configuration implementation"
```

---

**Plan complete and saved to `docs/plans/2026-03-09-docker-image-configuration-implementation.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**