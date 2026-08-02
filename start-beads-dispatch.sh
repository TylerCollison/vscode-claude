#!/usr/bin/with-contenv bash
# Start the Beads Dispatch daemon.
# Opt-in via BEADS_DISPATCH=true. Installs a git post-commit hook in the
# workspace repo and runs a root daemon that listens on a unix socket. On
# every commit the hook pings the socket; the daemon checks bd for ready
# tasks and dispatches a worker (swarm service or local container) for each,
# creating the task branch off the current HEAD and pushing it.
#
# Runs as ROOT: dispatch shells out to `docker` via the mounted host socket,
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

# No repo yet (GIT_REPO_URL unset and no mounted workspace): the dispatcher has
# nothing to hook into, so skip. It can be started manually after a repo exists.
if [ ! -d "$DEFAULT_WORKSPACE/.git" ]; then
    log "WARNING: no git repository found at $DEFAULT_WORKSPACE — skipping (the dispatcher triggers on git commits)."
    exit 0
fi

PID_FILE="/var/run/beads-dispatch.pid"
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    log "Beads dispatch already running (PID $(cat "$PID_FILE")). Skipping."
    exit 0
fi

log "Starting Beads dispatch daemon (workspace: $DEFAULT_WORKSPACE, state: $STATE_DIR)..."
/usr/local/bin/beads-dispatch --daemon > /tmp/beads-dispatch.log 2>&1 &
echo $! > "$PID_FILE"
log "Beads dispatch daemon started (PID $(cat "$PID_FILE")). Log: /tmp/beads-dispatch.log"