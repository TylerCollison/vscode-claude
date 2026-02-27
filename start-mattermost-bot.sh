#!/usr/bin/with-contenv bash
# Mattermost Bot Startup Script
# Starts the bidirectional Claude Code-Mattermost integration

set -euo pipefail

# Logging functions
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1"
}

error_exit() {
    log "ERROR: $1" >&2
    exit 1
}

# Check if bot integration is enabled
if [ "${MM_BOT_ENABLED:-false}" != "true" ]; then
    log "Mattermost bot integration disabled (MM_BOT_ENABLED not set to 'true')"
    exit 0
fi

# Validate required environment variables
log "Validating Mattermost bot environment variables..."

REQUIRED_VARS=("MM_ADDRESS" "MM_CHANNEL" "MM_TOKEN")
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        error_exit "Missing required environment variable: $var"
    fi
    log "✓ $var is set"
done

# Check if Node.js is available
if ! command -v node >/dev/null 2>&1; then
    error_exit "Node.js is required but not installed"
fi

# Check if mattermost-bot.js exists
if [ ! -f "/workspace/mattermost-bot.js" ]; then
    error_exit "Mattermost bot service not found at /workspace/mattermost-bot.js"
fi

log "Starting Mattermost bot service..."

# Start the bot service in background
node /workspace/mattermost-bot.js &

# Store PID for later management
BOT_PID=$!
echo $BOT_PID > /var/run/mattermost-bot.pid

log_success "Mattermost bot service started with PID: $BOT_PID"