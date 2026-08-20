#!/usr/bin/with-contenv bash
# Start a Claude Code session with a prompt from the PROMPT environment variable.
# If HAPPIER_MODE is set, starts the session via Happier for web UI access.
# Otherwise, starts a regular Claude Code session.

set -euo pipefail

# Source container environment variables
if [ -d /run/s6/container_environment ]; then
    for file in /run/s6/container_environment/*; do
        if [ -f "$file" ]; then
            export "$(basename "$file")=$(cat "$file")"
        fi
    done
fi

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

# Skip if PROMPT is not set
if [ -z "${PROMPT:-}" ]; then
    log "PROMPT environment variable not set. Skipping prompt session startup."
    exit 0
fi

DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"

# Ensure we're in the workspace
if [ ! -d "$DEFAULT_WORKSPACE" ]; then
    error_exit "Workspace directory not found: $DEFAULT_WORKSPACE"
fi

cd "$DEFAULT_WORKSPACE"

log "Starting Claude Code session with PROMPT..."

# Check if Happier mode is enabled
if [ -n "${HAPPIER_MODE:-}" ]; then
    log "HAPPIER_MODE is set (${HAPPIER_MODE}). Starting session via Happier for web UI access."

    # Check if Happier daemon is running and authenticated
    HAPPIER_SERVER_URL="${HAPPIER_SERVER_URL:-https://localhost:3005}"

    # Try to start a Happier session with the prompt
    # Use the anthropic profile (Claude Code backend) with the prompt
    log "Executing: happier --profile anthropic -p \"${PROMPT}\""
    happier --profile anthropic -p "${PROMPT}" &

    HAPPIER_PID=$!
    log "Happier session started with PID $HAPPIER_PID"
    log_success "Prompt session started via Happier (web UI accessible)"

else
    log "HAPPIER_MODE not set. Starting regular Claude Code session."

    # Start a regular Claude Code session with the prompt
    # Use --print for non-interactive mode, or run interactively in background
    log "Executing: claude -p \"${PROMPT}\""
    claude -p "${PROMPT}" &

    CLAUDE_PID=$!
    log "Claude Code session started with PID $CLAUDE_PID"
    log_success "Prompt session started (regular Claude Code)"
fi