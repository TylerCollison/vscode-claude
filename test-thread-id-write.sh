#!/bin/bash
# Test script for thread ID file writing functionality

set -euo pipefail

# Test logging functions
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1"
}

log_warning() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - WARNING: $1" >&2
}

# Function to test writing thread ID to file
test_write_thread_id() {
    local thread_id="$1"
    local output_file="/tmp/mm_thread_id"

    log "Testing thread ID write functionality..."

    # Create test thread ID
    if [ -z "$thread_id" ]; then
        thread_id="test_thread_$(date +%s)"
    fi

    # Write thread ID to file
    log "Writing thread ID '$thread_id' to $output_file"
    if echo "$thread_id" > "$output_file"; then
        log_success "Thread ID written successfully"
    else
        log_warning "Failed to write thread ID to file"
        return 1
    fi

    # Verify file was written
    if [ -f "$output_file" ] && [ -s "$output_file" ]; then
        local written_id
        written_id=$(cat "$output_file")
        if [ "$written_id" = "$thread_id" ]; then
            log_success "Thread ID verification passed"
            echo "Expected: $thread_id"
            echo "Actual: $written_id"
        else
            log_warning "Thread ID verification failed"
            echo "Expected: $thread_id"
            echo "Actual: $written_id"
            return 1
        fi
    else
        log_warning "Output file not found or empty"
        return 1
    fi

    # Clean up
    rm -f "$output_file"
    return 0
}

# Function to test error handling
test_error_handling() {
    log "Testing error handling scenarios..."

    # Test invalid file path
    local invalid_path="/invalid/directory/mm_thread_id"
    if echo "test" > "$invalid_path" 2>/dev/null; then
        log_warning "Should have failed with invalid path"
        return 1
    else
        log_success "Correctly handled invalid file path"
    fi

    # Test permission denied scenario (simulated with a read-only file)
    local temp_file="/tmp/test_readonly_file"
    touch "$temp_file"
    chmod a-w "$temp_file"  # Remove write permissions

    if echo "test" >> "$temp_file" 2>/dev/null; then
        log_warning "Should have failed with permission denied"
        chmod u+w "$temp_file"  # Restore permissions for cleanup
        rm -f "$temp_file"
        return 1
    else
        log_success "Correctly handled permission denied scenario"
        chmod u+w "$temp_file"  # Restore permissions for cleanup
        rm -f "$temp_file"
    fi

    return 0
}

# Main test execution
main() {
    log "Starting thread ID file writing tests"

    # Test normal operation
    if test_write_thread_id "test_post_123456"; then
        log_success "Normal operation test passed"
    else
        log_warning "Normal operation test failed"
        return 1
    fi

    # Test with generated thread ID
    if test_write_thread_id ""; then
        log_success "Generated thread ID test passed"
    else
        log_warning "Generated thread ID test failed"
        return 1
    fi

    # Test error handling
    if test_error_handling; then
        log_success "Error handling test passed"
    else
        log_warning "Error handling test failed"
        return 1
    fi

    log_success "All thread ID file writing tests completed successfully"
    return 0
}

# Run main function
main "$@"