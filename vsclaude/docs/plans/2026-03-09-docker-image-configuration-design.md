# Docker Image Configuration Design

## Overview
Enable configuration of the docker image (and tag) that gets instantiated for VSClaude instances, allowing users to specify custom docker images while maintaining backward compatibility.

## Requirements
- Allow full docker image name configuration (registry/image:tag format)
- Support global default configuration
- Support per-instance override via CLI flag
- Maintain backward compatibility with existing deployments
- Simple, minimal implementation

## Architecture

### Configuration Priority
1. **CLI `--image` flag** (highest priority, per-instance override)
2. **Global config `default_image`** (default for all instances)
3. **Fallback** to `"tylercollison2089/vscode-claude:{image_tag}"` (backward compatibility)

### Data Flow
```
CLI --image flag → Global default_image → Fallback image
      ↓                    ↓                    ↓
compose.generate(image_name=selected_image)
```

## Implementation Details

### Global Configuration Extension
Add `default_image` field to global config (`~/.vsclaude/global-config.json`):

```json
{
  "port_range": {"min": 8000, "max": 9000},
  "default_profile": "default",
  "ide_address_template": "http://{host}:{port}",
  "environment": {},
  "enabled_volumes": [],
  "include_docker_sock": true,
  "default_image": "tylercollison2089/vscode-claude:latest"
}
```

### CLI Interface Extension
Add `--image` flag to `vsclaude start` command:

```bash
# Use custom image
vsclaude start my-instance --image custom-registry/vscode-claude:dev

# Use global default
vsclaude start my-instance --port-auto

# Use specific tag of default image (backward compatible)
vsclaude start my-instance --image tylercollison2089/vscode-claude:stable
```

### compose.py Changes
Extend `generate()` function signature:

```python
def generate(
    instance_name: str,
    port: int,
    environment_vars: Optional[Dict[str, str]] = None,
    image_tag: str = "latest",  # Maintained for backward compatibility
    container_port: int = 8443,
    additional_ports: Optional[List[str]] = None,
    restart_policy: str = "unless-stopped",
    include_docker_sock: bool = True,
    enabled_volumes: Optional[List[str]] = None,
    image_name: Optional[str] = None  # NEW: Full image name override
) -> Dict[str, Any]:
```

### Image Selection Logic
```python
# Determine final image to use
if image_name:
    final_image = image_name
elif global_config.get("default_image"):
    final_image = global_config["default_image"]
else:
    final_image = f"tylercollison2089/vscode-claude:{image_tag}"

# Use in compose config
compose_config = {
    "services": {
        "vscode-claude": {
            "image": final_image,
            # ... rest of config
        }
    }
}
```

## Files to Modify

1. **`vsclaude/config.py`**
   - Add `get_default_image()` method to ConfigManager
   - Update `_default_global_config()` to include default_image

2. **`vsclaude/cli.py`**
   - Add `--image` argument to start command parser
   - Add image selection logic in `start_command()`
   - Pass selected image to `compose.generate()`

3. **`vsclaude/compose.py`**
   - Extend `generate()` function with `image_name` parameter
   - Update image selection logic
   - Maintain backward compatibility

4. **Tests**
   - Add tests for image selection priority
   - Add tests for CLI --image flag
   - Add tests for global default_image config

## Validation Rules

- Image names must follow docker naming conventions
- Support both tagged and untagged images
- Validate image format during configuration

## Backward Compatibility

- Existing deployments continue to work unchanged
- `image_tag` parameter remains functional
- Fallback mechanism ensures no breaking changes

## Testing Strategy

1. **Unit Tests**: Image selection logic, config parsing
2. **Integration Tests**: CLI flag functionality, global config
3. **Backward Compatibility Tests**: Ensure existing behavior unchanged

## Migration Path

No migration required - existing configurations continue to work as-is.

## Success Criteria

- Users can specify custom docker images via CLI flag
- Global default image configuration works
- Backward compatibility maintained
- All existing tests pass
- New functionality properly tested