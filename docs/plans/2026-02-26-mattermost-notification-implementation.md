# Mattermost Notification Script Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a startup script that posts notifications to Mattermost when Claude Code containers start.

**Architecture:** Bash script using curl for Mattermost API integration, runs as part of container startup sequence.

**Tech Stack:** Bash, curl, Mattermost REST API

---

### Task 1: Create Mattermost notification script

**Files:**
- Create: `/etc/cont-init.d/94-mattermost-notification`

**Step 1: Create script structure**

```bash
#!/usr/bin/with-contenv bash
# Mattermost notification script for Claude Code container startup
# Posts notification to Mattermost channel when container starts

set -euo pipefail

# Use existing logging patterns from codebase
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
```

**Step 2: Add environment variable validation**

```bash
# Validate required environment variables
log "Validating environment variables..."

# Required environment variables
REQUIRED_VARS=("MM_ADDRESS" "MM_CHANNEL" "MM_TOKEN" "PROMPT" "IDE_ADDRESS")

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        error_exit "Missing required environment variable: $var"
    fi
    log "✓ $var is set"
done

# Validate Mattermost server URL format
if [[ ! "$MM_ADDRESS" =~ ^https?:// ]]; then
    error_exit "MM_ADDRESS must start with http:// or https://: $MM_ADDRESS"
fi
```

**Step 3: Add channel resolution function**

```bash
# Get channel ID from channel name
resolve_channel_id() {
    local channel_name="$1"
    local response

    log "Resolving channel ID for: $channel_name"

    response=$(curl -s -w "%{http_code}" \
        -H "Authorization: Bearer $MM_TOKEN" \
        "$MM_ADDRESS/api/v4/channels/name/$channel_name")

    local http_code="${response: -3}"
    local response_body="${response%???}"

    if [ "$http_code" -eq 200 ]; then
        echo "$response_body" | jq -r '.id'
    elif [ "$http_code" -eq 404 ]; then
        error_exit "Channel '$channel_name' not found"
    else
        error_exit "Failed to resolve channel ID (HTTP $http_code): $response_body"
    fi
}
```

**Step 4: Add message posting function**

```bash
# Post message to Mattermost
post_to_mattermost() {
    local channel_id="$1"
    local message="$2"
    local response

    log "Posting message to Mattermost..."

    # Create JSON payload
    local payload
    payload=$(jq -n --arg channel_id "$channel_id" --arg message "$message" \
        '{"channel_id": $channel_id, "message": $message}')

    response=$(curl -s -w "%{http_code}" \
        -H "Authorization: Bearer $MM_TOKEN" \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$MM_ADDRESS/api/v4/posts")

    local http_code="${response: -3}"
    local response_body="${response%???}"

    if [ "$http_code" -eq 201 ]; then
        log_success "Message posted successfully"
    else
        error_exit "Failed to post message (HTTP $http_code): $response_body"
    fi
}
```

**Step 5: Add main execution logic**

```bash
# Main execution function
main() {
    log "Starting Mattermost notification..."

    # Resolve channel ID
    local channel_id
    channel_id=$(resolve_channel_id "$MM_CHANNEL")

    # Create formatted message
    local message
    message="## New Claude Code Session Started 🚀\n\n"
    message+="**Prompt:** $PROMPT\n"
    message+="**Session URL:** [$IDE_ADDRESS]($IDE_ADDRESS)\n"
    message+="**Container:** $(hostname)\n\n"
    message+="Started at: $(date)"

    # Post to Mattermost
    post_to_mattermost "$channel_id" "$message"

    log_success "Mattermost notification completed"
}

# Run main function
main "$@"
```

**Step 6: Set execute permissions**

```bash
# After creating the file, set execute permissions
chmod +x /etc/cont-init.d/94-mattermost-notification
```

**Step 7: Test script creation**

```bash
# Verify script was created correctly
ls -la /etc/cont-init.d/94-mattermost-notification
# Expected: -rwxr-xr-x 1 root root ... /etc/cont-init.d/94-mattermost-notification

# Check script syntax
bash -n /etc/cont-init.d/94-mattermost-notification
# Expected: No output (syntax OK)
```

**Step 8: Commit**

```bash
git add /etc/cont-init.d/94-mattermost-notification
git commit -m "feat: add Mattermost notification startup script"
```

### Task 2: Update Dockerfile to include the script

**Files:**
- Modify: `Dockerfile`

**Step 1: Add script copy command**

```dockerfile
# Add Mattermost notification script
COPY mattermost-notification.sh /etc/cont-init.d/94-mattermost-notification
RUN chmod +x /etc/cont-init.d/94-mattermost-notification
```

**Step 2: Verify Dockerfile syntax**

```bash
# Check Dockerfile syntax
docker build --no-cache --pull --file Dockerfile . --dry-run
# Expected: No syntax errors
```

**Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat: add Mattermost notification script to Dockerfile"
```

### Task 3: Update README with documentation

**Files:**
- Modify: `README.md`

**Step 1: Add Mattermost notification section**

```markdown
## Mattermost Notifications

This image includes a startup script that posts notifications to Mattermost when Claude Code containers start.

### Configuration

Set these environment variables to enable Mattermost notifications:

- `MM_ADDRESS`: Mattermost server URL (e.g., `http://portainer.home.com:8081`)
- `MM_CHANNEL`: Target channel name (e.g., `claude-code`)
- `MM_TOKEN`: Bot authentication token
- `PROMPT`: Initial prompt text provided to Claude
- `IDE_ADDRESS`: Claude Code session web address

### Example Docker Compose

```yaml
services:
  claude-dev:
    image: tylercollison2089/vscode-claude:latest
    environment:
      - MM_ADDRESS=http://portainer.home.com:8081
      - MM_CHANNEL=claude-code
      - MM_TOKEN=your-bot-token
      - PROMPT=Initial prompt text
      - IDE_ADDRESS=https://your-claude-session.example.com
    # ... other configuration
```
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add Mattermost notification documentation"
```

### Task 4: Test the implementation

**Files:**
- Test: Manual testing with environment variables

**Step 1: Set up test environment variables**

```bash
# Export test variables
export MM_ADDRESS="http://portainer.home.com:8081"
export MM_CHANNEL="claude-code"
export MM_TOKEN="wkansc9mcjfqtr4oubkh4kwmmw"
export PROMPT="Test prompt for Mattermost notification"
export IDE_ADDRESS="https://test-session.example.com"
```

**Step 2: Run script manually**

```bash
# Test script execution
/etc/cont-init.d/94-mattermost-notification
# Expected: Successful posting to Mattermost or appropriate error
```

**Step 3: Verify Mattermost post**

Check Mattermost channel `claude-code` for the test notification.

**Step 4: Commit any fixes**

```bash
git add .
git commit -m "test: verify Mattermost notification functionality"
```

---

Plan complete and saved to `docs/plans/2026-02-26-mattermost-notification-implementation.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?