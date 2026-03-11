# Port Auto Flag Removal Design

**Date**: 2026-03-10
**Author**: Claude Sonnet 4.6
**Status**: Approved

## Overview
Remove the `--port-auto` flag from vsclaude CLI and make port auto-allocation the default behavior when `--port` flag is not provided.

## Problem Statement
The current vsclaude CLI has redundant port configuration options:
- `--port-auto`: Explicitly requests auto-allocation
- `--port`: Specifies a specific port
- Default behavior: Uses minimum port from config

This creates confusion and complexity. The `--port-auto` behavior should be the default when no port is specified.

## Design Decisions

### 1. Flag Removal Strategy
- **Approach**: Complete removal of `--port-auto` flag
- **Rationale**: Simplest and cleanest solution, eliminates confusion
- **Migration**: Users must remove `--port-auto` from existing scripts

### 2. Default Behavior Change
- **Before**: Default = minimum port from config
- **After**: Default = auto-allocate available port
- **Rationale**: Auto-allocation is safer and more user-friendly

### 3. Port Logic Priority
- **Current**: `--port-auto` → `--port` → minimum port
- **New**: `--port` → auto-allocation (no fallback)

## Implementation Plan

### Files to Modify
1. `vsclaude/cli.py`
   - Remove `--port-auto` argument definition
   - Update port selection logic
2. `tests/test_cli_integration.py`
   - Remove `port_auto=True` from test arguments
   - Update tests for new default behavior
3. `tests/test_ports.py`
   - Ensure port auto-allocation tests still work

### Code Changes

#### CLI Argument Parsing
```python
# Remove this line:
start_parser.add_argument("--port-auto", action="store_true", help="Auto-allocate port")
```

#### Port Selection Logic
```python
# Current:
if args.port_auto:
    port = port_manager.find_available_port()
elif args.port:
    port = args.port
else:
    port = global_config["port_range"]["min"]

# New:
if args.port:
    port = args.port
else:
    port = port_manager.find_available_port()
```

## Testing Strategy

### Test Cases
1. **No port flags**: Verify auto-allocation occurs
2. **With --port flag**: Verify specific port is used
3. **Port range exhausted**: Verify error handling
4. **Docker unavailable**: Verify fallback behavior

### Backward Compatibility
- **Breaking change**: Scripts using `--port-auto` will fail
- **Migration**: Simple removal of `--port-auto` flag
- **Benefit**: Cleaner CLI interface

## User Impact

### Before vs After
```bash
# Before:
vsclaude start my-instance                    # Uses port 8000
vsclaude start my-instance --port-auto        # Auto-allocates port
vsclaude start my-instance --port 8080        # Uses port 8080

# After:
vsclaude start my-instance                    # Auto-allocates port
vsclaude start my-instance --port 8080        # Uses port 8080
```

### Migration Guide
- Remove `--port-auto` flag from all scripts
- No other changes required
- Behavior remains the same for auto-allocation scenarios

## Risk Assessment

### Low Risk
- Core port allocation logic unchanged
- Only CLI interface modified
- Existing `--port` functionality preserved

### Medium Risk
- Breaking change for scripts using `--port-auto`
- Requires user migration

## Success Criteria
- [ ] `--port-auto` flag removed from CLI
- [ ] Default behavior changed to auto-allocation
- [ ] All tests pass
- [ ] Existing `--port` functionality preserved
- [ ] Auto-allocation works correctly

## Future Considerations
- Consider adding `--port-min` flag to specify fallback port
- Consider port range validation for `--port` flag
- Consider port conflict detection

## Approval
✅ **Approved by user** - Proceed with implementation