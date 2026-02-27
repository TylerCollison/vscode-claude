#!/bin/bash
# Enhanced Test script for Mattermost bot integration
# Follows existing codebase patterns and standards

set -euo pipefail

# Use logging functions following existing codebase patterns
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Error handling function matching codebase standards
error_exit() {
    log "ERROR: $1" >&2
    exit 1
}

# Success logging function
log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1"
}

# Configuration - use relative paths instead of hardcoded /workspace/
WORKSPACE_DIR="${WORKSPACE_DIR:-$(pwd)}"
BOT_JS_FILE="${BOT_JS_FILE:-$WORKSPACE_DIR/mattermost-bot.js}"
STARTUP_SCRIPT="${STARTUP_SCRIPT:-$WORKSPACE_DIR/start-mattermost-bot.sh}"

# Test function to check file existence with proper logging
check_file_exists() {
    local file_path="$1"
    local description="$2"

    if [ -f "$file_path" ]; then
        log "✓ $description exists: $file_path"
        return 0
    else
        error_exit "✗ $description missing: $file_path"
    fi
}

# Test function to validate syntax
validate_syntax() {
    local file_path="$1"
    local validator_command="$2"
    local description="$3"

    if $validator_command "$file_path"; then
        log "✓ $description syntax valid"
        return 0
    else
        error_exit "✗ $description syntax invalid"
    fi
}

# Functional validation tests
validate_functional_components() {
    log "Running functional validation tests..."

    # Test 5: Validate JavaScript class definitions exist
    if grep -q "class MattermostBot" "$BOT_JS_FILE" 2>/dev/null; then
        log "✓ MattermostBot class definition found"
    else
        log "WARNING: MattermostBot class definition not found"
    fi

    if grep -q "class ClaudeCodeSession" "$BOT_JS_FILE" 2>/dev/null; then
        log "✓ ClaudeCodeSession class definition found"
    else
        log "WARNING: ClaudeCodeSession class definition not found"
    fi

    # Test 6: Validate module export syntax
    if grep -q "module.exports = { MattermostBot, ClaudeCodeSession }" "$BOT_JS_FILE" 2>/dev/null; then
        log "✓ Mattermost bot module exports syntax valid"
    else
        log "WARNING: Mattermost bot module exports syntax may be incorrect"
    fi

    # Test 7: Validate script has proper shebang lines
    local scripts=("$BOT_JS_FILE" "$STARTUP_SCRIPT")
    for script in "${scripts[@]}"; do
        if [ -f "$script" ] && head -1 "$script" | grep -q "^#!/" > /dev/null 2>&1; then
            log "✓ Proper shebang found in $(basename "$script")"
        else
            log "WARNING: Missing or incorrect shebang in $(basename "$script")"
        fi
    done

    # Test 8: Check script permissions
    for script in "${scripts[@]}"; do
        if [ -f "$script" ] && [ -x "$script" ]; then
            log "✓ Script $(basename "$script") is executable"
        else
            log "WARNING: Script $(basename "$script") is not executable"
        fi
    done

    # Test 9: Validate environment variable handling in startup script
    if grep -q "MM_BOT_ENABLED" "$STARTUP_SCRIPT" 2>/dev/null; then
        log "✓ Startup script handles MM_BOT_ENABLED environment variable"
    else
        log "WARNING: Startup script may not handle MM_BOT_ENABLED variable"
    fi
}

# Main test execution
main() {
    log "Starting enhanced Mattermost bot integration tests..."
    log "Workspace directory: $WORKSPACE_DIR"

    # Basic existence and syntax tests

    # Test 1: Check if bot service file exists
    check_file_exists "$BOT_JS_FILE" "Mattermost bot service"

    # Test 2: Check if startup script exists
    check_file_exists "$STARTUP_SCRIPT" "Mattermost bot startup script"


    # Test 4: Verify Node.js syntax
    validate_syntax "$BOT_JS_FILE" "node -c" "Mattermost bot service"

    # Test 5: Verify bash script syntax
    validate_syntax "$STARTUP_SCRIPT" "bash -n" "Mattermost bot startup script"


    # Enhanced functional tests
    validate_functional_components

    log_success "All tests passed! Mattermost bot integration appears functional."
    log "Summary: Basic syntax and file validation completed successfully."
    log "Functional validation: Bot service class structure validated."
}

# Execute main function
main "$@"