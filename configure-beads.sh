#!/usr/bin/with-contenv bash
# Configure Beads on container startup
# Initializes Beads (bd init) in the workspace when BEADS_ENABLED=true
# and optionally configures Dolt credentials for remote syncing.
#
# Stealth mode: when BEADS_DIR is set, the Beads database is stored at
# $BEADS_DIR instead of the workspace and initialized with
# `bd init --quiet --stealth` so no beads files clutter the workspace.

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

# Stealth mode: if BEADS_DIR is set, keep the Beads database out of the
# workspace (data lives at $BEADS_DIR) and use quiet stealth init.
STEALTH_MODE=0
if [[ -n "${BEADS_DIR:-}" ]]; then
    STEALTH_MODE=1
fi

# Verify Beads is installed
if ! command -v bd &> /dev/null; then
    log "WARNING: Beads (bd) not found on PATH. Skipping initialization."
    exit 0
fi

log "Beads version: $(bd --version 2>/dev/null || echo 'unknown')"

# Where Beads data lives (for the already-initialized check)
# - Stealth mode:  $BEADS_DIR (the dir itself, marker = metadata.json)
# - Standard mode: $DEFAULT_WORKSPACE/.beads
if [ "$STEALTH_MODE" = "1" ]; then
    BEADS_DATA_DIR="$BEADS_DIR"
else
    BEADS_DATA_DIR="$DEFAULT_WORKSPACE/.beads"
fi

# Initialize Beads if not already initialized
if [ -f "$BEADS_DATA_DIR/metadata.json" ]; then
    if [ "$STEALTH_MODE" = "1" ]; then
        log "Beads already initialized at $BEADS_DIR (stealth mode). Skipping bd init."
    else
        log "Beads already initialized in $DEFAULT_WORKSPACE. Skipping bd init."
    fi
else
    log "Initializing Beads in $DEFAULT_WORKSPACE..."
    mkdir -p "$DEFAULT_WORKSPACE"
    cd "$DEFAULT_WORKSPACE"
    if [ "$STEALTH_MODE" = "1" ]; then
        # Stealth init: quiet, no workspace clutter, data stored in $BEADS_DIR.
        # bd init still runs from the workspace so stealth git excludes are
        # configured in the repo (.git/info/exclude) when one is present.
        if bd init --quiet --stealth; then
            log_success "Beads initialized at $BEADS_DIR (stealth mode)"
        else
            log "WARNING: bd init --quiet --stealth failed. Beads may not be fully configured."
            exit 0
        fi
    else
        if bd init; then
            log_success "Beads initialized in $DEFAULT_WORKSPACE"
        else
            log "WARNING: bd init failed. Beads may not be fully configured."
            exit 0
        fi
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