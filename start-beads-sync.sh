#!/usr/bin/with-contenv bash
# Start the Beads External Task Manager Sync daemon.
# Opt-in via BEADS_SYNC_PROVIDERS (comma-separated: jira,github,gitlab,linear,dolt).
# Runs `bd <provider> sync` for external providers, or `bd dolt pull` for dolt,
# at the specified interval.
# Requires BEADS_SYNC_PROVIDERS to be set and non-empty.

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Skip unless explicitly enabled with at least one provider
SYNC_PROVIDERS="${BEADS_SYNC_PROVIDERS:-}"
if [ -z "$SYNC_PROVIDERS" ]; then
    log "Beads sync not enabled (BEADS_SYNC_PROVIDERS not set). Skipping."
    exit 0
fi

# Verify prerequisites
if ! command -v bd &> /dev/null; then
    log "WARNING: bd not found on PATH — skipping."
    exit 0
fi

DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"

# Beads must be initialized (the .beads directory must exist)
# In stealth mode, BEADS_DIR is used instead
if [[ -n "${BEADS_DIR:-}" ]]; then
    BEADS_DATA_DIR="$BEADS_DIR"
else
    BEADS_DATA_DIR="$DEFAULT_WORKSPACE/.beads"
fi

if [ ! -d "$BEADS_DATA_DIR" ]; then
    log "WARNING: Beads not initialized at $BEADS_DATA_DIR — skipping."
    exit 0
fi

# Configuration
SYNC_INTERVAL="${BEADS_SYNC_INTERVAL:-300}"
RUN_ON_START="${BEADS_SYNC_RUN_ON_START:-true}"

# Parse providers (comma-separated)
IFS=',' read -ra PROVIDERS <<< "$SYNC_PROVIDERS"

# Validate providers
VALID_PROVIDERS=()
for provider in "${PROVIDERS[@]}"; do
    provider=$(echo "$provider" | xargs)  # trim whitespace
    case "$provider" in
        jira|github|gitlab|linear|dolt)
            VALID_PROVIDERS+=("$provider")
            ;;
        *)
            log "WARNING: Unknown provider '$provider' — skipping."
            ;;
    esac
done

if [ ${#VALID_PROVIDERS[@]} -eq 0 ]; then
    log "No valid providers configured — skipping."
    exit 0
fi

log "Beads sync enabled for providers: ${VALID_PROVIDERS[*]} (interval: ${SYNC_INTERVAL}s)"

PID_FILE="/var/run/beads-sync.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "Beads sync already running (PID $(cat "$PID_FILE")). Skipping."
    exit 0
fi

# The sync needs to run as the abc user to access git credentials
# (gh/glab credential helpers are configured for abc)
RUN_USER="abc"

# Function to run sync for all providers
run_sync() {
    log "Starting sync cycle..."
    for provider in "${VALID_PROVIDERS[@]}"; do
        log "Syncing with $provider..."
        # Run as abc user so gh/glab credential helpers work
        # Use the abc user's home directory (/config) if it exists, otherwise use root's home
        if [ -d "/config" ]; then
            SYNC_HOME="/config"
        else
            SYNC_HOME="/root"
        fi

        # Determine the correct sync command
        if [ "$provider" = "dolt" ]; then
            SYNC_CMD=(bd dolt pull --directory "$DEFAULT_WORKSPACE")
        else
            SYNC_CMD=(bd "$provider" sync --directory "$DEFAULT_WORKSPACE")
        fi

        if setpriv --reuid="$RUN_USER" --regid="$RUN_USER" --init-groups \
            env HOME="$SYNC_HOME" \
            "${SYNC_CMD[@]}" 2>&1 | while IFS= read -r line; do
            log "[$provider] $line"
        done; then
            log "Sync with $provider completed"
        else
            log "WARNING: Sync with $provider failed"
        fi
    done
    log "Sync cycle completed"

    # Trigger the beads dispatcher if enabled
    if [[ "${BEADS_DISPATCH:-}" == "true" ]]; then
        log "Triggering Beads dispatcher..."
        python3 -c '
import socket
try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(1.0)
    s.connect("/run/beads-dispatch.sock")
    s.sendall(b"sync")
    s.close()
    print("Beads dispatcher triggered successfully.")
except Exception as e:
    print(f"WARNING: Failed to trigger Beads dispatcher: {e}")
' 2>&1 | while IFS= read -r line; do
            log "[dispatcher-trigger] $line"
        done
    fi
}

# Start the sync daemon
log "Starting Beads sync daemon (workspace: $DEFAULT_WORKSPACE, interval: ${SYNC_INTERVAL}s)..."

# Run initial sync if enabled
if [[ "$RUN_ON_START" == "true" ]]; then
    run_sync
fi

# Background loop
(
    while true; do
        sleep "$SYNC_INTERVAL"
        run_sync
    done
) > /tmp/beads-sync.log 2>&1 &

echo $! > "$PID_FILE"
log "Beads sync daemon started (PID $(cat "$PID_FILE")). Log: /tmp/beads-sync.log"