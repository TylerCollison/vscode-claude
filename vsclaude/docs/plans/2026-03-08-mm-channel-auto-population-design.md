# MM_CHANNEL Auto-population Design

**Date**: 2026-03-08
**Author**: Claude Sonnet 4.6
**Status**: Approved

## Overview

Automatically populate the `MM_CHANNEL` environment variable with the instance name, unless overridden by user-provided values via `--env` flag or global configuration.

## Requirements

- Auto-populate `MM_CHANNEL` with instance name when not explicitly set
- Respect existing environment variable priority system
- Maintain backward compatibility
- No breaking changes to existing functionality

## Priority Order (Highest to Lowest)

1. **User Override**: `--env MM_CHANNEL=value` (CLI flag)
2. **Global Configuration**: `MM_CHANNEL` in `~/.vsclaude/global-config.json`
3. **Auto-population**: Instance name (fallback)

## Implementation Details

### Location
- **File**: `/workspace/vsclaude/vsclaude/cli.py`
- **Function**: `start_command()`
- **Line**: After environment variable merging (line 36)

### Code Changes

```python
# Current code (line 36):
merged_environment = {**global_environment, **environment_vars}

# New code to add after line 36:
# Auto-populate MM_CHANNEL with instance name, respecting priority
if 'MM_CHANNEL' not in environment_vars:  # Not overridden by user
    if 'MM_CHANNEL' not in global_environment:  # Not set globally
        merged_environment['MM_CHANNEL'] = args.name  # Auto-populate
    # Else: use global config value (already merged)
```

### Flow Logic

```
User provides --env MM_CHANNEL=custom → Use "custom" (highest priority)
No --env flag, global config has MM_CHANNEL=global → Use "global"
No --env flag, no global MM_CHANNEL → Use instance name (auto-populate)
```

## Testing Strategy

### Unit Tests
- Verify MM_CHANNEL auto-population in `start_command()`
- Test priority order: --env → global → auto-pop
- Ensure existing functionality unaffected

### Integration Tests
- Verify MM_CHANNEL flows correctly to Docker Compose
- Test end-to-end environment variable propagation

### Test Scenarios
1. **Override**: `vsclaude start my-project --env MM_CHANNEL=custom` → MM_CHANNEL="custom"
2. **Global**: Global config has `MM_CHANNEL=global` → MM_CHANNEL="global"
3. **Auto-pop**: No global, no --env → MM_CHANNEL="my-project"

## Backward Compatibility

- **No breaking changes**: Existing instances continue working
- **Transparent**: Users unaware of MM_CHANNEL won't notice any difference
- **Optional**: Users can still override via `--env MM_CHANNEL=...`

## Security Considerations

- Uses existing instance name validation (safe characters, length limits)
- No new security risks introduced
- Environment variable validation already ensures proper formatting

## Documentation Updates

Update README.md to document the auto-population behavior:

```markdown
### MM_CHANNEL Auto-population

vsclaude automatically populates the `MM_CHANNEL` environment variable with the instance name, unless overridden:

- Highest priority: `--env MM_CHANNEL=custom`
- Medium priority: Global config `MM_CHANNEL` setting
- Lowest priority: Instance name auto-population

Example: `vsclaude start my-project` → MM_CHANNEL="my-project"
```

## Success Criteria

- MM_CHANNEL automatically populated with instance name when not set
- User overrides via --env flag respected
- Global configuration MM_CHANNEL values respected
- Existing functionality remains unchanged
- Tests pass for all priority scenarios