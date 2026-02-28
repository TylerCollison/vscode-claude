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
    "/95-git-repo-setup"
    "/96-combine-markdowns"
    "/97-configure-ccr-settings"
    "/98-configure-claude-permissions"
    "/99-configure-claude-plugins"
    "/100-mattermost-initial-post"
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