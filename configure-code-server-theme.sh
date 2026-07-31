#!/usr/bin/with-contenv bash
# Configure code-server color theme from VSCODE_THEME environment variable

# Source container environment variables
if [ -d /run/s6/container_environment ]; then
    for file in /run/s6/container_environment/*; do
        if [ -f "$file" ]; then
            export "$(basename "$file")=$(cat "$file")"
        fi
    done
fi

# Logging function following existing patterns
log() {
    if [[ "${LOGGING:-}" == "verbose" ]] || [[ "$*" == *"ERROR"* ]] || [[ "$*" == *"WARNING"* ]]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $*"
    fi
}

VSCODE_THEME="${VSCODE_THEME:-}"

# If no theme is specified, skip
if [ -z "$VSCODE_THEME" ]; then
    log "VSCODE_THEME not set — skipping code-server theme configuration"
    exit 0
fi

log "Configuring code-server theme: $VSCODE_THEME"

# code-server stores user settings under ~/.local/share/code-server/User/settings.json.
# The linuxserver image runs code-server as the abc user (HOME=/config).
SETTINGS_DIR="/config/.local/share/code-server/User"
SETTINGS_FILE="$SETTINGS_DIR/settings.json"

mkdir -p "$SETTINGS_DIR"

# Merge the theme into the existing settings.json (or create a new one)
if [ -f "$SETTINGS_FILE" ]; then
    # Use jq to update workbench.colorTheme in place
    if command -v jq >/dev/null 2>&1; then
        jq --arg theme "$VSCODE_THEME" '.["workbench.colorTheme"] = $theme' "$SETTINGS_FILE" \
            > "${SETTINGS_FILE}.tmp" \
            && mv "${SETTINGS_FILE}.tmp" "$SETTINGS_FILE"
        log "Theme updated to: $VSCODE_THEME"
    else
        log "WARNING: jq not found — overwriting settings.json with minimal config"
        cat > "$SETTINGS_FILE" << EOF
{
  "workbench.colorTheme": "$VSCODE_THEME"
}
EOF
    fi
else
    # Create a fresh settings.json with just the theme
    cat > "$SETTINGS_FILE" << EOF
{
  "workbench.colorTheme": "$VSCODE_THEME"
}
EOF
    log "Created settings.json with theme: $VSCODE_THEME"
fi

log "code-server theme configuration complete"