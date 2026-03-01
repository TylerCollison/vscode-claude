# Mattermost Channel Creation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Modify `mattermost-initial-post.sh` to create a new Mattermost channel instead of posting to an existing one, set the channel header, add the bot user to the channel, and update the config.yaml with the channel ID.

**Architecture:** The script will use Mattermost REST API to create a channel, retrieve the bot user ID, add the user to the channel, update the channel header, and then update the config file. All operations follow existing error handling patterns in the codebase.

**Tech Stack:** Bash, curl, Mattermost API v4, jq (for JSON parsing)

---

## Prerequisites Check

Before starting, verify these files exist:
- `/workspace/mattermost-initial-post.sh` - The script to modify
- `/config/.config/claude-threads/config.yaml` - The config file to update

---

## Task 1: Add Channel Name Sanitization Function

**Files:**
- Modify: `/workspace/mattermost-initial-post.sh` (add new function before `main()`)

**Step 1: Write the sanitized channel name function**

Add this function after the `log_warning()` function (around line 26):

```bash
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
```

**Step 2: Verify script syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 3: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "feat: add channel name sanitization function"
```

---

## Task 2: Add get_user_id Function

**Files:**
- Modify: `/workspace/mattermost-initial-post.sh` (add new function before `main()`)

**Step 1: Write function to get user ID from token**

Add this function after `sanitize_channel_name`:

```bash
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
```

**Step 2: Verify script syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 3: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "feat: add get_user_id function"
```

---

## Task 3: Add get_team_id Function

**Files:**
- Modify: `/workspace/mattermost-initial-post.sh` (add new function before `main()`)

**Step 1: Write function to get team ID from team name**

Add this function after `get_user_id`:

```bash
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
```

**Step 2: Verify script syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 3: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "feat: add get_team_id function"
```

---

## Task 4: Add create_mattermost_channel Function

**Files:**
- Modify: `/workspace/mattermost-initial-post.sh` (add new function before `main()`)

**Step 1: Write function to create a new channel**

Add this function after `get_team_id`:

```bash
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
```

**Step 2: Verify script syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 3: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "feat: add create_mattermost_channel function"
```

---

## Task 5: Add add_user_to_channel Function

**Files:**
- Modify: `/workspace/mattermost-initial-post.sh` (add new function before `main()`)

**Step 1: Write function to add user to channel**

Add this function after `create_mattermost_channel`:

```bash
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
```

**Step 2: Verify script syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 3: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "feat: add add_user_to_channel function"
```

---

## Task 6: Add update_channel_header Function

**Files:**
- Modify: `/workspace/mattermost-initial-post.sh` (add new function before `main()`)

**Step 1: Write function to update channel header**

Add this function after `add_user_to_channel`:

```bash
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
```

**Step 2: Verify script syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 3: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "feat: add update_channel_header function"
```

---

## Task 7: Add update_config_file Function

**Files:**
- Modify: `/workspace/mattermost-initial-post.sh` (add new function before `main()`)

**Step 1: Write function to update config.yaml**

Add this function after `update_channel_header`:

```bash
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

  if sed "s/\${MM_CHANNEL_ID}/$channel_id/g" "$config_file" > "$temp_file"; then
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
```

**Step 2: Verify script syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 3: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "feat: add update_config_file function"
```

---

## Task 8: Update main() Function

**Files:**
- Modify: `/workspace/mattermost-initial-post.sh:main()` (replace existing main function)

**Step 1: Replace the main() function**

Replace the entire `main()` function (lines 196-250 approximately) with this new version:

```bash
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
```

**Step 2: Verify script syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 3: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "feat: update main() to create channel, set header, and update config"
```

---

## Task 9: Remove Unused Functions

**Files:**
- Modify: `/workspace/mattermost-initial-post.sh` (remove old functions)

**Step 1: Remove resolve_channel_id function**

This function is no longer needed since we create the channel instead of resolving it. Delete lines 89-119 (the `resolve_channel_id` function).

**Step 2: Remove post_to_mattermost function**

This function is no longer needed since we don't post messages anymore. Delete the `post_to_mattermost` function (lines 121-194 after the previous deletion).

**Step 3: Verify script syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 4: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "refactor: remove unused resolve_channel_id and post_to_mattermost functions"
```

---

## Task 10: Test Script Syntax

**Files:**
- Test: `/workspace/mattermost-initial-post.sh`

**Step 1: Run shellcheck if available**

Run: `which shellcheck && shellcheck /workspace/mattermost-initial-post.sh || echo "shellcheck not available, skipping"`

**Step 2: Test bash syntax**

Run: `bash -n /workspace/mattermost-initial-post.sh`
Expected: No output (syntax OK)

**Step 3: Make script executable**

Run: `chmod +x /workspace/mattermost-initial-post.sh`

**Step 4: Commit**

```bash
git add mattermost-initial-post.sh
git commit -m "chore: make script executable and verify syntax"
```

---

## Task 11: Create Test Script (Optional but Recommended)

**Files:**
- Create: `/workspace/test-channel-creation.sh`

**Step 1: Write test script**

```bash
#!/usr/bin/env bash
# Test script for Mattermost channel creation

set -euo pipefail

echo "=== Mattermost Channel Creation Test ==="
echo

# Check if required env vars are set
if [ -z "${MM_ADDRESS:-}" ] || [ -z "${MM_TOKEN:-}" ]; then
  echo "WARNING: MM_ADDRESS and MM_TOKEN must be set for live testing"
  echo "Testing in dry-run mode (syntax only)"
  echo
fi

# Test script syntax
echo "Testing script syntax..."
if bash -n /workspace/mattermost-initial-post.sh; then
  echo "✓ Script syntax is valid"
else
  echo "✗ Script has syntax errors"
  exit 1
fi

# Test that functions are defined
echo
echo "Checking function definitions..."
for func in sanitize_channel_name get_user_id get_team_id create_mattermost_channel add_user_to_channel update_channel_header update_config_file; do
  if grep -q "^$func()" /workspace/mattermost-initial-post.sh; then
    echo "✓ Function '$func' is defined"
  else
    echo "✗ Function '$func' is NOT defined"
  fi
done

echo
echo "=== Test Complete ==="
```

Make it executable:
Run: `chmod +x /workspace/test-channel-creation.sh`

**Step 2: Run test**

Run: `/workspace/test-channel-creation.sh`
Expected: All functions found, syntax valid

**Step 3: Commit**

```bash
git add test-channel-creation.sh
git commit -m "test: add channel creation test script"
```

---

## Task 12: Update Documentation

**Files:**
- Modify: `/workspace/README.md` (update relevant section)

**Step 1: Update README with new behavior**

Find the section about Mattermost and update it to reflect:
- Script now creates a new channel instead of posting to existing
- Channel name is sanitized from MM_CHANNEL env var
- Channel header contains device information
- Config file is automatically updated with channel ID

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with new channel creation behavior"
```

---

## Summary

After completing all tasks:
- `mattermost-initial-post.sh` creates a new Mattermost channel
- Channel name is sanitized from MM_CHANNEL env var
- Bot user is automatically added to the channel
- Channel header contains formatted device information
- `/config/.config/claude-threads/config.yaml` is updated with the channel ID
- Old message-posting code is removed
- Tests verify the implementation

The script maintains backward compatibility with existing environment variables while changing the behavior from "post to existing channel" to "create new channel".
