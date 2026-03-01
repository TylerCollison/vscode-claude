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

# Warning logging function
log_warning() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - WARNING: $1" >&2
}

# Function to sanitize channel name for Mattermost
# Mattermost requires: lowercase, alphanumeric and hyphens only
sanitize_channel_name() {
 local name="$1"
 # Convert to lowercase
 name=$(echo "$name" | tr '[:upper:]' '[:lower:]')
 # Replace spaces and underscores with hyphens
 name=$(echo "$name" | tr ' _' '-')
 # Remove any characters that aren't alphanumeric or hyphens
 name=$(echo "$name" | sed 's/[^a-z0-9-]//g')
 # Remove leading/trailing hyphens
 name=$(echo "$name" | sed 's/^-//;s/-$//')
 # Collapse multiple hyphens into one
 name=$(echo "$name" | sed 's/-\+/-/g')
 echo "$name"
}

# Function to get user ID from Mattermost token
get_user_id() {
  local mm_address="$1"
  local mm_token="$2"

  log "Getting user ID from token..." >&2

  local response
  response=$(make_api_call "$mm_address/api/v4/users/me" "GET" "" "$mm_token")

  # Parse user ID from response
  local user_id
  if command -v jq >/dev/null 2>&1; then
    user_id=$(echo "$response" | jq -r '.id' 2>/dev/null || echo "")
  else
    user_id=$(echo "$response" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
  fi

  if [ -z "$user_id" ]; then
    error_exit "Failed to get user ID from token"
  fi

  log "Got user ID: $user_id" >&2
  echo "$user_id"
}

# Function to get team ID from team name
get_team_id() {
  local team_name="$1"
  local mm_address="$2"
  local mm_token="$3"

  log "Getting team ID for team '$team_name'..." >&2

  local response
  response=$(make_api_call "$mm_address/api/v4/teams/name/$team_name" "GET" "" "$mm_token")

  # Parse team ID from response
  local team_id
  if command -v jq >/dev/null 2>&1; then
    team_id=$(echo "$response" | jq -r '.id' 2>/dev/null || echo "")
  else
    team_id=$(echo "$response" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
  fi

  if [ -z "$team_id" ]; then
    error_exit "Failed to get team ID for team '$team_name'"
  fi

  log "Got team ID: $team_id" >&2
  echo "$team_id"
}

# Function to create a new Mattermost channel
create_mattermost_channel() {
  local team_id="$1"
  local channel_name="$2"
  local display_name="$3"
  local mm_address="$4"
  local mm_token="$5"

  log "Creating channel '$channel_name' (display: '$display_name')..." >&2

  # Build payload
  local payload
  if command -v jq >/dev/null 2>&1; then
    payload=$(jq -n \
      --arg team_id "$team_id" \
      --arg name "$channel_name" \
      --arg display_name "$display_name" \
      '{"team_id": $team_id, "name": $name, "display_name": $display_name, "type": "O"}')
  else
    payload=$(printf '{"team_id": "%s", "name": "%s", "display_name": "%s", "type": "O"}' \
      "$team_id" "$channel_name" "$display_name")
  fi

  # Create channel
  local response
  response=$(make_api_call "$mm_address/api/v4/channels" "POST" "$payload" "$mm_token")

  # Parse channel ID from response
  local channel_id
  if command -v jq >/dev/null 2>&1; then
    channel_id=$(echo "$response" | jq -r '.id' 2>/dev/null || echo "")
  else
    channel_id=$(echo "$response" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
  fi

  if [ -z "$channel_id" ]; then
    error_exit "Failed to create channel - no channel ID in response"
  fi

  log "Created channel with ID: $channel_id" >&2
  echo "$channel_id"
}

# Function to add a user to a channel
add_user_to_channel() {
  local channel_id="$1"
  local user_id="$2"
  local mm_address="$3"
  local mm_token="$4"

  log "Adding user $user_id to channel $channel_id..." >&2

  # Build payload
  local payload
  if command -v jq >/dev/null 2>&1; then
    payload=$(jq -n --arg user_id "$user_id" '{"user_id": $user_id}')
  else
    payload=$(printf '{"user_id": "%s"}' "$user_id")
  fi

  # Add user to channel (ignore 409 conflict - user already in channel)
  local response
  local http_code
  response=$(curl -s -w "%{http_code}" \
    -H "Authorization: Bearer $mm_token" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "$mm_address/api/v4/channels/$channel_id/members")

  http_code="${response: -3}"

  case "$http_code" in
    "201"|"200")
      log "User added to channel successfully" >&2
      ;;
    "409")
      log "User already in channel (OK)" >&2
      ;;
    *)
      log_warning "Unexpected response adding user to channel: HTTP $http_code" >&2
      ;;
  esac
}

# Function to update channel header
update_channel_header() {
  local channel_id="$1"
  local header="$2"
  local mm_address="$3"
  local mm_token="$4"

  log "Updating channel header..." >&2

  # Build payload
  local payload
  if command -v jq >/dev/null 2>&1; then
    payload=$(jq -n --arg header "$header" '{"header": $header}')
  else
    # Escape the header for JSON
    local escaped_header
    escaped_header=$(echo "$header" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g')
    payload=$(printf '{"header": "%s"}' "$escaped_header")
  fi

  # Update channel header using PUT request
  local response
  response=$(curl -s -w "%{http_code}" \
    -X PUT \
    -H "Authorization: Bearer $mm_token" \
    -H "Content-Type: application/json" \
    -d "$payload" \
    "$mm_address/api/v4/channels/$channel_id")

  local http_code="${response: -3}"

  case "$http_code" in
    "200"|"201")
      log "Channel header updated successfully" >&2
      ;;
    *)
      log_warning "Failed to update channel header: HTTP $http_code" >&2
      ;;
  esac
}

# Function to update config.yaml with the new channel ID
update_config_file() {
  local channel_id="$1"
  local config_file="${CONFIG_FILE:-/config/.config/claude-threads/config.yaml}"

  log "Updating config file: $config_file"

  if [ ! -f "$config_file" ]; then
    log_warning "Config file not found: $config_file"
    return 1
  fi

  # Replace ${MM_CHANNEL_ID} with actual channel ID
  # Use a temp file for atomic update
  local temp_file
  temp_file=$(mktemp)

  if sed "s/\\${MM_CHANNEL_ID}/$channel_id/g" "$config_file" > "$temp_file"; then
    if mv "$temp_file" "$config_file"; then
      log_success "Config file updated with channel ID: $channel_id"
      return 0
    else
      rm -f "$temp_file"
      log_warning "Failed to move updated config file"
      return 1
    fi
  else
    rm -f "$temp_file"
    log_warning "Failed to update config file"
    return 1
  fi
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

# Main execution logic
main() {
  log "Starting Mattermost channel creation script"

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

  # Get team name (defaults to 'home')
  local team_name="${MM_TEAM:-home}"
  log "Using Mattermost team: $team_name"

  # Sanitize channel name
  local channel_name
  channel_name=$(sanitize_channel_name "$MM_CHANNEL")
  log "Sanitized channel name: $channel_name"

  # Get team ID
  local team_id
  team_id=$(get_team_id "$team_name" "$MM_ADDRESS" "$MM_TOKEN")

  # Get bot user ID
  local user_id
  user_id=$(get_user_id "$MM_ADDRESS" "$MM_TOKEN")

  # Create the channel
  local channel_id
  channel_id=$(create_mattermost_channel "$team_id" "$channel_name" "$MM_CHANNEL" "$MM_ADDRESS" "$MM_TOKEN")

  # Add bot user to the channel
  add_user_to_channel "$channel_id" "$user_id" "$MM_ADDRESS" "$MM_TOKEN"

  # Format channel header
  local header
  header="Claude Code | Prompt: $PROMPT | IDE: $IDE_ADDRESS | Started: $(date)"
  # Truncate if too long (Mattermost limit is around 1024 chars for headers)
  if [ ${#header} -gt 250 ]; then
    header="${header:0:247}..."
  fi

  # Update channel header
  update_channel_header "$channel_id" "$header" "$MM_ADDRESS" "$MM_TOKEN"

  # Write channel ID to file for reference (similar to thread_id in previous version)
  local channel_id_file="/tmp/mm_channel_id"
  if echo "$channel_id" > "$channel_id_file"; then
    log_success "Channel ID written to $channel_id_file"
  else
    log_warning "Failed to write channel ID to $channel_id_file"
  fi

  # Update config.yaml with the channel ID
  update_config_file "$channel_id"

  log_success "Mattermost channel creation completed successfully"
  log "Channel ID: $channel_id"
  log "Channel URL: $MM_ADDRESS/$team_name/channels/$channel_name"
}

# Execute main function
main "$@"

exit 0