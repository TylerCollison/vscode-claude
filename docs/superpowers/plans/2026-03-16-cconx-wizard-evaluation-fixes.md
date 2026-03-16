# cconx Wizard Evaluation Fixes Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all issues identified in the cconx wizard evaluation notes to improve user experience and completeness.

**Architecture:** Update existing field handlers to fix description issues and add missing environment variable handling with conditional logic for Claude Threads configuration.

**Tech Stack:** Python 3.12, pytest for testing, cconx wizard framework

---

## File Structure

**Modified Files:**
- `/workspace/cconx/cconx/wizard/field_handlers.py` - Core field handler implementations
- `/workspace/cconx/tests/test_setup_wizard.py` - Test coverage for all changes

**No New Files Needed:** All changes can be made to existing files

## Chunk 1: Fix Port Range Description Duplication

### Task 1: Fix PortRangeFieldHandler description duplication

**Files:**
- Modify: `/workspace/cconx/cconx/wizard/field_handlers.py:103-104`
- Test: `/workspace/cconx/tests/test_setup_wizard.py:106-124`

- [ ] **Step 1: Write failing test for description behavior**

```python
def test_port_range_field_handler_description_not_duplicated():
    """Test that PortRangeFieldHandler doesn't duplicate description in prompt."""
    from cconx.wizard.field_handlers import PortRangeFieldHandler
    from unittest.mock import patch

    handler = PortRangeFieldHandler()
    current_value = {"min": 8000, "max": 9000}

    with patch('builtins.input', side_effect=["8001", "9001"]):
        with patch('builtins.print') as mock_print:
            handler.prompt(current_value)

    # Verify description is printed exactly once
    description_calls = [call for call in mock_print.call_args_list
                        if "Defines the port range" in str(call)]
    assert len(description_calls) == 1, f"Description printed {len(description_calls)} times, expected 1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_port_range_field_handler_description_not_duplicated -v`
Expected: FAIL with description being printed multiple times

- [ ] **Step 3: Fix PortRangeFieldHandler.prompt method**

Modify `/workspace/cconx/cconx/wizard/field_handlers.py:103-104`:

```python
def prompt(self, current_value: Any) -> Any:
    # Remove the duplicate description print - SetupWizard already prints it
    # print(f"Description: {self.get_explanation()}")  # REMOVE THIS LINE
    default_min = current_value.get("min", 8000) if current_value else 8000
    default_max = current_value.get("max", 9000) if current_value else 9000

    print("Configure port range for instance allocation:")
    min_port = input(f"Minimum port (default: {default_min}): ") or default_min
    max_port = input(f"Maximum port (default: {default_max}): ") or default_max

    return {"min": min_port, "max": max_port}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_port_range_field_handler_description_not_duplicated -v`
Expected: PASS

- [ ] **Step 5: Update existing port range tests**

Update `/workspace/cconx/tests/test_setup_wizard.py:106-124` to ensure tests still pass:

```python
def test_port_range_field_handler():
    """Test PortRangeFieldHandler functionality."""
    from cconx.wizard.field_handlers import PortRangeFieldHandler

    handler = PortRangeFieldHandler()

    assert handler.field_name == "port_range"
    assert "port range" in handler.get_explanation().lower()

    # Test validation
    assert handler.validate({"min": "8000", "max": "9000"}) == True
    assert handler.validate({"min": "9000", "max": "8000"}) == False  # min > max
    assert handler.validate({"min": "0", "max": "9000"}) == False     # min too low
    assert handler.validate({"min": "8000", "max": "70000"}) == False # max too high

    # Test formatting
    formatted = handler.format({"min": "8000", "max": "9000"})
    assert formatted == {"min": 8000, "max": 9000}
```

- [ ] **Step 6: Run all port range tests**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py -k "port_range" -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add /workspace/cconx/cconx/wizard/field_handlers.py /workspace/cconx/tests/test_setup_wizard.py
git commit -m "fix: remove duplicate description in port range field handler"
```

## Chunk 2: Update Environment Variable Descriptions

### Task 2: Update CCR_PROFILE description with available profiles

**Files:**
- Modify: `/workspace/cconx/cconx/wizard/field_handlers.py:151`
- Test: `/workspace/cconx/tests/test_setup_wizard.py:126-148`

- [ ] **Step 1: Write failing test for CCR_PROFILE description**

```python
def test_environment_field_handler_ccr_profile_description():
    """Test that CCR_PROFILE description includes available profiles."""
    from cconx.wizard.field_handlers import EnvironmentFieldHandler

    handler = EnvironmentFieldHandler()

    # Check that CCR_PROFILE description includes available options
    ccr_description = handler.special_variables["CCR_PROFILE"]
    assert "default" in ccr_description, "CCR_PROFILE description should include 'default'"
    assert "nim-kimi" in ccr_description, "CCR_PROFILE description should include 'nim-kimi'"
    assert "nim-deepseek" in ccr_description, "CCR_PROFILE description should include 'nim-deepseek'"
    assert "google-gemini" in ccr_description, "CCR_PROFILE description should include 'google-gemini'"
    assert "mistral-devstral" in ccr_description, "CCR_PROFILE description should include 'mistral-devstral'"
    assert "mistral-mistral-large" in ccr_description, "CCR_PROFILE description should include 'mistral-mistral-large'"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_ccr_profile_description -v`
Expected: FAIL with current description not including profile options

- [ ] **Step 3: Update CCR_PROFILE description**

Modify `/workspace/cconx/cconx/wizard/field_handlers.py:151`:

```python
self.special_variables = {
    "NIM_API_KEY": "NVIDIA NIM API key",
    "GOOGLE_API_KEY": "Google AI Studio API key",
    "MISTRAL_API_KEY": "Mistral AI API key",
    "OPENROUTER_API_KEY": "OpenRouter API key",
    "CCR_PROFILE": "Claude Code Router profile (default, nim-kimi, nim-deepseek, google-gemini, mistral-devstral, mistral-mistral-large)",
    "PUID": "User ID for container processes",
    "PGID": "Group ID for container processes",
    "TZ": "Timezone configuration",
    "CLAUDE_CODE_PERMISSION_MODE": "Claude Code permission mode"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_ccr_profile_description -v`
Expected: PASS

### Task 3: Update TZ description with example

**Files:**
- Modify: `/workspace/cconx/cconx/wizard/field_handlers.py:154`
- Test: `/workspace/cconx/tests/test_setup_wizard.py` (add new test)

- [ ] **Step 1: Write failing test for TZ description**

```python
def test_environment_field_handler_tz_description():
    """Test that TZ description includes example."""
    from cconx.wizard.field_handlers import EnvironmentFieldHandler

    handler = EnvironmentFieldHandler()

    # Check that TZ description includes example
    tz_description = handler.special_variables["TZ"]
    assert "ex." in tz_description.lower(), "TZ description should include example"
    assert "utc" in tz_description.lower(), "TZ description should include UTC example"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_tz_description -v`
Expected: FAIL with current description not including example

- [ ] **Step 3: Update TZ description**

Modify `/workspace/cconx/cconx/wizard/field_handlers.py:154`:

```python
"TZ": "Timezone configuration (ex. Etc/UTC)",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_tz_description -v`
Expected: PASS

### Task 4: Update CLAUDE_CODE_PERMISSION_MODE description

**Files:**
- Modify: `/workspace/cconx/cconx/wizard/field_handlers.py:155`
- Test: `/workspace/cconx/tests/test_setup_wizard.py` (add new test)

- [ ] **Step 1: Write failing test for CLAUDE_CODE_PERMISSION_MODE description**

```python
def test_environment_field_handler_permission_mode_description():
    """Test that CLAUDE_CODE_PERMISSION_MODE description includes all modes."""
    from cconx.wizard.field_handlers import EnvironmentFieldHandler

    handler = EnvironmentFieldHandler()

    # Check that permission mode description includes all options
    permission_description = handler.special_variables["CLAUDE_CODE_PERMISSION_MODE"]
    assert "acceptEdits" in permission_description, "Permission description should include 'acceptEdits'"
    assert "bypassPermissions" in permission_description, "Permission description should include 'bypassPermissions'"
    assert "default" in permission_description, "Permission description should include 'default'"
    assert "plan" in permission_description, "Permission description should include 'plan'"
    assert "dontAsk" in permission_description, "Permission description should include 'dontAsk'"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_permission_mode_description -v`
Expected: FAIL with current description not including all modes

- [ ] **Step 3: Update CLAUDE_CODE_PERMISSION_MODE description**

Modify `/workspace/cconx/cconx/wizard/field_handlers.py:155`:

```python
"CLAUDE_CODE_PERMISSION_MODE": "Claude Code permission mode (acceptEdits, bypassPermissions, default, plan, dontAsk)",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_permission_mode_description -v`
Expected: PASS

- [ ] **Step 5: Run all environment field handler tests**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py -k "environment" -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add /workspace/cconx/cconx/wizard/field_handlers.py /workspace/cconx/tests/test_setup_wizard.py
git commit -m "feat: update environment variable descriptions with examples and options"
```

## Chunk 3: Add Missing Environment Variables

### Task 5: Add missing environment variables to special_variables

**Files:**
- Modify: `/workspace/cconx/cconx/wizard/field_handlers.py:146-156`
- Test: `/workspace/cconx/tests/test_setup_wizard.py` (add comprehensive test)

- [ ] **Step 1: Write failing test for missing environment variables**

```python
def test_environment_field_handler_includes_all_required_variables():
    """Test that EnvironmentFieldHandler includes all required special variables."""
    from cconx.wizard.field_handlers import EnvironmentFieldHandler

    handler = EnvironmentFieldHandler()

    required_variables = [
        "PROXY_DOMAIN", "DEFAULT_WORKSPACE", "PWA_APPNAME",
        "PASSWORD", "SUDO_PASSWORD", "CLAUDE_MARKETPLACES", "CLAUDE_PLUGINS",
        "GIT_REPO_URL", "GIT_BRANCH_NAME", "KNOWLEDGE_REPOS"
    ]

    for var_name in required_variables:
        assert var_name in handler.special_variables, f"Missing required variable: {var_name}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_includes_all_required_variables -v`
Expected: FAIL with missing variables

- [ ] **Step 3: Add missing environment variables**

Modify `/workspace/cconx/cconx/wizard/field_handlers.py:146-156`:

```python
self.special_variables = {
    "NIM_API_KEY": "NVIDIA NIM API key",
    "GOOGLE_API_KEY": "Google AI Studio API key",
    "MISTRAL_API_KEY": "Mistral AI API key",
    "OPENROUTER_API_KEY": "OpenRouter API key",
    "CCR_PROFILE": "Claude Code Router profile (default, nim-kimi, nim-deepseek, google-gemini, mistral-devstral, mistral-mistral-large)",
    "PUID": "User ID for container processes",
    "PGID": "Group ID for container processes",
    "TZ": "Timezone configuration (ex. Etc/UTC)",
    "PROXY_DOMAIN": "Reverse proxy domain for external access",
    "DEFAULT_WORKSPACE": "Default workspace directory",
    "PWA_APPNAME": "Progressive Web App name",
    "PASSWORD": "Plaintext password for VS Code web interface",
    "SUDO_PASSWORD": "Plaintext sudo password",
    "CLAUDE_CODE_PERMISSION_MODE": "Claude Code permission mode (acceptEdits, bypassPermissions, default, plan, dontAsk)",
    "CLAUDE_MARKETPLACES": "Comma-separated list of plugin marketplaces",
    "CLAUDE_PLUGINS": "Comma-separated list of plugins to install",
    "GIT_REPO_URL": "Repository URL to clone on startup",
    "GIT_BRANCH_NAME": "Branch name",
    "KNOWLEDGE_REPOS": "Git repos with markdown files to load into CLAUDE.md"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_includes_all_required_variables -v`
Expected: PASS

### Task 6: Add test for environment variable default values

**Files:**
- Test: `/workspace/cconx/tests/test_setup_wizard.py` (add new test)

- [ ] **Step 1: Write test for environment variable default values**

```python
def test_environment_field_handler_prompt_includes_new_variables():
    """Test that EnvironmentFieldHandler.prompt() includes new variables."""
    from cconx.wizard.field_handlers import EnvironmentFieldHandler
    from unittest.mock import patch

    handler = EnvironmentFieldHandler()
    current_value = {}

    # Mock user input for all variables
    input_responses = [
        "", "", "", "", "", "", "", "", "", "",  # API keys
        "default", "1000", "1000", "Etc/UTC",  # CCR profile, PUID, PGID, TZ
        "", "/workspace", "ClaudeConX", "", "",  # PROXY_DOMAIN, DEFAULT_WORKSPACE, PWA_APPNAME, PASSWORD, SUDO_PASSWORD
        "acceptEdits", "", "", "", "", ""  # Permission mode, marketplaces, plugins, git, knowledge repos
    ]

    with patch('builtins.input', side_effect=input_responses):
        with patch('builtins.print'):
            result = handler.prompt(current_value)

    # Verify new variables are included in result
    assert "DEFAULT_WORKSPACE" in result
    assert "PWA_APPNAME" in result
    assert "CLAUDE_MARKETPLACES" in result
    assert "CLAUDE_PLUGINS" in result
    assert "GIT_REPO_URL" in result
    assert "GIT_BRANCH_NAME" in result
    assert "KNOWLEDGE_REPOS" in result
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_prompt_includes_new_variables -v`
Expected: PASS

- [ ] **Step 3: Run all environment field handler tests**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py -k "environment" -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add /workspace/cconx/cconx/wizard/field_handlers.py /workspace/cconx/tests/test_setup_wizard.py
git commit -m "feat: add missing environment variables to wizard configuration"
```

## Chunk 4: Add Conditional Claude Threads Handling

### Task 7: Add Claude Threads variables with conditional logic

**Files:**
- Modify: `/workspace/cconx/cconx/wizard/field_handlers.py:146-210`
- Test: `/workspace/cconx/tests/test_setup_wizard.py` (add comprehensive tests)

- [ ] **Step 1: Write failing test for Claude Threads conditional logic**

```python
def test_environment_field_handler_threads_variables_conditional():
    """Test that Claude Threads variables are only prompted when ENABLE_THREADS=true."""
    from cconx.wizard.field_handlers import EnvironmentFieldHandler
    from unittest.mock import patch

    handler = EnvironmentFieldHandler()
    current_value = {}

    # Test 1: ENABLE_THREADS=false - should not prompt for Threads variables
    input_responses_no_threads = [
        "", "", "", "", "", "", "", "", "", "",  # API keys
        "default", "1000", "1000", "Etc/UTC",  # CCR profile, PUID, PGID, TZ
        "", "/workspace", "ClaudeConX", "", "",  # Other variables
        "acceptEdits", "", "", "", "", "",  # More variables
        "false"  # ENABLE_THREADS = false
    ]

    with patch('builtins.input', side_effect=input_responses_no_threads):
        with patch('builtins.print'):
            result_no_threads = handler.prompt(current_value)

    # Should not include Threads variables when ENABLE_THREADS=false
    threads_vars = ["MM_ADDRESS", "MM_TOKEN", "MM_TEAM", "MM_BOT_NAME",
                   "THREADS_CHROME", "THREADS_WORKTREE_MODE", "THREADS_SKIP_PERMISSIONS"]
    for var in threads_vars:
        assert var not in result_no_threads, f"Threads variable {var} should not be present when ENABLE_THREADS=false"

    # Test 2: ENABLE_THREADS=true - should prompt for Threads variables
    input_responses_with_threads = [
        "", "", "", "", "", "", "", "", "", "",  # API keys
        "default", "1000", "1000", "Etc/UTC",  # CCR profile, PUID, PGID, TZ
        "", "/workspace", "ClaudeConX", "", "",  # Other variables
        "acceptEdits", "", "", "", "", "",  # More variables
        "true",  # ENABLE_THREADS = true
        "http://localhost:80", "Mattermost-Bot-Token", "team-name", "bot-name",  # Threads variables
        "false", "off", "false"  # More Threads variables
    ]

    with patch('builtins.input', side_effect=input_responses_with_threads):
        with patch('builtins.print'):
            result_with_threads = handler.prompt(current_value)

    # Should include Threads variables when ENABLE_THREADS=true
    for var in threads_vars:
        assert var in result_with_threads, f"Threads variable {var} should be present when ENABLE_THREADS=true"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_threads_variables_conditional -v`
Expected: FAIL with no conditional logic implemented

- [ ] **Step 3: Add Claude Threads variables to special_variables**

Modify `/workspace/cconx/cconx/wizard/field_handlers.py:146-156` to add Threads variables:

```python
self.special_variables = {
    # ... existing variables ...
    "ENABLE_THREADS": "Enable Claude Threads server",
    "MM_ADDRESS": "Mattermost server URL",
    "MM_TOKEN": "Mattermost bot authentication token",
    "MM_TEAM": "Mattermost team name",
    "MM_BOT_NAME": "Bot display name",
    "THREADS_CHROME": "Use Chrome browser",
    "THREADS_WORKTREE_MODE": "Git worktree mode",
    "THREADS_SKIP_PERMISSIONS": "Skip permission prompts",
    # ... other variables ...
}
```

- [ ] **Step 4: Implement conditional logic in EnvironmentFieldHandler.prompt**

Modify `/workspace/cconx/cconx/wizard/field_handlers.py:158-194` to add conditional logic:

```python
def prompt(self, current_value: Any) -> Any:
    env_vars = current_value.copy() if current_value else {}

    print("\n=== CONFIGURE ENVIRONMENT VARIABLES ===")
    print("The following special variables are commonly configured:")

    # Separate Threads variables from others
    threads_variables = ["ENABLE_THREADS", "MM_ADDRESS", "MM_TOKEN", "MM_TEAM",
                        "MM_BOT_NAME", "THREADS_CHROME", "THREADS_WORKTREE_MODE",
                        "THREADS_SKIP_PERMISSIONS"]

    other_variables = [var for var in self.special_variables.keys()
                      if var not in threads_variables]

    # Process non-Threads variables first
    for var_name in other_variables:
        description = self.special_variables[var_name]
        current_val = env_vars.get(var_name, "")
        print(f"\n{var_name}: {description}")
        if current_val:
            print(f"Current value: {current_val}")

        new_value = input(f"Enter value for {var_name} (leave empty to keep current): ")
        if new_value.strip():
            env_vars[var_name] = new_value.strip()
        elif var_name not in env_vars and new_value == "":
            # Skip if no current value and user enters empty
            continue

    # Process ENABLE_THREADS first, then conditionally show other Threads variables
    print("\n=== CLAUDE THREADS CONFIGURATION ===")

    # Prompt for ENABLE_THREADS
    threads_enabled_var = "ENABLE_THREADS"
    threads_description = self.special_variables[threads_enabled_var]
    current_threads_val = env_vars.get(threads_enabled_var, "false")
    print(f"\n{threads_enabled_var}: {threads_description}")
    if current_threads_val:
        print(f"Current value: {current_threads_val}")

    threads_enabled_input = input(f"Enter value for {threads_enabled_var} (default: false): ").strip()
    if threads_enabled_input:
        env_vars[threads_enabled_var] = threads_enabled_input
    elif threads_enabled_var not in env_vars:
        env_vars[threads_enabled_var] = "false"

    # Only prompt for other Threads variables if ENABLE_THREADS is true
    threads_enabled = env_vars.get(threads_enabled_var, "false").lower() in ["true", "yes", "1"]

    if threads_enabled:
        print("\n=== THREADS-SPECIFIC CONFIGURATION ===")
        for var_name in threads_variables:
            if var_name == "ENABLE_THREADS":  # Already processed
                continue

            description = self.special_variables[var_name]
            current_val = env_vars.get(var_name, "")
            print(f"\n{var_name}: {description}")
            if current_val:
                print(f"Current value: {current_val}")

            new_value = input(f"Enter value for {var_name} (leave empty to keep current): ")
            if new_value.strip():
                env_vars[var_name] = new_value.strip()
            elif var_name not in env_vars and new_value == "":
                # Set default values for Threads variables
                if var_name == "MM_ADDRESS":
                    env_vars[var_name] = "http://localhost:80"
                elif var_name == "MM_TOKEN":
                    env_vars[var_name] = "Mattermost-Bot-Token"
                elif var_name == "MM_TEAM":
                    env_vars[var_name] = "team-name"
                elif var_name == "MM_BOT_NAME":
                    env_vars[var_name] = "bot-name"
                elif var_name == "THREADS_CHROME":
                    env_vars[var_name] = "false"
                elif var_name == "THREADS_WORKTREE_MODE":
                    env_vars[var_name] = "off"
                elif var_name == "THREADS_SKIP_PERMISSIONS":
                    env_vars[var_name] = "false"

    # Allow adding arbitrary variables (existing code)
    print("\n=== ADDITIONAL VARIABLES ===")
    print("You can add any additional environment variables.")
    print("Enter variables as KEY=VALUE pairs, one per line.")
    print("Enter an empty line when finished.\n")

    while True:
        user_input = input("Enter KEY=VALUE (or empty to finish): ").strip()
        if not user_input:
            break

        if "=" in user_input:
            key, value = user_input.split("=", 1)
            env_vars[key.strip()] = value.strip()
        else:
            print("Invalid format. Use KEY=VALUE format.")

    return env_vars
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_threads_variables_conditional -v`
Expected: PASS

### Task 8: Add comprehensive tests for Claude Threads functionality

**Files:**
- Test: `/workspace/cconx/tests/test_setup_wizard.py` (add multiple tests)

- [ ] **Step 1: Write test for Threads variable defaults**

```python
def test_environment_field_handler_threads_default_values():
    """Test that Claude Threads variables have correct default values."""
    from cconx.wizard.field_handlers import EnvironmentFieldHandler
    from unittest.mock import patch

    handler = EnvironmentFieldHandler()
    current_value = {"ENABLE_THREADS": "true"}

    # Mock user entering empty for all Threads variables to test defaults
    input_responses = [
        "", "", "", "", "", "", "", "", "", "",  # API keys
        "default", "1000", "1000", "Etc/UTC",  # CCR profile, PUID, PGID, TZ
        "", "/workspace", "ClaudeConX", "", "",  # Other variables
        "acceptEdits", "", "", "", "", "",  # More variables
        "true",  # ENABLE_THREADS = true
        "", "", "", "", "", "", ""  # Empty for all Threads variables (should use defaults)
    ]

    with patch('builtins.input', side_effect=input_responses):
        with patch('builtins.print'):
            result = handler.prompt(current_value)

    # Verify default values are set correctly
    assert result["MM_ADDRESS"] == "http://localhost:80"
    assert result["MM_TOKEN"] == "Mattermost-Bot-Token"
    assert result["MM_TEAM"] == "team-name"
    assert result["MM_BOT_NAME"] == "bot-name"
    assert result["THREADS_CHROME"] == "false"
    assert result["THREADS_WORKTREE_MODE"] == "off"
    assert result["THREADS_SKIP_PERMISSIONS"] == "false"
```

- [ ] **Step 2: Run Threads default values test**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_threads_default_values -v`
Expected: PASS

- [ ] **Step 3: Write test for Threads variable validation**

```python
def test_environment_field_handler_threads_validation():
    """Test that Claude Threads variables are properly validated."""
    from cconx.wizard.field_handlers import EnvironmentFieldHandler

    handler = EnvironmentFieldHandler()

    # Test validation accepts valid Threads configuration
    valid_threads_config = {
        "ENABLE_THREADS": "true",
        "MM_ADDRESS": "http://localhost:80",
        "MM_TOKEN": "valid-token",
        "MM_TEAM": "team-name",
        "MM_BOT_NAME": "bot-name",
        "THREADS_CHROME": "false",
        "THREADS_WORKTREE_MODE": "off",
        "THREADS_SKIP_PERMISSIONS": "false"
    }

    assert handler.validate(valid_threads_config) == True

    # Test validation still works with non-dict input
    assert handler.validate("invalid") == False
```

- [ ] **Step 4: Run Threads validation test**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_environment_field_handler_threads_validation -v`
Expected: PASS

- [ ] **Step 5: Run all Threads-related tests**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py -k "threads" -v`
Expected: All tests PASS

- [ ] **Step 6: Run full integration test**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_end_to_end_wizard_flow -v`
Expected: PASS (may need to update mock input to include new variables)

- [ ] **Step 7: Update end-to-end test mock input**

Update `/workspace/cconx/tests/test_setup_wizard.py:267-281` to include new variables:

```python
def mock_input(prompt):
    if "Minimum port" in prompt:
        return "8000"
    elif "Maximum port" in prompt:
        return "9000"
    elif "default:" in prompt.lower() and "docker image" in prompt.lower():
        return "test-image:latest"
    elif "Enable?" in prompt:
        return "yes"
    elif "NIM_API_KEY" in prompt:
        return "test-nim-key"
    elif "ENABLE_THREADS" in prompt:
        return "false"  # Add Threads variables
    elif "empty to finish" in prompt:
        return ""
    else:
        return "test-value"  # Default for any other field
```

- [ ] **Step 8: Run updated end-to-end test**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_end_to_end_wizard_flow -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add /workspace/cconx/cconx/wizard/field_handlers.py /workspace/cconx/tests/test_setup_wizard.py
git commit -m "feat: add conditional Claude Threads configuration to wizard"
```

## Chunk 5: Final Integration and Testing

### Task 9: Run comprehensive test suite

- [ ] **Step 1: Run all setup wizard tests**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run CLI integration test**

Run: `pytest /workspace/cconx/tests/test_setup_wizard.py::test_cli_setup_command -v`
Expected: PASS

- [ ] **Step 3: Verify git status is clean**

Run: `git status`
Expected: No uncommitted changes

- [ ] **Step 4: Final commit if any remaining changes**

```bash
git add .
git commit -m "chore: finalize cconx wizard evaluation fixes"
```

## Summary

This implementation plan addresses all the evaluation feedback:

1. **Port Range Description Fix**: Remove duplicate description printing
2. **Environment Variable Description Updates**: Add examples and available options to descriptions
3. **Missing Environment Variables**: Add handlers for all variables mentioned in evaluation notes
4. **Conditional Claude Threads**: Add conditional logic for Threads configuration

Each task is broken down into bite-sized steps with specific tests and expected outcomes to ensure comprehensive coverage and validation.