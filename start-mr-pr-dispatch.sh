#!/usr/bin/with-contenv bash
# Start the MR/PR Responder Dispatch daemon.
# Opt-in via MR_PR_DISPATCH=true.
# Listens on a unix socket for MR/PR events and dispatches worker containers.

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Skip unless explicitly enabled
if [[ "${MR_PR_DISPATCH:-}" != "true" ]]; then
    log "MR/PR dispatch not enabled (MR_PR_DISPATCH is not 'true'). Skipping."
    exit 0
fi

# Verify prerequisites
for binary in docker git python3 gh glab; do
    if ! command -v "$binary" &> /dev/null; then
        log "WARNING: $binary not found on PATH — skipping."
        exit 0
    fi
done

# Check for docker socket at both common locations
DOCKER_SOCK=""
for sock in /var/run/docker.sock /run/docker.sock; do
    if [ -S "$sock" ]; then
        DOCKER_SOCK="$sock"
        break
    fi
done

if [ -z "$DOCKER_SOCK" ]; then
    log "WARNING: Docker socket not found at /var/run/docker.sock or /run/docker.sock — the dispatcher cannot talk to the host Docker daemon. Skipping."
    exit 0
fi

DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"
STATE_DIR="${MR_PR_DISPATCH_STATE_DIR:-/config/.mr-pr-dispatch}"
mkdir -p "$STATE_DIR"

PID_FILE="/var/run/mr-pr-dispatch.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "MR/PR dispatch already running (PID $(cat "$PID_FILE")). Skipping."
    exit 0
fi

log "Starting MR/PR dispatch daemon (workspace: $DEFAULT_WORKSPACE, state: $STATE_DIR)..."
/usr/local/bin/mr_pr_dispatch.py --daemon > /tmp/mr-pr-dispatch.log 2>&1 &
echo $! > "$PID_FILE"
log "MR/PR dispatch daemon started (PID $(cat "$PID_FILE")). Log: /tmp/mr-pr-dispatch.log"