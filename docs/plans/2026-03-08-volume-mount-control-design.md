# Volume Mount Control Design

**Date**: 2026-03-08
**Author**: Claude Code
**Status**: Approved

## Overview
Add individual volume mount control to vsclaude global configuration, allowing users to specify exactly which container directories should have persistent storage.

## Design Decisions

### Schema Structure
```json
{
  "enabled_volumes": [],
  "include_docker_sock": true
}
```

### Key Features
- **Flexible volume specification**: Users can specify any container path
- **Docker socket independence**: Socket mount remains separate parameter
- **Security-first defaults**: Empty array means no volumes mounted
- **Path validation**: Volume paths must start with `/`

## Implementation Details

### Volume Mapping Logic
For each entry in `enabled_volumes`:
- **Container path**: e.g., `/config`, `/workspace`, `/data`
- **Volume name**: `{instance_name}-{basename(path)}`
- **Volume mount**: `{volume_name}:{container_path}`

### Example Usage

**Global Config:**
```json
{
  "enabled_volumes": ["/config", "/workspace", "/data"],
  "include_docker_sock": false
}
```

**Result:**
- Named volumes: `instance-config`, `instance-workspace`, `instance-data`
- Mount points: `/config`, `/workspace`, `/data`
- Docker socket: Not mounted

## Backward Compatibility

**Breaking Change:**
- Empty `enabled_volumes` array means NO volumes mounted
- Users must explicitly enable volumes they need
- Docker socket defaults to true for compatibility

**Migration Path:**
- Existing configurations will need to add `enabled_volumes`
- Documentation updates required
- Clear error messages for missing volumes

## Files to Modify

1. `vsclaude/vsclaude/config.py`
   - Add `get_enabled_volumes()` method
   - Add `get_include_docker_sock()` method
   - Add path validation

2. `vsclaude/vsclaude/compose.py`
   - Update `generate()` function parameters
   - Replace hardcoded volume logic
   - Dynamic volume generation

3. `vsclaude/vsclaude/cli.py`
   - Update `start_command()`
   - Pass new parameters to `generate()`

4. Test files
   - Update existing tests
   - Add new test cases

## Validation Rules

- Volume paths must start with `/`
- Duplicate paths are handled gracefully
- Invalid paths generate clear error messages
- Docker socket parameter remains backward compatible

## Success Criteria

- Users can specify exact container paths for persistence
- Docker socket mount remains independent
- Empty config results in no volume mounts
- Path validation prevents invalid configurations
- Backward compatibility maintained for Docker socket