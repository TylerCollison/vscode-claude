# Docker Image Configuration Guide

## Overview
VSClaude allows you to configure which docker image is used for instances, supporting custom docker images while maintaining backward compatibility with existing deployments.

## Configuration Priority
1. **CLI `--image` flag** (highest priority, per-instance override)
2. **Global config `default_image`** (default for all instances)
3. **Fallback** to `"tylercollison2089/vscode-claude:{image_tag}"` (backward compatibility)

## Implementation Details

The `ConfigManager` class has been extended with default image support:

```python
def get_default_image(self) -> str:
    """Get default docker image from global config"""
    config = self.load_global_config()
    return config.get("default_image", "tylercollison2089/vscode-claude:latest")
```

The CLI `start` command integrates image handling through priority-based image selection:

```python
# Extract image name and tag from --image argument if provided
if args.image:
    # Parse custom image provided via --image flag
    if ':' in args.image:
        image_name, image_tag = args.image.rsplit(':', 1)
    else:
        image_name = args.image
        image_tag = "latest"

    # Validate the image name format before using it
    _validate_image_name(image_name)
else:
    # Use default image from ConfigManager when --image flag is not provided
    default_image = config_manager.get_default_image()
    if ':' in default_image:
        image_name, image_tag = default_image.rsplit(':', 1)
    else:
        image_name = default_image
        image_tag = "latest"
```

## Key Features
- **Priority System**: Custom images (`--image` flag) take precedence over config defaults
- **Image Validation**: All custom images are validated using `_validate_image_name()`
- **Tag Handling**: Supports image names with or without tags (defaults to "latest")
- **Config Integration**: Seamlessly integrates with `ConfigManager.get_default_image()`

## Examples

### Global Configuration
Edit `~/.vsclaude/global-config.json`:

```json
{
  "port_range": {"min": 8000, "max": 9000},
  "default_profile": "default",
  "ide_address_template": "http://{host}:{port}",
  "environment": {},
  "enabled_volumes": [],
  "include_docker_sock": true,
  "default_image": "my-registry/custom-image:tag"
}
```

### Per-Instance Override
```bash
# Use custom image
vsclaude start my-instance --image custom-registry/vscode-claude:dev

# Use global default
vsclaude start my-instance --port-auto

# Use specific tag of default image (backward compatible)
vsclaude start my-instance --image tylercollison2089/vscode-claude:stable
```

### Image Name Formats Supported
- `image-name` (defaults to "latest" tag)
- `image-name:v1.0` (with specific tag)
- `registry/image-name` (with registry prefix)
- `registry/namespace/image-name:tag` (full format)

## Backward Compatibility

- Existing deployments continue to work unchanged
- `image_tag` parameter remains functional
- Fallback mechanism ensures no breaking changes
- Commands without `--image` flag continue to use default behavior

## Error Handling
The implementation provides comprehensive error handling:

- **Invalid Image Names**: Raises `ValueError` with descriptive messages
- **Missing Dependencies**: Falls back to default configuration gracefully
- **Docker Operations**: Handles container creation and start failures

## Image Validation
A comprehensive validation function ensures Docker image names follow proper conventions:

```python
def _validate_image_name(image_name: str) -> None:
    """Validate Docker image name format."""
    # Validates: lowercase letters, digits, hyphens, underscores, dots, slashes
    # Prohibits: uppercase letters, invalid starting/ending characters
    # Maximum length: 255 characters
    # Registry format: registry/namespace/image (up to 3 components)
```

## Compose Generation Integration
The `compose.generate()` function accepts image parameters:

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
    image_name: Optional[str] = None
) -> Dict[str, Any]:
```

## Configuration
Configure the default image in the global configuration file (`~/.vsclaude/global-config.json`):

```json
{
    "default_image": "my-registry/custom-vscode-claude:latest"
}
```

This configuration will be used when the `--image` flag is not provided.