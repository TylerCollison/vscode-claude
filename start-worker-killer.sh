#!/usr/bin/with-contenv bash
# Start the Worker Killer daemon.
# Opt-in via WORKER_KILLER=true. Periodically checks the worker's MR/PR
# and shuts down the container when the MR/PR closes (merged or closed
# without merging) after a 5-minute grace period with re-verification.
#
# Runs as ROOT: uses the host's git/gh/glab via setpriv as abc user.
# No docker socket required — shutdown is via /usr/local/bin/shutdown.

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Skip unless explicitly enabled
if [[ "${WORKER_KILLER:-}" != "true" ]]; then
    log "Worker killer not enabled (WORKER_KILLER is not 'true'). Skipping."
    exit 0
fi

# Verify prerequisites
for binary in gh glab git python3; do
    if ! command -v "$binary" &> /dev/null; then
        log "WARNING: $binary not found on PATH — skipping."
        exit 0
    fi
done

DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"
STATE_DIR="${WORKER_KILLER_STATE_DIR:-/config/.worker-killer}"
mkdir -p "$STATE_DIR"

PID_FILE="/var/run/worker-killer.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "Worker killer already running (PID $(cat "$PID_FILE")). Skipping."
    exit 0
fi

log "Starting worker killer daemon (state: $STATE_DIR, interval: ${WORKER_KILLER_INTERVAL:-300}s)..."
/usr/local/bin/worker_killer.py --daemon > /tmp/worker-killer.log 2>&1 &
echo $! > "$PID_FILE"
log "Worker killer daemon started (PID $(cat "$PID_FILE")). Log: /tmp/worker-killer.log"