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

### PortRangeFieldHandler Fix

**Current Issue**: The `prompt` method in PortRangeFieldHandler calls `print(f"Description: {self.get_explanation()}")` which causes the description to appear twice since the SetupWizard's `_process_field` method already displays it.

**Solution**: Remove the redundant print statement:

```python
class PortRangeFieldHandler(FieldHandler):
    def prompt(self, current_value: Any) -> Any:
        # REMOVE: print(f"Description: {self.get_explanation()}")  # This causes duplication
        default_min = current_value.get("min", 8000) if current_value else 8000
        default_max = current_value.get("max", 9000) if current_value else 9000

        print("Configure port range for instance allocation:")
        min_port = input(f"Minimum port (default: {default_min}): ") or default_min
        max_port = input(f"Maximum port (default: {default_max}): ") or default_max

        return {"min": min_port, "max": max_port}
```

### EnvironmentFieldHandler Enhancements

**Enhanced special_variables Dictionary**:

```python
self.special_variables = {
    # API Keys & Authentication (existing)
    "NIM_API_KEY": "NVIDIA NIM API key",
    "GOOGLE_API_KEY": "Google AI Studio API key",
    "MISTRAL_API_KEY": "Mistral AI API key",
    "OPENROUTER_API_KEY": "OpenRouter API key",

    # Container Configuration (enhanced)
    "PUID": "User ID for container processes",
    "PGID": "Group ID for container processes",
    "TZ": "Timezone configuration (ex. Etc/UTC)",
    "PROXY_DOMAIN": "Reverse proxy domain for external access",
    "DEFAULT_WORKSPACE": "Default workspace directory",
    "PWA_APPNAME": "Progressive Web App name",

    # Authentication & Access Control (new)
    "PASSWORD": "Plaintext password for VS Code web interface",
    "SUDO_PASSWORD": "Plaintext sudo password",

    # Claude Code Configuration (enhanced)
    "CCR_PROFILE": "Claude Code Router profile (default, nim-kimi, nim-deepseek, google-gemini, mistral-devstral, mistral-mistral-large)",
    "CLAUDE_CODE_PERMISSION_MODE": "Claude Code permission mode (acceptEdits, bypassPermissions, default, plan, dontAsk)",
    "CLAUDE_MARKETPLACES": "Comma-separated list of plugin marketplaces",
    "CLAUDE_PLUGINS": "Comma-separated list of plugins to install",

    # Claude Threads Configuration (conditional - new)
    "ENABLE_THREADS": "Enable Claude Threads server",
    "MM_ADDRESS": "Mattermost server URL",
    "MM_TOKEN": "Mattermost bot authentication token",
    "MM_TEAM": "Mattermost team name",
    "MM_BOT_NAME": "Bot display name",
    "THREADS_CHROME": "Chrome executable path",
    "THREADS_WORKTREE_MODE": "Git worktree mode",
    "THREADS_SKIP_PERMISSIONS": "Skip permission prompts",

    # Git Repository Setup (new)
    "GIT_REPO_URL": "Repository URL to clone on startup",
    "GIT_BRANCH_NAME": "Branch name",

    # Knowledge Repository Integration (new)
    "KNOWLEDGE_REPOS": "Git repos with markdown files to load into CLAUDE.md"
}
```

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

### Phase 1: UI/UX Fixes (High Priority)
1. Fix PortRangeFieldHandler duplicate description
2. Update CCR_PROFILE message with available profiles
3. Update TZ message with example
4. Update CLAUDE_CODE_PERMISSION_MODE with available modes

### Phase 2: Simple Environment Variables (Medium Priority)
1. Add PROXY_DOMAIN, DEFAULT_WORKSPACE, PWA_APPNAME
2. Add PASSWORD, SUDO_PASSWORD
3. Add CLAUDE_MARKETPLACES, CLAUDE_PLUGINS

### Phase 3: Complex Environment Variables (Low Priority)
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
- Update existing PortRangeFieldHandler tests to verify no duplicate descriptions
- Add tests for EnvironmentFieldHandler with new variables
- Test conditional variable logic (threads variables only appear when enabled)

### Integration Tests
- Test full wizard flow with new environment variables
- Verify backward compatibility with existing configurations
- Test conditional variable handling in different scenarios

### Manual Testing
- Run wizard and verify UI improvements
- Test conditional threads variable display
- Verify all new variables appear correctly

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

### Low Risk
- UI/UX fixes are isolated changes
- Environment variable additions are additive
- Conditional logic is contained within existing method

### Mitigation Strategies
- Thorough testing of conditional variable logic
- Maintain existing test coverage
- Incremental implementation with validation at each phase

## Next Steps

1. **Implementation Planning** - Create detailed implementation plan
2. **Development** - Implement changes in phases
3. **Testing** - Comprehensive testing of all features
4. **Documentation** - Update user documentation if needed
5. **Release** - Deploy and gather user feedback