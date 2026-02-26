#!/usr/bin/with-contenv bash
# Mattermost Notification Script for Claude Code Development Environment
# Posts notifications to Mattermost when containers start

set -euo pipefail

# Logging functions following existing codebase patterns
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Error handling function
error_exit() {
    log "ERROR: $1" >&2
    exit 1
}

# Success logging function
log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1"
}

# Function to resolve channel name to channel ID using Mattermost API
resolve_channel_id() {
    local channel_name="$1"
    local mm_address="$2"
    local mm_token="$3"

    log "Resolving channel name '$channel_name' to channel ID..."

    # Call Mattermost API to get channel list
    response=$(curl -s \
        -H "Authorization: Bearer $mm_token" \
        "$mm_address/api/v4/channels" \
        || echo "")

    # Check if response is empty or contains error
    if [ -z "$response" ]; then
        error_exit "Failed to connect to Mattermost server at $mm_address"
    fi

    # Extract channel ID from response
    channel_id=$(echo "$response" | grep -o '"id":"[^"]*","name":"'"$channel_name"'"' | cut -d'"' -f4)

    if [ -z "$channel_id" ]; then
        error_exit "Channel '$channel_name' not found or authentication failed"
    fi

    echo "$channel_id"
}

# Function to post message to Mattermost channel
post_to_mattermost() {
    local mm_address="$1"
    local channel_id="$2"
    local mm_token="$3"
    local message="$4"

    log "Posting message to Mattermost channel ID: $channel_id"

    # Format message payload
    payload="{\"channel_id\": \"$channel_id\", \"message\": \"$message\"}"

    # Post message to Mattermost
    response=$(curl -s \
        -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $mm_token" \
        -d "$payload" \
        "$mm_address/api/v4/posts" \
        || echo "")

    # Check if message was posted successfully
    if [ -z "$response" ]; then
        error_exit "Failed to post message to Mattermost"
    fi

    # Verify response contains success indicators
    if ! echo "$response" | grep -q '"id"'; then
        error_exit "Message post failed - check Mattermost server configuration"
    fi

    log_success "Message posted to Mattermost successfully"
}

# Main execution logic
main() {
    log "Starting Mattermost notification script"

    # Validate required environment variables
    log "Validating environment variables..."

    if [ -z "${MM_ADDRESS:-}" ]; then
        error_exit "MM_ADDRESS environment variable is required"
    fi

    if [ -z "${MM_CHANNEL:-}" ]; then
        error_exit "MM_CHANNEL environment variable is required"
    fi

    if [ -z "${MM_TOKEN:-}" ]; then
        error_exit "MM_TOKEN environment variable is required"
    fi

    if [ -z "${PROMPT:-}" ]; then
        error_exit "PROMPT environment variable is required"
    fi

    if [ -z "${IDE_ADDRESS:-}" ]; then
        error_exit "IDE_ADDRESS environment variable is required"
    fi

    log "All required environment variables are present"

    # Resolve channel name to channel ID
    channel_id=$(resolve_channel_id "$MM_CHANNEL" "$MM_ADDRESS" "$MM_TOKEN")

    # Format markdown message
    message="🚀 **Claude Code Development Environment Started**

**Container Information:**
- **Prompt:** $PROMPT
- **IDE Address:** $IDE_ADDRESS
- **Started at:** $(date '+%Y-%m-%d %H:%M:%S')

**Environment Details:**
- Claude Code Version: 2.1.59.17f
- Platform: $(uname -s) $(uname -m)
- Working Directory: $(pwd)

This container is ready for development work!"

    # Post message to Mattermost
    post_to_mattermost "$MM_ADDRESS" "$channel_id" "$MM_TOKEN" "$message"

    log_success "Mattermost notification completed"
}

# Execute main function
main "$@"

exit 0