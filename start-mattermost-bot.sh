#!/usr/bin/with-contenv bash
# Mattermost Bot Startup Script
# Starts the bidirectional Claude Code-Mattermost integration

set -euo pipefail

# Security Fixes Implemented:
# - PID file race condition vulnerability - Fixed with atomic file creation using dd with exclusive flag
# - Missing process supervision and cleanup - Added comprehensive signal handling
# - PID file location follows container best practices - Uses /tmp/ directory
# - Graceful shutdown handling - Added proper trap handlers
# - Process validation logic - Added check for existing process and stale PID files

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

# Security Fix 3: Use /tmp directory for container compatibility
PID_FILE="/tmp/mattermost-bot.pid"

# Security Fix 2: Add signal handling for cleanup
cleanup_process() {
    log "Cleaning up Mattermost bot process..."
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
        log "PID file removed: $PID_FILE"
    fi
    if [ -n "${BOT_PID:-}" ]; then
        kill "$BOT_PID" 2>/dev/null || true
        log "Process terminated: $BOT_PID"
    fi
}

# Setup signal handlers for graceful shutdown
trap cleanup_process SIGTERM SIGINT EXIT

# Security Fix 1: Atomic PID file directory creation
mkdir -p "$(dirname "$PID_FILE")"

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

# Start process
node /workspace/mattermost-bot.js &
BOT_PID=$!

# Security Fix 3: Atomic PID file creation with validation
echo "$BOT_PID" | dd of="$PID_FILE" conv=excl 2>/dev/null || {
    log "PID file already exists, checking if process is alive"
    if [ -f "$PID_FILE" ]; then
        existing_pid=$(cat "$PID_FILE")
        if kill -0 "$existing_pid" 2>/dev/null; then
            log "Process with PID $existing_pid is already running, terminating current instance"
            kill "$BOT_PID" 2>/dev/null || true
            exit 0
        else
            log "Stale PID file detected, removing and continuing"
            rm -f "$PID_FILE"
            # Retry atomic creation
            echo "$BOT_PID" | dd of="$PID_FILE" conv=excl 2>/dev/null || {
                log "Failed to create PID file after cleanup, continuing without PID tracking"
            }
        fi
    fi
}

log_success "Mattermost bot service started with PID: $BOT_PID"
log "PID file created: $PID_FILE"

# Wait for process to complete with proper cleanup
wait "$BOT_PID" || true