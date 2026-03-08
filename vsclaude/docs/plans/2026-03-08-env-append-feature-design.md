# Environment Append Feature Design

**Date**: 2026-03-08
**Feature**: `--env-append` command-line argument for vsclaude
**Status**: Approved Design

## Overview

Add a new `--env-append` command-line argument to vsclaude that provides append-style environment variable merging, complementing the existing `--env` override behavior.

## Problem Statement

Currently, vsclaude's `--env` argument provides override behavior where CLI environment variables completely replace global configuration variables. There's a need for append behavior where CLI variables can be appended to existing global values instead of replacing them.

## Design Decisions

### Approach Selection
- **Selected**: Separate Processing Pipeline (Approach 1)
- **Rationale**: Maintains backward compatibility, clear separation of concerns, consistent with existing architecture

### Append Behavior
- **Method**: Simple concatenation without separators
- **Example**: `GLOBAL_VAR=value1` + `--env-append GLOBAL_VAR=value2` = `GLOBAL_VAR=value1value2`

### Flag Name
- **Selected**: `--env-append`
- **Rationale**: Clear and descriptive, follows existing `--env` pattern

## Technical Specification

### CLI Changes
**File**: `vsclaude/vsclaude/cli.py`

```python
# Add to start_parser arguments
start_parser.add_argument("--env-append", action="append", help="Environment variable to append to global config (key=value)")
```

### Processing Logic
**File**: `vsclaude/vsclaude/cli.py` (`start_command` function)

```python
# Current logic (lines 26-36)
environment_vars = {}
if hasattr(args, 'env') and args.env:
    for env_var in args.env:
        if '=' in env_var:
            key, value = env_var.split('=', 1)
            environment_vars[key] = value

# NEW: Process --env-append variables
append_environment_vars = {}
if hasattr(args, 'env_append') and args.env_append:
    for env_var in args.env_append:
        if '=' in env_var:
            key, value = env_var.split('=', 1)
            append_environment_vars[key] = value

# Merge global environment with append variables first
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

### Priority Order (Updated)
1. **Global Environment**: Variables from global config
2. **Append Environment**: Variables from `--env-append` (appended to global if exists)
3. **Override Environment**: Variables from `--env` (override everything)
4. **Auto-population**: MM_CHANNEL auto-population (lowest priority)

## Usage Examples

### Example 1: Appending to Existing Global Variable
```bash
# Global config: {"environment": {"PATH": "/usr/bin"}}
vsclaude start my-project --env-append PATH=/custom/bin

# Result: PATH=/usr/bin/custom/bin
```

### Example 2: Setting New Variable (Fallback)
```bash
# Global config: {"environment": {}}
vsclaude start my-project --env-append CUSTOM_PATH=/my/path

# Result: CUSTOM_PATH=/my/path (behaves like --env)
```

### Example 3: Mixed Usage
```bash
# Global config: {"environment": {"PATH": "/usr/bin", "THEME": "dark"}}
vsclaude start my-project \
  --env-append PATH=/custom/bin \
  --env THEME=light \
  --env-append EXTRA_VAR=extra

# Result:
# PATH=/usr/bin/custom/bin (appended)
# THEME=light (overridden)
# EXTRA_VAR=extra (new variable)
```

## Testing Strategy

**New Test File**: `tests/test_env_append.py`

### Test Cases
1. **Basic Append**: Append to existing global variable
2. **Fallback Behavior**: Set new variable when global doesn't exist
3. **Mixed Usage**: Combined `--env` and `--env-append` usage
4. **Multiple Appends**: Multiple `--env-append` arguments
5. **Edge Cases**: Empty values, special characters
6. **Priority Validation**: Verify correct priority order

### Test Examples
```python
def test_env_append_basic():
    """Test basic append functionality"""
    # Setup global config with PATH
    # Call start_command with --env-append PATH=/custom/bin
    # Verify PATH=/usr/bin/custom/bin

def test_env_append_fallback():
    """Test fallback to set behavior when global doesn't exist"""
    # Setup empty global config
    # Call start_command with --env-append NEW_VAR=value
    # Verify NEW_VAR=value
```

## Implementation Plan

### Phase 1: Core Implementation
1. Add `--env-append` argument to CLI parser
2. Implement append processing logic in `start_command`
3. Update priority order documentation

### Phase 2: Testing
1. Create comprehensive test suite
2. Test edge cases and error conditions
3. Verify backward compatibility

### Phase 3: Documentation
1. Update README.md with new feature
2. Add usage examples
3. Update environment variable priority documentation

## Error Handling

- **Invalid Format**: Same validation as `--env` (must contain `=`)
- **Empty Values**: Handle gracefully (append empty string)
- **Non-existent Global Variables**: Fallback to set behavior

## Backward Compatibility

- **No Breaking Changes**: Existing `--env` behavior unchanged
- **No Dependencies**: No changes to config files or other modules
- **Optional Feature**: `--env-append` is additive, not required

## Success Criteria

- [ ] `--env-append` argument accepted by CLI
- [ ] Append behavior works correctly (concatenation)
- [ ] Fallback to set behavior when global variable doesn't exist
- [ ] Correct priority order maintained
- [ ] Backward compatibility preserved
- [ ] Comprehensive test coverage
- [ ] Documentation updated

## Future Considerations

- **Variable-specific separators**: Could extend to support different concatenation methods per variable type
- **Advanced merging**: More sophisticated merging strategies (PATH-style with separators)
- **Validation**: Additional validation for specific variable types

---

*Design approved for implementation*