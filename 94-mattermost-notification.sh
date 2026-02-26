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
        local curl_cmd=(curl -s -w "%{http_code}" --max-time 30 -H "Authorization: Bearer $mm_token")

        if [ "$method" = "POST" ]; then
            curl_cmd+=(-X POST -H "Content-Type: application/json")
            [ -n "$data" ] && curl_cmd+=(-d "$data")
        fi

        curl_cmd+=("$url")

        # Execute curl command and capture both response body and status code
        local response
        response=$("${curl_cmd[@]}")
        local http_code="${response: -3}"
        local response_body="${response%???}"

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
    local team_name="${4:-home}"

    log "Resolving channel name '$channel_name' to channel ID..." >&2

    # Use direct channel resolution endpoint with team name from MM_TEAM_NAME environment variable
    local response
    response=$(make_api_call "$mm_address/api/v4/teams/name/$team_name/channels/name/$channel_name" "GET" "" "$mm_token")

    # Use jq for robust JSON parsing
    if ! command -v jq >/dev/null 2>&1; then
        # Fallback to grep/cut with improved safety
        channel_id=$(echo "$response" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
        if [ -z "$channel_id" ]; then
            error_exit "Channel '$channel_name' not found or authentication failed"
        fi
    else
        # Use jq for proper JSON parsing
        channel_id=$(echo "$response" | jq -r '.id' 2>/dev/null || echo "")
        if [ -z "$channel_id" ]; then
            error_exit "Channel '$channel_name' not found or authentication failed"
        fi
    fi

    log "Resolved channel '$channel_name' in team '$team_name' to ID: $channel_id" >&2
    echo "$channel_id"
}

# Function to post message to Mattermost channel
post_to_mattermost() {
    local mm_address="$1"
    local channel_id="$2"
    local mm_token="$3"
    local message="$4"

    log "Posting message to Mattermost channel ID: $channel_id"

    # Format message payload using jq if available, otherwise use printf
    local payload
    if command -v jq >/dev/null 2>&1; then
        payload=$(jq -n --arg channel_id "$channel_id" --arg message "$message" '{"channel_id": $channel_id, "message": $message}')
    else
        payload=$(printf '{"channel_id": "%s", "message": "%s"}' "$channel_id" "$(echo "$message" | sed 's/"/\\"/g')")
    fi

    # Post message to Mattermost - use direct curl (proven to work)
    local response
    response=$(curl -s -w "%{http_code}" -H "Authorization: Bearer $mm_token" -H "Content-Type: application/json" -d "$payload" "$mm_address/api/v4/posts")

    # Validate response using jq if available
    if command -v jq >/dev/null 2>&1; then
        local post_id
        post_id=$(echo "$response" | jq -r '.id' 2>/dev/null || echo "")
        # Check if the response indicates an error
        local status_code
        status_code=$(echo "$response" | jq -r '.status_code' 2>/dev/null || echo "")
        if [ -n "$status_code" ] && [ "$status_code" != "null" ] && [ "$status_code" != "" ]; then
            # This is an error response
            error_exit "Message post failed - check Mattermost server configuration"
        fi
        if [ -n "$post_id" ] && [ "$post_id" != "null" ] && [ "$post_id" != "" ]; then
            log "Message posted successfully with ID: $post_id"
        else
            error_exit "Message post failed - check Mattermost server configuration"
        fi
    else
        # Fallback validation using grep
        if echo "$response" | grep -q '"status_code"'; then
            error_exit "Message post failed - check Mattermost server configuration"
        fi
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

    # Log team name being used (defaults to 'home' if MM_TEAM_NAME is not set)
    local team_name="${MM_TEAM_NAME:-home}"
    log "Using Mattermost team: $team_name"

    # Resolve channel name to channel ID
    channel_id=$(resolve_channel_id "$MM_CHANNEL" "$MM_ADDRESS" "$MM_TOKEN" "$team_name")

    # Format markdown message
    message="🚀 **Claude Code Development Environment Started**

**Container Information:**
- **Prompt:** $PROMPT
- **IDE Address:** $IDE_ADDRESS
- **Started at:** $(date)

This container is ready for development work!"

    # Post message to Mattermost
    post_to_mattermost "$MM_ADDRESS" "$channel_id" "$MM_TOKEN" "$message"

    log_success "Mattermost notification completed"
}

# Execute main function
main "$@"

exit 0