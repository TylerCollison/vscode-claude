#!/usr/bin/with-contenv bash
# Start the Beads Dispatch watcher.
# Opt-in via BEADS_DISPATCH=true. Polls the Beads ready set and dispatches a
# worker (swarm service or local container) for each newly-ready task, with
# GIT_BRANCH_NAME set to a branch named after the task.
#
# Runs as ROOT: the watcher shells out to `docker` via the mounted host socket,
# which is only accessible to root/group 989 in this image.

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Skip unless explicitly enabled
if [[ "${BEADS_DISPATCH:-}" != "true" ]]; then
    log "Beads dispatch not enabled (BEADS_DISPATCH is not 'true'). Skipping."
    exit 0
fi

# Verify prerequisites
if ! command -v bd &> /dev/null; then
    log "WARNING: bd not found on PATH — skipping."
    exit 0
fi
if ! command -v docker &> /dev/null; then
    log "WARNING: docker not found on PATH — skipping."
    exit 0
fi
if [ ! -S /var/run/docker.sock ]; then
    log "WARNING: /var/run/docker.sock not mounted — the dispatcher cannot talk to the host Docker daemon. Skipping."
    exit 0
fi

DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"
STATE_DIR="${BEADS_DISPATCH_STATE_DIR:-/config/.beads-dispatch}"
mkdir -p "$STATE_DIR"

PID_FILE="/var/run/beads-dispatch.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "Beads dispatch already running (PID $(cat "$PID_FILE")). Skipping."
    exit 0
fi

log "Starting Beads dispatch watcher (workspace: $DEFAULT_WORKSPACE, state: $STATE_DIR)..."
/usr/local/bin/beads-dispatch > /tmp/beads-dispatch.log 2>&1 &
echo $! > "$PID_FILE"
log "Beads dispatch watcher started (PID $(cat "$PID_FILE")). Log: /tmp/beads-dispatch.log"