#!/usr/bin/with-contenv bash

# Determine whether Claude Threads is enabled
log() {
    if [[ "${LOGGING:-}" == "verbose" ]] || [[ "$*" == *"ERROR"* ]] || [[ "$*" == *"WARNING"* ]]; then
        echo "$*"
    fi
}

if [[ "$ENABLE_THREADS" != "true" ]]; then
    log "Claude Threads Disabled"
    exit 0
else
    log "Claude Threads Enabled"
fi

log "Setting up Claude Threads server..."

# Run Claude Threads server in the background
log "Starting Claude Threads Server"
cd ${DEFAULT_WORKSPACE}
claude-threads