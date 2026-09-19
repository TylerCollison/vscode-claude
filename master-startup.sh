#!/usr/bin/with-contenv bash
# Master Startup Script
# Executes all startup scripts in strict sequential order

set -euo pipefail

# Logging functions
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $1"
}

error_exit() {
    log "ERROR: $1" >&2
    exit 1
}

# Verbose-only logging (hidden unless LOGGING=verbose)
debug_log() {
    if [[ "${LOGGING:-}" == "verbose" ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
    fi
}

# List of scripts to execute in order
STARTUP_SCRIPTS=(
    "/92-configure-code-server-theme"
    "/93-git-repo-setup"
    "/94-combine-markdowns"
    "/95-configure-claude-skip-onboarding"
    "/96-start-lite-llm"
    "/97-configure-claude-permissions"
    "/98-configure-claude-plugins"
    "/99-mattermost-create-channel"
    "/100-configure-threads-settings"
    "/101-start-claude-threads"
    "/102-start-happier"
    "/103-configure-buildx"
    "/104-configure-beads"
    "/105-start-scotty"
    "/106-start-beads-dispatch"
    "/107-start-beads-sync"
    "/108-start-prompt-session"
    "/110-start-mr-pr-dispatch"
    "/109-start-mr-pr-sync"
)

log "Starting master startup sequence..."

# Execute each script in order
for script_path in "${STARTUP_SCRIPTS[@]}"; do
    script_name=$(basename "$script_path")

    # Check if script exists and is executable
    if [ ! -f "$script_path" ]; then
        log "WARNING: Script not found: $script_path"
        continue
    fi

    if [ ! -x "$script_path" ]; then
        log "WARNING: Script not executable: $script_path"
        continue
    fi

    log "Executing: $script_name"

    # Execute the script
    if "$script_path"; then
        log_success "Completed: $script_name"
    fi
done

log_success "All startup scripts completed successfully"
log "Container startup sequence finished"

# Ensure /config (and any files created by startup scripts) is owned by the abc user.
# Most files were pre-owned at build time (Dockerfile RUN chown) so this is a fast
# metadata-only pass with minimal overlay2 copy-up, limited to newly-created config files —
# *unless* PUID differs from the build-time UID (911). In that case, every pre-built
# file needs copy-up, which can stall on large caches (1.6 GB+).
#
# When abc is root (PUID=0), skip the chown entirely — root can access everything,
# and forcing 911→0 copy-up serves no purpose.
if [ -d /config ]; then
    if [ "$(id -u abc)" != "0" ]; then
        chown -R abc:abc /config 2>/dev/null || true
    fi
    debug_log "Config permissions set for /config"
fi

# Ensure workspace directory is owned by the abc user for non-root access.
# This directory is created at runtime by git-repo-setup.sh, so the files live
# on the writable layer — chown here doesn't trigger overlay2 copy-up.
DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"
if [ -d "$DEFAULT_WORKSPACE" ]; then
    chown -R abc:abc "$DEFAULT_WORKSPACE" 2>/dev/null || true
    debug_log "Workspace permissions set for $DEFAULT_WORKSPACE"
fi
