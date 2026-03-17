# cconx Wizard Evaluation Feedback Implementation Specification

## Overview

This document specifies the implementation of feedback items identified in `cconx_wizard_evaluation_notes.txt` for the cconx setup wizard. The implementation addresses UI/UX improvements and missing functionality through targeted enhancements to the existing wizard architecture.

## Requirements Addressed

### UI/UX Fixes
- **Port Range Description**: Remove duplicate description display in PortRangeFieldHandler
- **CCR_PROFILE Message**: Update to include available profile options: "Claude Code Router profile (default, nim-kimi, nim-deepseek, google-gemini, mistral-devstral, mistral-mistral-large)"
- **TZ Message**: Update with example: "Timezone configuration (ex. Etc/UTC)"
- **CLAUDE_CODE_PERMISSION_MODE**: Display all possible permission modes: "Claude Code permission mode (acceptEdits, bypassPermissions, default, plan, dontAsk)"

### Missing Environment Variables
- **Basic Variables**: PROXY_DOMAIN, DEFAULT_WORKSPACE, PWA_APPNAME
- **Authentication Variables**: PASSWORD, SUDO_PASSWORD
- **Claude Code Variables**: CLAUDE_MARKETPLACES, CLAUDE_PLUGINS
- **Claude Threads Variables**: ENABLE_THREADS, MM_ADDRESS, MM_TOKEN, MM_TEAM, MM_BOT_NAME, THREADS_CHROME, THREADS_WORKTREE_MODE, THREADS_SKIP_PERMISSIONS
- **Git Variables**: GIT_REPO_URL, GIT_BRANCH_NAME
- **Knowledge Variables**: KNOWLEDGE_REPOS

## Architecture Changes

### PortRangeFieldHandler Description Fix

**Current Issue**: The `prompt` method in PortRangeFieldHandler calls `print(f"Description: {self.get_explanation()}")` which causes the description to appear twice since the SetupWizard's `_process_field` method already displays it.

**Root Cause**: The `SetupWizard._process_field` method prints the description:
```python
print(f"Description: {handler.get_explanation()}")
```

But PortRangeFieldHandler also prints its own description in its `prompt` method.

**Solution**: Remove the redundant print statement from PortRangeFieldHandler:

```python
# PortRangeFieldHandler.prompt() - REMOVE:
print(f"Description: {self.get_explanation()}")
```

This will ensure the port range description appears only once per field, displayed by the SetupWizard.

### EnvironmentFieldHandler Enhancements

**Enhanced special_variables Dictionary with Defaults**:

```python
self.special_variables = {
    # API Keys & Authentication (existing)
    "NIM_API_KEY": "NVIDIA NIM API key",
    "GOOGLE_API_KEY": "Google AI Studio API key",
    "MISTRAL_API_KEY": "Mistral AI API key",
    "OPENROUTER_API_KEY": "OpenRouter API key",

    # Container Configuration (enhanced with defaults)
    "PUID": "User ID for container processes",
    "PGID": "Group ID for container processes",
    "TZ": "Timezone configuration (ex. Etc/UTC)",
    "PROXY_DOMAIN": "Reverse proxy domain for external access",
    "DEFAULT_WORKSPACE": "Default workspace directory",  # Default: /workspace
    "PWA_APPNAME": "Progressive Web App name",  # Default: ClaudeConX

    # Authentication & Access Control (new)
    "PASSWORD": "Plaintext password for VS Code web interface",
    "SUDO_PASSWORD": "Plaintext sudo password",

    # Claude Code Configuration (enhanced)
    "CCR_PROFILE": "Claude Code Router profile (default, nim-kimi, nim-deepseek, google-gemini, mistral-devstral, mistral-mistral-large)",
    "CLAUDE_CODE_PERMISSION_MODE": "Claude Code permission mode (acceptEdits, bypassPermissions, default, plan, dontAsk)",
    "CLAUDE_MARKETPLACES": "Comma-separated list of plugin marketplaces",
    "CLAUDE_PLUGINS": "Comma-separated list of plugins to install",

    # Claude Threads Configuration (conditional - new with defaults)
    "ENABLE_THREADS": "Enable Claude Threads server",  # Default: false
    "MM_ADDRESS": "Mattermost server URL",  # Default: http://localhost:80
    "MM_TOKEN": "Mattermost bot authentication token",  # Default: Mattermost-Bot-Token
    "MM_TEAM": "Mattermost team name",  # Default: team-name
    "MM_BOT_NAME": "Bot display name",  # Default: bot-name
    "THREADS_CHROME": "Chrome executable path",  # Default: false
    "THREADS_WORKTREE_MODE": "Git worktree mode",  # Default: off
    "THREADS_SKIP_PERMISSIONS": "Skip permission prompts",  # Default: false

    # Git Repository Setup (new)
    "GIT_REPO_URL": "Repository URL to clone on startup",
    "GIT_BRANCH_NAME": "Branch name",

    # Knowledge Repository Integration (new)
    "KNOWLEDGE_REPOS": "Git repos with markdown files to load into CLAUDE.md"
}
```

**Default Value Implementation**: The EnvironmentFieldHandler should be enhanced to provide sensible defaults when users leave fields empty, as specified in the evaluation notes.

### Conditional Variable Handling

**Implementation**: Add logic to skip Claude Threads variables unless `ENABLE_THREADS` is set to true

```python
def prompt(self, current_value: Any) -> Any:
    env_vars = current_value.copy() if current_value else {}

    print("\n=== CONFIGURE ENVIRONMENT VARIABLES ===")
    print("The following special variables are commonly configured:")

    # Track if threads are enabled
    threads_enabled = env_vars.get("ENABLE_THREADS", "").lower() in ["true", "yes", "1"]

    for var_name, description in self.special_variables.items():
        # Skip threads variables if threads not enabled
        if var_name.startswith(("MM_", "THREADS_")) and not threads_enabled:
            continue

        current_val = env_vars.get(var_name, "")
        print(f"\n{var_name}: {description}")

        if current_val:
            print(f"Current value: {current_val}")

        new_value = input(f"Enter value for {var_name} (leave empty to keep current): ")
        if new_value.strip():
            env_vars[var_name] = new_value.strip()
            # Re-evaluate threads enabled status if ENABLE_THREADS changed
            if var_name == "ENABLE_THREADS":
                threads_enabled = new_value.lower() in ["true", "yes", "1"]
        elif var_name not in env_vars and new_value == "":
            continue

    # Rest of the method for arbitrary variables remains unchanged
```

## Implementation Phases

### Phase 1: UI/UX Fixes and Simple Environment Variables
1. Fix PortRangeFieldHandler duplicate description
2. Update CCR_PROFILE message with available profiles
3. Update TZ message with example
4. Update CLAUDE_CODE_PERMISSION_MODE with available modes
5. Add PROXY_DOMAIN, DEFAULT_WORKSPACE, PWA_APPNAME
6. Add PASSWORD, SUDO_PASSWORD
7. Add CLAUDE_MARKETPLACES, CLAUDE_PLUGINS

### Phase 2: Complex Environment Variables
1. Add ENABLE_THREADS and conditional thread variables
2. Add GIT_REPO_URL, GIT_BRANCH_NAME
3. Add KNOWLEDGE_REPOS

## File Changes

### Modified Files
- `/workspace/cconx/cconx/wizard/field_handlers.py`
  - PortRangeFieldHandler.prompt() method
  - EnvironmentFieldHandler.special_variables dictionary
  - EnvironmentFieldHandler.prompt() method (conditional logic)

### New Files
- None required - all changes are modifications to existing files

## Testing Strategy

### Unit Tests
- Update PortRangeFieldHandler tests to verify no duplicate descriptions
- Add tests for EnvironmentFieldHandler with new variables
- Test conditional variable logic (threads variables only appear when enabled)
- Add specific test for dynamic thread enable/disable during prompt

```python
def test_port_range_field_handler_no_duplicate_description():
    """Test that port range description appears only once"""
    handler = PortRangeFieldHandler()
    # Mock SetupWizard._process_field description display
    # Verify PortRangeFieldHandler.prompt doesn't duplicate description

def test_environment_field_handler_conditional_threads():
    """Test that threads variables only appear when ENABLE_THREADS is true"""
    handler = EnvironmentFieldHandler()

    # Test with ENABLE_THREADS=false
    current_config = {"ENABLE_THREADS": "false"}
    # Mock input to verify threads variables are skipped

    # Test with ENABLE_THREADS=true
    current_config = {"ENABLE_THREADS": "true"}
    # Mock input to verify threads variables appear

    # Test dynamic enable/disable during prompt
    # Simulate user enabling threads mid-prompt
```

### Integration Tests
- Test full wizard flow with new environment variables
- Verify backward compatibility with existing configurations
- Test conditional variable handling in different scenarios
- Mock user input sequences for complex conditional flows

### Manual Testing
- Run wizard and verify UI improvements
- Test conditional threads variable display
- Verify all new variables appear correctly
- Test dynamic thread enable/disable functionality

## Backward Compatibility

- All changes maintain backward compatibility
- Existing configurations continue to work unchanged
- New variables have sensible defaults (empty strings or "unset")
- Users can run setup wizard again to configure new variables

## Success Criteria

### Functional
- Port range description appears only once
- CCR_PROFILE message includes available profiles
- TZ message includes example
- CLAUDE_CODE_PERMISSION_MODE displays all modes
- All missing environment variables are available in wizard
- Conditional variable handling works correctly

### User Experience
- Wizard remains intuitive and easy to use
- Clear explanations and helpful defaults maintained
- Graceful error handling preserved
- Fast and responsive interaction maintained

### Technical
- Code remains maintainable and testable
- Integration with existing codebase is clean
- Performance meets user expectations
- Security considerations addressed

## Risk Assessment

### Medium Risk
- **Conditional Logic Complexity**: Dynamic variable display based on `ENABLE_THREADS` state introduces complexity
- **Backward Compatibility**: Need to ensure existing configurations continue working
- **Default Value Implementation**: Must correctly handle default values as specified in evaluation notes

### Low Risk
- UI/UX fixes are isolated changes
- Environment variable additions are additive

### Mitigation Strategies
- **Thorough testing** of conditional variable logic with various scenarios
- **Comprehensive integration testing** with real-world configurations
- **Incremental implementation** with validation at each phase
- **Default value validation** to ensure correct defaults are applied

## Next Steps

1. **Implementation Planning** - Create detailed implementation plan
2. **Development** - Implement changes in phases
3. **Testing** - Comprehensive testing of all features
4. **Documentation** - Update user documentation if needed
5. **Release** - Deploy and gather user feedback