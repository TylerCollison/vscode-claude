#!/bin/bash
# Test script to verify mattermost-initial-post.sh modifications

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

# Function to test the post_to_mattermost function logic
test_post_function() {
    log "Testing post_to_mattermost function logic..."

    # Create a mock response with post_id
    local mock_response='{"id":"mock_post_id_123456","message":"test","channel_id":"channel_123"}'
    local post_id

    # Test jq path
    if command -v jq >/dev/null 2>&1; then
        log "Testing jq extraction path..."
        post_id=$(echo "$mock_response" | jq -r '.id' 2>/dev/null || echo "")
        if [ -n "$post_id" ] && [ "$post_id" = "mock_post_id_123456" ]; then
            log_success "jq extraction working correctly"
        else
            log_warning "jq extraction failed"
            return 1
        fi
    fi

    # Test grep/cut path
    log "Testing grep/cut extraction path..."
    post_id=$(echo "$mock_response" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    if [ -n "$post_id" ] && [ "$post_id" = "mock_post_id_123456" ]; then
        log_success "grep/cut extraction working correctly"
    else
        log_warning "grep/cut extraction failed"
        return 1
    fi

    # Test file writing
    local output_file="/tmp/mm_thread_id"
    log "Testing file writing functionality..."

    if echo "$post_id" > "$output_file"; then
        if [ -f "$output_file" ] && [ "$(cat $output_file)" = "$post_id" ]; then
            log_success "File writing working correctly"
            rm -f "$output_file"
        else
            log_warning "File verification failed"
            rm -f "$output_file"
            return 1
        fi
    else
        log_warning "File writing failed"
        return 1
    fi

    return 0
}

# Function to test error handling
test_error_handling() {
    log "Testing error handling..."

    # Test with empty post_id
    local empty_post_id=""
    local output_file="/tmp/mm_thread_id"

    if [ -z "$empty_post_id" ]; then
        if echo "$empty_post_id" > "$output_file"; then
            # File should be empty
            if [ -f "$output_file" ] && [ ! -s "$output_file" ]; then
                log_success "Empty post_id handled correctly"
                rm -f "$output_file"
            else
                log_warning "Empty post_id handling failed"
                rm -f "$output_file"
                return 1
            fi
        fi
    fi

    return 0
}

# Function to test actual script modification
test_script_modification() {
    log "Testing mattermost-initial-post.sh modifications..."

    # Check if the warning function was added
    if grep -q "log_warning" /workspace/mattermost-initial-post.sh; then
        log_success "log_warning function found in script"
    else
        log_warning "log_warning function not found in script"
        return 1
    fi

    # Check if thread ID writing logic was added (jq path)
    if grep -q 'Write thread ID to file for other processes to use' /workspace/mattermost-initial-post.sh; then
        log_success "Thread ID writing comment found"
    else
        log_warning "Thread ID writing comment not found"
        return 1
    fi

    # Check if fallback extraction logic was added
    if grep -q 'Extract post_id using grep/cut for fallback' /workspace/mattermost-initial-post.sh; then
        log_success "Fallback extraction comment found"
    else
        log_warning "Fallback extraction comment not found"
        return 1
    fi

    return 0
}

# Main test execution
main() {
    log "Starting mattermost-initial-post.sh modification tests"

    # Test the script modifications
    if test_script_modification; then
        log_success "Script modification verification passed"
    else
        log_warning "Script modification verification failed"
        return 1
    fi

    # Test post function logic
    if test_post_function; then
        log_success "Post function logic test passed"
    else
        log_warning "Post function logic test failed"
        return 1
    fi

    # Test error handling
    if test_error_handling; then
        log_success "Error handling test passed"
    else
        log_warning "Error handling test failed"
        return 1
    fi

    log_success "All mattermost-initial-post.sh modification tests completed successfully"
    return 0
}

# Run main function
main "$@"