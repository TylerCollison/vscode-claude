#!/usr/bin/with-contenv bash
# Start the Worker Reaper daemon.
# Opt-in via WORKER_REAPER=true. Periodically removes dispatched worker
# services/containers (beads-* and mr-pr-*) that ran to completion: a worker is
# only removed after the reaper has observed it UP at least once and it is now
# DOWN, so freshly created (not yet started) workers are never touched.
#
# Runs as ROOT: shells out to `docker` via the mounted host socket.

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Skip unless explicitly enabled
if [[ "${WORKER_REAPER:-}" != "true" ]]; then
    log "Worker reaper not enabled (WORKER_REAPER is not 'true'). Skipping."
    exit 0
fi

# Verify prerequisites
if ! command -v docker &> /dev/null; then
    log "WARNING: docker not found on PATH — skipping."
    exit 0
fi

# Check for docker socket at both common locations
docker_sock=""
for sock in /var/run/docker.sock /run/docker.sock; do
    if [ -S "$sock" ]; then
        docker_sock="$sock"
        break
    fi
done
if [ -z "$docker_sock" ]; then
    log "WARNING: Docker socket not found at /var/run/docker.sock or /run/docker.sock — the reaper cannot talk to the host Docker daemon. Skipping."
    exit 0
fi

STATE_DIR="${WORKER_REAPER_STATE_DIR:-/config/.worker-reaper}"
mkdir -p "$STATE_DIR"

PID_FILE="/var/run/worker-reaper.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "Worker reaper already running (PID $(cat "$PID_FILE")). Skipping."
    exit 0
fi

log "Starting worker reaper daemon (state: $STATE_DIR, interval: ${WORKER_REAPER_INTERVAL:-60}s)..."
/usr/local/bin/worker_reaper.py --daemon > /tmp/worker-reaper.log 2>&1 &
echo $! > "$PID_FILE"
log "Worker reaper daemon started (PID $(cat "$PID_FILE")). Log: /tmp/worker-reaper.log"
