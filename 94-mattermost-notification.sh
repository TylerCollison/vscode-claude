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

# Function to make secure API calls with timeout and retry logic
make_api_call() {
    local url="$1"
    local method="${2:-GET}"
    local data="${3:-}"
    local mm_token="$4"
    local max_retries=2
    local retry_count=0

    while [ $retry_count -le $max_retries ]; do
        # Use process substitution to hide token from command-line arguments
        local auth_header_file
        auth_header_file=$(mktemp)
        echo "Authorization: Bearer $mm_token" > "$auth_header_file"

        local curl_cmd=(curl -s -w "%{http_code}" --max-time 30)

        if [ "$method" = "POST" ]; then
            curl_cmd+=(-X POST -H "Content-Type: application/json")
            [ -n "$data" ] && curl_cmd+=(-d "$data")
        fi

        curl_cmd+=(-H "@$auth_header_file" "$url")

        # Execute curl command and capture both response body and status code
        local response
        response=$("${curl_cmd[@]}")
        local http_code="${response: -3}"
        local response_body="${response%???}"

        # Clean up temp file
        rm -f "$auth_header_file"

        # Handle HTTP status codes
        case "$http_code" in
            "200"|"201")
                echo "$response_body"
                return 0
                ;;
            "401"|"403")
                error_exit "API authentication failed (HTTP $http_code) - check Mattermost token"
                ;;
            "404")
                error_exit "API endpoint not found (HTTP $http_code) - check Mattermost server address"
                ;;
            "429")
                log "Rate limited (HTTP $http_code), waiting before retry..."
                sleep 5
                ((retry_count++))
                ;;
            "5"*)
                log "Server error (HTTP $http_code), retrying..."
                ((retry_count++))
                sleep 2
                ;;
            "000")
                log "Network error (HTTP $http_code), retrying..."
                ((retry_count++))
                sleep 2
                ;;
            *)
                error_exit "Unexpected HTTP response code: $http_code"
                ;;
        esac
    done

    error_exit "API call failed after $max_retries retries"
}

# Function to resolve channel name to channel ID using Mattermost API
resolve_channel_id() {
    local channel_name="$1"
    local mm_address="$2"
    local mm_token="$3"

    log "Resolving channel name '$channel_name' to channel ID..."

    # Call Mattermost API to get channel list
    local response
    response=$(make_api_call "$mm_address/api/v4/channels" "GET" "" "$mm_token")

    # Use jq for robust JSON parsing
    if ! command -v jq >/dev/null 2>&1; then
        # Fallback to grep/cut with improved safety
        channel_id=$(echo "$response" | grep -o '"id":"[^"]*","name":"'"$channel_name"'"' | head -1 | cut -d'"' -f4)
        if [ -z "$channel_id" ]; then
            # Try alternative pattern
            channel_id=$(echo "$response" | grep -o '"name":"'"$channel_name"'","id":"[^"]*"' | head -1 | cut -d'"' -f8)
        fi
    else
        # Use jq for proper JSON parsing
        channel_id=$(echo "$response" | jq -r --arg channel "$channel_name"
            '.[] | select(.name == $channel) | .id' 2>/dev/null || echo "")
    fi

    if [ -z "$channel_id" ]; then
        error_exit "Channel '$channel_name' not found or authentication failed"
    fi

    log "Resolved channel '$channel_name' to ID: $channel_id"
    echo "$channel_id"
}

# Function to post message to Mattermost channel
post_to_mattermost() {
    local mm_address="$1"
    local channel_id="$2"
    local mm_token="$3"
    local message="$4"

    log "Posting message to Mattermost channel ID: $channel_id"

    # Escape message for JSON
    local escaped_message
    escaped_message=$(echo "$message" | sed 's/"/\\"/g' | sed 's/\n/\\n/g')

    # Format message payload
    local payload="{\"channel_id\": \"$channel_id\", \"message\": \"$escaped_message\"}"

    # Post message to Mattermost
    local response
    response=$(make_api_call "$mm_address/api/v4/posts" "POST" "$payload" "$mm_token")

    # Validate response using jq if available
    if command -v jq >/dev/null 2>&1; then
        local post_id
        post_id=$(echo "$response" | jq -r '.id' 2>/dev/null || echo "")
        if [ -z "$post_id" ]; then
            error_exit "Failed to parse successful response from Mattermost"
        fi
        log "Message posted successfully with ID: $post_id"
    else
        # Fallback validation using grep
        if ! echo "$response" | grep -q '"id"'; then
            error_exit "Message post failed - check Mattermost server configuration"
        fi
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