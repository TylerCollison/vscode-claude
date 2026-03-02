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

# Function to get existing channel by name
get_existing_channel() {
    local team_id="$1"
    local channel_name="$2"
    local mm_address="$3"
    local mm_token="$4"

    log "Checking for existing channel '$channel_name'..." >&2

    # Fetch channel by name using the team endpoint
    local response
    local http_code
    response=$(curl -s -w "%{http_code}" --max-time 30 \
        -H "Authorization: Bearer $mm_token" \
        "$mm_address/api/v4/teams/$team_id/channels/name/$channel_name")

    http_code="${response: -3}"
    local response_body="${response%???}"

    if [ "$http_code" = "200" ]; then
        # Parse channel ID from response
        local channel_id
        if command -v jq >/dev/null 2>&1; then
            channel_id=$(echo "$response_body" | jq -r '.id' 2>/dev/null || echo "")
        else
            channel_id=$(echo "$response_body" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
        fi

        if [ -n "$channel_id" ]; then
            log "Found existing channel with ID: $channel_id" >&2
            echo "$channel_id"
            return 0
        fi
    fi

    return 1
}

# Function to create a new Mattermost channel (or return existing one)
create_mattermost_channel() {
    local team_id="$1"
    local channel_name="$2"
    local display_name="$3"
    local mm_address="$4"
    local mm_token="$5"

    # First, check if channel already exists
    local existing_channel_id
    if existing_channel_id=$(get_existing_channel "$team_id" "$channel_name" "$mm_address" "$mm_token"); then
        log "Using existing channel: $channel_name" >&2
        echo "$existing_channel_id"
        return 0
    fi

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

    # Create channel - handle 409 conflict explicitly
    local response
    local http_code
    response=$(curl -s -w "%{http_code}" --max-time 30 \
        -X POST \
        -H "Authorization: Bearer $mm_token" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$mm_address/api/v4/channels")

    http_code="${response: -3}"
    local response_body="${response%???}"

    # Parse channel ID from response
    local channel_id
    if command -v jq >/dev/null 2>&1; then
        channel_id=$(echo "$response_body" | jq -r '.id' 2>/dev/null || echo "")
    else
        channel_id=$(echo "$response_body" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    fi

    case "$http_code" in
        "200"|"201")
            log "Created channel with ID: $channel_id" >&2
            echo "$channel_id"
            ;;
        "409")
            # Channel already exists - fetch it to get the ID
            log "Channel already exists (HTTP 409), fetching existing channel..." >&2
            local existing_id
            if existing_id=$(get_existing_channel "$team_id" "$channel_name" "$mm_address" "$mm_token"); then
                log "Using existing channel: $channel_name" >&2
                echo "$existing_id"
            else
                error_exit "Failed to get existing channel after 409 response"
            fi
            ;;
        *)
            error_exit "Failed to create channel - HTTP $http_code"
            ;;
    esac
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

 # Mattermost PUT /api/v4/channels/{channel_id} requires ALL fields: id, team_id, name, display_name, type, header, purpose
 # First, get the current channel data to preserve existing values
 log "Fetching current channel data..." >&2
 local channel_data
 channel_data=$(make_api_call "$mm_address/api/v4/channels/$channel_id" "GET" "" "$mm_token")

 # Extract required fields
 local team_id name display_name type purpose
 if command -v jq >/dev/null 2>&1; then
 team_id=$(echo "$channel_data" | jq -r '.team_id')
 name=$(echo "$channel_data" | jq -r '.name')
 display_name=$(echo "$channel_data" | jq -r '.display_name')
 type=$(echo "$channel_data" | jq -r '.type')
 purpose=$(echo "$channel_data" | jq -r '.purpose // ""')
 else
 team_id=$(echo "$channel_data" | grep -o '"team_id":"[^"]*"' | cut -d'"' -f4)
 name=$(echo "$channel_data" | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4)
 display_name=$(echo "$channel_data" | grep -o '"display_name":"[^"]*"' | cut -d'"' -f4)
 type=$(echo "$channel_data" | grep -o '"type":"[^"]*"' | head -1 | cut -d'"' -f4)
 purpose=$(echo "$channel_data" | grep -o '"purpose":"[^"]*"' | head -1 | cut -d'"' -f4 || echo "")
 fi

 # Build full payload with all required fields
 local full_payload
 if command -v jq >/dev/null 2>&1; then
 full_payload=$(jq -n \
 --arg id "$channel_id" \
 --arg team_id "$team_id" \
 --arg name "$name" \
 --arg display_name "$display_name" \
 --arg type "$type" \
 --arg header "$header" \
 --arg purpose "$purpose" \
 '{"id": $id, "team_id": $team_id, "name": $name, "display_name": $display_name, "type": $type, "header": $header, "purpose": $purpose}')
 else
 # Escape the header for JSON
 local escaped_header
 escaped_header=$(echo "$header" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g')
 local escaped_purpose
 escaped_purpose=$(echo "$purpose" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g')
 full_payload=$(printf '{"id": "%s", "team_id": "%s", "name": "%s", "display_name": "%s", "type": "%s", "header": "%s", "purpose": "%s"}' \
 "$channel_id" "$team_id" "$name" "$display_name" "$type" "$escaped_header" "$escaped_purpose")
 fi

 local response
 response=$(curl -s -w "%{http_code}" \
 -X PUT \
 -H "Authorization: Bearer $mm_token" \
 -H "Content-Type: application/json" \
 -d "$full_payload" \
 "$mm_address/api/v4/channels/$channel_id")

 local http_code="${response: -3}"

 case "$http_code" in
 "200")
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
  header="Claude Code | IDE: $IDE_ADDRESS | Started: $(date)"
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