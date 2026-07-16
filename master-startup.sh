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

# List of scripts to execute in order
STARTUP_SCRIPTS=(
    "/93-git-repo-setup"
    "/94-combine-markdowns"
    "/95-configure-claude-skip-onboarding"
    "/96-start-lite-llm"
    "/97-configure-claude-permissions"
    "/98-configure-claude-plugins"
    "/99-mattermost-create-channel"
    "/100-configure-threads-settings"
    "/101-start-claude-threads", 
    "/102-start-happier"
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

# Ensure workspace directory is owned by the abc user for non-root access
DEFAULT_WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"
if [ -d "$DEFAULT_WORKSPACE" ]; then
    lsiown -R abc:abc "$DEFAULT_WORKSPACE" 2>/dev/null || true
    log "Workspace permissions set for $DEFAULT_WORKSPACE"
fi

# Ensure config directory is owned by the abc user (catch any remaining paths)
if [ -d /config ]; then
    lsiown -R abc:abc /config 2>/dev/null || true
    log "Config permissions set for /config"
fi
