#!/usr/bin/with-contenv bash
# Start Bead Me Up, Scotty — the Beads web UI (bead-me-up-scotty).
# Opt-in via ENABLE_SCOTTY=true. Runs the standalone Next.js server from
# /opt/bead-me-up-scotty as the abc user so it can read the workspace's
# .beads database and persist its config under /config/.config.

set -euo pipefail

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Skip unless explicitly enabled
if [[ "${ENABLE_SCOTTY:-}" != "true" ]]; then
    log "Scotty (Beads UI) not enabled (ENABLE_SCOTTY is not 'true'). Skipping."
    exit 0
fi

DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"
SCOTTY_DIR="/opt/bead-me-up-scotty"
SCOTTY_PID_FILE="/var/run/scotty.pid"
PORT="${SCOTTY_PORT:-3000}"

# The standalone server must have been built into the image
if [ ! -f "$SCOTTY_DIR/server.js" ]; then
    log "ERROR: Scotty not found at $SCOTTY_DIR. The image was built without it."
    exit 1
fi

# The UI shells out to `bd`, which must be on PATH (it is installed at
# /usr/local/bin/bd). Without it the app silently falls back to demo mode.
if ! command -v bd &> /dev/null; then
    log "WARNING: bd not found on PATH — Scotty will run in demo mode."
fi

# Avoid starting a duplicate server across container init re-runs
if [ -f "$SCOTTY_PID_FILE" ] && kill -0 "$(cat "$SCOTTY_PID_FILE")" 2>/dev/null; then
    log "Scotty already running (PID $(cat "$SCOTTY_PID_FILE")). Skipping."
    exit 0
fi

# The UI shells out to `bd` as the abc user, which needs to read and write
# the beads database. bd init runs as root, so hand the data dir to abc
# explicitly (targeted — never the whole workspace).
if [[ -n "${BEADS_DIR:-}" ]]; then
    BEADS_DATA_DIR="$BEADS_DIR"
else
    BEADS_DATA_DIR="$DEFAULT_WORKSPACE/.beads"
fi
if [ -d "$BEADS_DATA_DIR" ]; then
    chown -R abc:abc "$BEADS_DATA_DIR" 2>/dev/null || true
fi

# Stealth mode: the workspace has no .beads/ dir (the database lives at
# BEADS_DIR). Scotty only registers projects whose path contains a .beads
# directory, so link the workspace to BEADS_DIR. bd still resolves the
# database via the exported BEADS_DIR (the symlink is only for Scotty's
# project check) and the stealth git excludes keep it out of the repo.
if [[ -n "${BEADS_DIR:-}" ]]; then
    if [ ! -e "$DEFAULT_WORKSPACE/.beads" ]; then
        log "Linking $DEFAULT_WORKSPACE/.beads -> $BEADS_DIR (stealth mode)"
        ln -s "$BEADS_DIR" "$DEFAULT_WORKSPACE/.beads"
    fi
fi

# Ensure the abc user has a config dir for Scotty's project registry
mkdir -p /config/.config
chown -R abc:abc /config/.config 2>/dev/null || true

log "Starting Scotty (Beads UI) on port $PORT (workspace: $DEFAULT_WORKSPACE)..."
setpriv --reuid=abc --regid=abc --init-groups env \
    HOME=/config \
    BEADS_REPO="$DEFAULT_WORKSPACE" \
    PORT="$PORT" \
    HOSTNAME=0.0.0.0 \
    node "$SCOTTY_DIR/server.js" >/tmp/scotty.log 2>&1 &
echo $! > "$SCOTTY_PID_FILE"

# Wait for the server to start listening
MAX_RETRIES=30
COUNT=0
while ! nc -z 127.0.0.1 "$PORT" >/dev/null 2>&1; do
    sleep 1
    COUNT=$((COUNT + 1))
    if [ $COUNT -ge $MAX_RETRIES ]; then
        log "ERROR: Scotty failed to start after ${MAX_RETRIES}s (see /tmp/scotty.log)"
        exit 1
    fi
done

log "Scotty (Beads UI) is ready at http://localhost:$PORT"