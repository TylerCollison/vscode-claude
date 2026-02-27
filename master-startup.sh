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
    "/etc/cont-init.d/95-git-repo-setup.disabled"
    "/etc/cont-init.d/96-combine-markdowns.disabled"
    "/etc/cont-init.d/97-configure-ccr-settings.disabled"
    "/etc/cont-init.d/98-configure-claude-permissions.disabled"
    "/etc/cont-init.d/99-configure-claude-plugins.disabled"
    "/etc/cont-init.d/100-mattermost-bot.disabled"
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
    else
        error_exit "Failed to execute: $script_name"
    fi
done

log_success "All startup scripts completed successfully"
log "Container startup sequence finished"