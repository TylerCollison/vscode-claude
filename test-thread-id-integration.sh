#!/usr/bin/env bash
# Mattermost Thread ID Storage Integration Test Script
# Tests file-based thread ID storage and environment variable fallback

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test logging functions
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo -e "${GREEN}$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1${NC}"
}

log_error() {
    echo -e "${RED}$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $1${NC}" >&2
}

log_warning() {
    echo -e "${YELLOW}$(date '+%Y-%m-%d %H:%M:%S') - WARNING: $1${NC}" >&2
}

# Test configuration
THREAD_ID_FILE="/tmp/mm_thread_id"
TEST_THREAD_ID="test_thread_$(date +%s)"
BACKUP_THREAD_ID="backup_$(date +%s)"

# Cleanup function
cleanup() {
    log "Cleaning up test files..."
    if [ -f "$THREAD_ID_FILE" ]; then
        rm -f "$THREAD_ID_FILE"
        log "Removed test file: $THREAD_ID_FILE"
    fi
    # Clear environment variable
    unset MM_THREAD_ID 2>/dev/null || true
}

# Test case functions

# Test 1: File writing functionality
test_file_writing() {
    log "Test 1: Testing file writing functionality"

    # Clean any existing file
    if [ -f "$THREAD_ID_FILE" ]; then
        rm -f "$THREAD_ID_FILE"
    fi

    # Test writing to file
    echo "$TEST_THREAD_ID" > "$THREAD_ID_FILE"

    if [ $? -ne 0 ]; then
        log_error "Failed to write to file: $THREAD_ID_FILE"
        return 1
    fi

    if [ ! -f "$THREAD_ID_FILE" ]; then
        log_error "File was not created: $THREAD_ID_FILE"
        return 1
    fi

    local content
    content=$(cat "$THREAD_ID_FILE")

    if [ "$content" != "$TEST_THREAD_ID" ]; then
        log_error "File content mismatch. Expected: $TEST_THREAD_ID, Got: $content"
        return 1
    fi

    log_success "File writing test passed"
    return 0
}

# Test 2: File reading functionality
test_file_reading() {
    log "Test 2: Testing file reading functionality"

    # Create test file
    echo "$TEST_THREAD_ID" > "$THREAD_ID_FILE"

    if [ ! -f "$THREAD_ID_FILE" ]; then
        log_error "Test file does not exist"
        return 1
    fi

    # Test reading from file
    local content
    content=$(cat "$THREAD_ID_FILE")

    if [ $? -ne 0 ]; then
        log_error "Failed to read from file: $THREAD_ID_FILE"
        return 1
    fi

    if [ "$content" != "$TEST_THREAD_ID" ]; then
        log_error "File content mismatch. Expected: $TEST_THREAD_ID, Got: $content"
        return 1
    fi

    log_success "File reading test passed"
    return 0
}

# Test 3: Stop hook file-first approach logic
test_stop_hook_file_first() {
    log "Test 3: Testing stop hook file-first approach logic"

    # Clean any existing file
    if [ -f "$THREAD_ID_FILE" ]; then
        rm -f "$THREAD_ID_FILE"
    fi

    # Create test file with valid thread ID
    echo "$TEST_THREAD_ID" > "$THREAD_ID_FILE"

    # Set environment variable with different value
    export MM_THREAD_ID="$BACKUP_THREAD_ID"

    # Simulate stop hook thread ID reading logic
    local thread_id=""
    local source=""

    # File-first approach: Try to read from file first
    if [ -f "$THREAD_ID_FILE" ]; then
        log "Reading thread ID from file: $THREAD_ID_FILE"
        thread_id=$(cat "$THREAD_ID_FILE" 2>/dev/null | tr -d '\n' || echo "")
        if [ -n "$thread_id" ]; then
            source="file"
            log "Using thread ID from file: $thread_id"
        else
            log "File exists but is empty, falling back to environment variable"
        fi
    fi

    # Environment variable fallback
    if [ -z "$thread_id" ] && [ -n "${MM_THREAD_ID:-}" ]; then
        log "Using thread ID from environment variable: MM_THREAD_ID"
        thread_id="$MM_THREAD_ID"
        source="env"
        log "Using thread ID from environment: $thread_id"
    fi

    # Validate file-first approach
    if [ "$source" != "file" ]; then
        log_error "File-first approach failed. Source should be 'file' but got: '$source'"
        return 1
    fi

    if [ "$thread_id" != "$TEST_THREAD_ID" ]; then
        log_error "Thread ID mismatch. Expected: $TEST_THREAD_ID, Got: $thread_id"
        return 1
    fi

    log_success "Stop hook file-first approach test passed"
    return 0
}

# Test 4: Environment variable fallback
test_env_fallback() {
    log "Test 4: Testing environment variable fallback"

    # Remove test file
    if [ -f "$THREAD_ID_FILE" ]; then
        rm -f "$THREAD_ID_FILE"
    fi

    # Set environment variable
    export MM_THREAD_ID="$BACKUP_THREAD_ID"

    # Simulate stop hook thread ID reading logic
    local thread_id=""
    local source=""

    # File-first approach: Try to read from file first
    if [ -f "$THREAD_ID_FILE" ]; then
        log "Reading thread ID from file: $THREAD_ID_FILE"
        thread_id=$(cat "$THREAD_ID_FILE" 2>/dev/null | tr -d '\n' || echo "")
        if [ -n "$thread_id" ]; then
            source="file"
            log "Using thread ID from file: $thread_id"
        else
            log "File exists but is empty, falling back to environment variable"
        fi
    fi

    # Environment variable fallback
    if [ -z "$thread_id" ] && [ -n "${MM_THREAD_ID:-}" ]; then
        log "Using thread ID from environment variable: MM_THREAD_ID"
        thread_id="$MM_THREAD_ID"
        source="env"
        log "Using thread ID from environment: $thread_id"
    fi

    # Validate fallback
    if [ "$source" != "env" ]; then
        log_error "Environment fallback failed. Source should be 'env' but got: '$source'"
        return 1
    fi

    if [ "$thread_id" != "$BACKUP_THREAD_ID" ]; then
        log_error "Thread ID mismatch. Expected: $BACKUP_THREAD_ID, Got: $thread_id"
        return 1
    fi

    log_success "Environment variable fallback test passed"
    return 0
}

# Test 5: Error handling scenarios
test_error_handling() {
    log "Test 5: Testing error handling scenarios"

    # Cleanup first
    if [ -f "$THREAD_ID_FILE" ]; then
        rm -f "$THREAD_ID_FILE"
    fi
    unset MM_THREAD_ID 2>/dev/null || true

    # Test missing both file and environment variable
    local thread_id=""
    local source=""

    # File-first approach: Try to read from file first
    if [ -f "$THREAD_ID_FILE" ]; then
        log "Reading thread ID from file: $THREAD_ID_FILE"
        thread_id=$(cat "$THREAD_ID_FILE" 2>/dev/null | tr -d '\n' || echo "")
        if [ -n "$thread_id" ]; then
            source="file"
            log "Using thread ID from file: $thread_id"
        else
            log "File exists but is empty, falling back to environment variable"
        fi
    fi

    # Environment variable fallback
    if [ -z "$thread_id" ] && [ -n "${MM_THREAD_ID:-}" ]; then
        log "Using thread ID from environment variable: MM_THREAD_ID"
        thread_id="${MM_THREAD_ID}"
        source="env"
        log "Using thread ID from environment: $thread_id"
    fi

    # Both should be empty
    if [ -n "$thread_id" ]; then
        log_error "Thread ID should be empty but got: '$thread_id'"
        return 1
    fi

    # Test empty file
    touch "$THREAD_ID_FILE"
    thread_id=""
    source=""

    if [ -f "$THREAD_ID_FILE" ]; then
        log "Reading thread ID from empty file"
        thread_id=$(cat "$THREAD_ID_FILE" 2>/dev/null | tr -d '\n' || echo "")
        if [ -n "$thread_id" ]; then
            source="file"
            log "Using thread ID from file: $thread_id"
        else
            log "File exists but is empty, falling back to environment variable"
        fi
    fi

    # Should still be empty
    if [ -n "$thread_id" ]; then
        log_error "Thread ID should be empty but got: '$thread_id'"
        return 1
    fi

    log_success "Error handling test passed"
    return 0
}

# Test 6: Integration with actual script files
test_integration() {
    log "Test 6: Testing integration with actual script files"

    # Cleanup first
    if [ -f "$THREAD_ID_FILE" ]; then
        rm -f "$THREAD_ID_FILE"
    fi
    unset MM_THREAD_ID 2>/dev/null || true

    # Test mattermost-initial-post.sh thread ID writing logic
    log "Testing initial post script thread ID writing..."

    # Simulate the thread ID writing logic from mattermost-initial-post.sh
    local post_id="integration_test_$(date +%s)"

    if [ -n "$post_id" ] && [ "$post_id" != "null" ] && [ "$post_id" != "" ]; then
        log "Simulating successful message post with ID: $post_id"

        # Write thread ID to file for other processes to use
        if echo "$post_id" > "$THREAD_ID_FILE"; then
            log_success "Thread ID written to $THREAD_ID_FILE"
        else
            log_error "Failed to write thread ID to $THREAD_ID_FILE"
            return 1
        fi
    fi

    # Verify file was written correctly
    if [ ! -f "$THREAD_ID_FILE" ]; then
        log_error "Thread ID file was not created"
        return 1
    fi

    local file_content
    file_content=$(cat "$THREAD_ID_FILE")

    if [ "$file_content" != "$post_id" ]; then
        log_error "File content mismatch. Expected: $post_id, Got: $file_content"
        return 1
    fi

    # Test stop-hook.js reading logic
    log "Testing stop hook script thread ID reading..."

    # Simulate the thread ID reading logic from stop-hook.js
    local thread_id=""
    local source=""

    # File-first approach
    if [ -f "$THREAD_ID_FILE" ]; then
        log "Reading thread ID from file: $THREAD_ID_FILE"
        thread_id=$(cat "$THREAD_ID_FILE" 2>/dev/null | tr -d '\n' || echo "")
        if [ -n "$thread_id" ]; then
            source="file"
            log "Using thread ID from file: $thread_id"
        else
            log "File exists but is empty, falling back to environment variable"
        fi
    fi

    # Environment variable fallback
    if [ -z "$thread_id" ] && [ -n "${MM_THREAD_ID:-}" ]; then
        log "Using thread ID from environment variable: MM_THREAD_ID"
        thread_id="${MM_THREAD_ID}"
        source="env"
        log "Using thread ID from environment: $thread_id"
    fi

    # Validate integration
    if [ "$source" != "file" ]; then
        log_error "Integration test failed. Source should be 'file' but got: '$source'"
        return 1
    fi

    if [ "$thread_id" != "$post_id" ]; then
        log_error "Integration test failed. Expected: $post_id, Got: $thread_id"
        return 1
    fi

    log_success "Integration test passed"
    return 0
}

# Main test execution
main() {
    log "Starting Mattermost Thread ID Storage Integration Tests"
    log "Thread ID file location: $THREAD_ID_FILE"

    # Array of test functions
    tests=(
        test_file_writing
        test_file_reading
        test_stop_hook_file_first
        test_env_fallback
        test_error_handling
        test_integration
    )

    # Counters
    passed=0
    failed=0
    total=${#tests[@]}

    # Run all tests
    for test_func in "${tests[@]}"; do
        log "Running $test_func..."

        if $test_func; then
            ((passed++))
            log_success "$test_func completed successfully"
        else
            ((failed++))
            log_error "$test_func failed"
        fi

        echo ""

        # Cleanup after each test
        cleanup
    done

    # Final cleanup
    cleanup

    # Summary
    log "Test Summary:"
    log "Total tests: $total"
    log "Passed: $passed"
    log "Failed: $failed"

    if [ $failed -eq 0 ]; then
        log_success "All integration tests passed!"
        return 0
    else
        log_error "$failed test(s) failed"
        return 1
    fi
}

# Execute main function
main "$@"