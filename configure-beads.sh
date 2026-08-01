#!/usr/bin/with-contenv bash
# Configure Beads on container startup
# Initializes Beads (bd init) in the workspace when BEADS_ENABLED=true
# and optionally configures Dolt credentials for remote syncing.

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1"
}

# Skip unless Beads is explicitly enabled
if [[ "${BEADS_ENABLED:-}" != "true" ]]; then
    log "Beads not enabled (BEADS_ENABLED is not 'true'). Skipping Beads initialization."
    exit 0
fi

DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"

# Verify Beads is installed
if ! command -v bd &> /dev/null; then
    log "WARNING: Beads (bd) not found on PATH. Skipping initialization."
    exit 0
fi

log "Beads version: $(bd --version 2>/dev/null || echo 'unknown')"

# Initialize Beads in the workspace if not already initialized
if [ -d "$DEFAULT_WORKSPACE/.beads" ]; then
    log "Beads already initialized in $DEFAULT_WORKSPACE. Skipping bd init."
else
    log "Initializing Beads in $DEFAULT_WORKSPACE..."
    cd "$DEFAULT_WORKSPACE"
    if bd init; then
        log_success "Beads initialized in $DEFAULT_WORKSPACE"
    else
        log "WARNING: bd init failed. Beads may not be fully configured."
        exit 0
    fi
fi

# Configure Dolt/Git credentials for Beads remote sync
# In embedded mode, Dolt uses git config for user identity
if [[ -n "${DOLT_USERNAME:-}" ]] && [[ -n "${DOLT_EMAIL:-}" ]]; then
    log "Configuring Git/Dolt credentials for Beads remote sync..."
    git config --global user.name "$DOLT_USERNAME" 2>/dev/null || true
    git config --global user.email "$DOLT_EMAIL" 2>/dev/null || true
    log_success "Git/Dolt credentials configured"
fi

log_success "Beads startup completed"