#!/usr/bin/with-contenv bash
# Configure Beads on container startup
# Initializes Beads (bd init) in the workspace and optionally configures Dolt
# credentials for remote syncing.
#
# Task sync for replicated (worker) containers:
#   - The dispatcher pushes the beads Dolt DB (gitignored) to the git remote
#     via `bd dolt push` before spawning a worker.
#   - On startup, this script syncs the DB from the git remote: `bd bootstrap`
#     clones it when the remote has Dolt data (creating the local DB), with
#     `bd init` as the fallback when no remote/DB exists.
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

# Beads initialization and task sync (dolt push/pull) is now always attempted so
# that replicated (worker) containers pick up tasks on startup. BEADS_ENABLED no
# longer gates init/sync (only the *full* setup + credentials are gated); it is
# kept here for backward compatibility of logs.
BEADS_ENABLED_ONLY="${BEADS_ENABLED:-}"

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

# ── Dolt task sync (runs BEFORE init: bootstrap must clone into a fresh DB) ──
# Replicated (worker) containers clone the git repo but NOT the gitignored
# .beads Dolt DB, so on startup we sync the DB from the git remote the same way
# the dispatcher pushes it. Both the parent (which pushes) and workers (which
# pull) run this; it is idempotent and non-fatal.
#   - BEADS_REMOTE (set by the dispatcher on workers) is the Dolt remote URL.
#   - Fall back to GIT_REPO_URL or the workspace git origin.
BEADS_REMOTE_URL="${BEADS_REMOTE:-${GIT_REPO_URL:-}}"
if [ -z "$BEADS_REMOTE_URL" ] && [ -d "$DEFAULT_WORKSPACE/.git" ]; then
    BEADS_REMOTE_URL="$(git -C "$DEFAULT_WORKSPACE" remote get-url origin 2>/dev/null || true)"
fi

# DOLT_SYNC_DONE: set when the sync block cloned the DB from a remote; in that
# case bd init is intentionally NOT run (bootstrap refuses an existing DB).
DOLT_SYNC_DONE=0

if [ -n "$BEADS_REMOTE_URL" ]; then
    log "Syncing Beads tasks with remote: $BEADS_REMOTE_URL"
    cd "$DEFAULT_WORKSPACE"

    # 1. Ensure the Dolt remote exists (idempotent).
    bd dolt remote add origin "$BEADS_REMOTE_URL" >/dev/null 2>&1 \
        || log "WARNING: could not add dolt remote (may already exist)"

    # 2. Clone/pull: bootstrap clones from the remote and creates the local DB.
    #    ('bd bootstrap' auto-detects a Dolt DB on the remote and clones it,
    #    creating the local database — the recommended path for workers. Plain
    #    init + `bd dolt pull` risks divergent histories, and running init
    #    before bootstrap makes bootstrap refuse an existing DB.)
    if bd bootstrap --yes >/dev/null 2>&1; then
        DOLT_SYNC_DONE=1
        log "Bootstrapped Beads database from $BEADS_REMOTE_URL"
    else
        # Remote has no Dolt data yet, or DB already exists locally: plain pull.
        bd dolt pull >/dev/null 2>&1 || true
    fi

    # 3. The parent should also push its own DB up so workers can see new tasks
    #    even if the dispatcher's per-task push wasn't the last writer. Only the
    #    parent (BEADS_DISPATCH != 'false') pushes; workers never push back.
    if [[ "${BEADS_DISPATCH:-}" != "false" ]]; then
        bd dolt push >/dev/null 2>&1 \
            || log "WARNING: initial bd dolt push failed (workers may not see existing tasks)"
    fi
fi

# Initialize Beads if not already initialized (and not cloned from a remote).
if [ "$DOLT_SYNC_DONE" != "1" ]; then
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
fi

# The Beads database is used by services running as the abc user (e.g. the
# Scotty web UI and Claude Code). bd init above ran as root, and the recursive
# chown in master-startup.sh only runs after a potentially slow /config pass,
# so make the data dir abc-owned right here. Targeted to the small .beads dir
# (never the whole workspace).
if [ -d "$BEADS_DATA_DIR" ]; then
    chown -R abc:abc "$BEADS_DATA_DIR" 2>/dev/null || true
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