#!/usr/bin/with-contenv bash
# Configure Claude Code marketplaces and plugins from environment variables

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
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $*"
}

# Error logging function
log_error() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ERROR: $*" >&2
}

# Success logging function
log_success() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - SUCCESS: $*"
}

# Check if Claude CLI is available
check_claude_cli() {
    if ! command -v claude >/dev/null 2>&1; then
        log_error "Claude CLI not found in PATH"
        return 1
    fi
    log "Claude CLI is available"
    return 0
}

# Check network connectivity
check_network() {
    if ! curl -s --connect-timeout 10 --max-time 30 https://api.github.com >/dev/null 2>&1; then
        log_error "Network connectivity check failed"
        return 1
    fi
    log "Network connectivity verified"
    return 0
}

# Parse comma-separated environment variable
parse_env_var() {
    local var_name="$1"
    # Use indirect variable expansion
    local var_value="${!var_name:-}"

    if [ -z "$var_value" ]; then
        return 1
    fi

    # Remove leading/trailing whitespace and split by comma
    var_value=$(echo "$var_value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    echo "$var_value" | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | grep -v '^$'
}

# Extract marketplace name from URL or source
extract_marketplace_name() {
    local source="$1"

    # Handle GitHub URLs
    if [[ "$source" =~ github\.com/([^/]+)/([^/]+) ]]; then
        local org="${BASH_REMATCH[1]}"
        local repo="${BASH_REMATCH[2]}"
        echo "${org}-${repo}" | sed 's/[^a-zA-Z0-9_-]//g'
    # Handle simple names
    else
        echo "$source" | sed 's/[^a-zA-Z0-9_-]//g'
    fi
}

# Add marketplace configuration
add_marketplace_config() {
    local source="$1"
    local marketplace_name=$(extract_marketplace_name "$source")

    log "Configuring marketplace: $source (name: $marketplace_name)"

    # Create marketplace directory
    local marketplace_dir="/config/.claude/plugins/marketplaces/$marketplace_name"
    mkdir -p "$marketplace_dir"

    # Create marketplace configuration
    cat > "$marketplace_dir/.mcp.json" << EOF
{
  "name": "$marketplace_name",
  "version": "1.0.0",
  "source": "$source"
}
EOF

    # Update known_marketplaces.json
    local known_file="/config/.claude/plugins/known_marketplaces.json"
    if [ ! -f "$known_file" ]; then
        echo '{}' > "$known_file"
    fi

    jq --arg name "$marketplace_name" --arg source "$source" '
    .[$name] = {
        "source": {
            "source": "github",
            "repo": "anthropics/claude-plugins"
        },
        "installLocation": "/config/.claude/plugins/marketplaces/'"$marketplace_name"'",
        "lastUpdated": "'"$(date -Iseconds)"'"
    }
    ' "$known_file" > "${known_file}.tmp" && mv "${known_file}.tmp" "$known_file"

    log_success "Marketplace configured: $marketplace_name"
    return 0
}

# Enable plugin in settings
enable_plugin() {
    local plugin_name="$1"

    log "Enabling plugin: $plugin_name"

    # Update settings.json
    local settings_file="/config/.claude/settings.json"
    if [ ! -f "$settings_file" ]; then
        echo '{}' > "$settings_file"
    fi

    # Enable the plugin
    jq --arg plugin "$plugin_name" '
    if .enabledPlugins then . else .enabledPlugins = {} end |
    .enabledPlugins[$plugin] = true
    ' "$settings_file" > "${settings_file}.tmp" && mv "${settings_file}.tmp" "$settings_file"

    log_success "Plugin enabled: $plugin_name"
    return 0
}

# Main execution function
main() {
    log "Starting Claude Code marketplace and plugin configuration"

    # Pre-flight checks
    if ! check_claude_cli; then
        log_error "Pre-flight check failed: Claude CLI not available"
        return 1
    fi

    if ! check_network; then
        log_error "Pre-flight check failed: Network connectivity issue"
        return 1
    fi

    # Ensure Claude directories exist
    mkdir -p /config/.claude/plugins/marketplaces
    mkdir -p /config/.claude/plugins/cache

    # Initialize counters
    marketplace_success=0
    marketplace_failed=0
    plugin_success=0
    plugin_failed=0

    # Process marketplaces
    log "Processing CLAUDE_MARKETPLACES environment variable"
    marketplaces=$(parse_env_var "CLAUDE_MARKETPLACES")
    local parse_result=$?
    if [ $parse_result -eq 0 ] && [ -n "$marketplaces" ]; then
        while IFS= read -r marketplace; do
            if [ -n "$marketplace" ]; then
                if add_marketplace_config "$marketplace"; then
                    ((marketplace_success++))
                else
                    ((marketplace_failed++))
                fi
            fi
        done <<< "$marketplaces"
    else
        log "No marketplaces configured"
    fi

    # Process plugins
    log "Processing CLAUDE_PLUGINS environment variable"
    plugins=$(parse_env_var "CLAUDE_PLUGINS")
    parse_result=$?
    if [ $parse_result -eq 0 ] && [ -n "$plugins" ]; then
        while IFS= read -r plugin; do
            if [ -n "$plugin" ]; then
                if enable_plugin "$plugin"; then
                    ((plugin_success++))
                else
                    ((plugin_failed++))
                fi
            fi
        done <<< "$plugins"
    else
        log "No plugins configured"
    fi

    # Final verification and status reporting
    log "Configuration completed:"
    log "- Marketplaces: $marketplace_success successful, $marketplace_failed failed"
    log "- Plugins: $plugin_success successful, $plugin_failed failed"

    # Verify configuration
    if [ -f "/config/.claude/plugins/known_marketplaces.json" ]; then
        log "Marketplace configuration verified"
    fi

    if [ -f "/config/.claude/settings.json" ]; then
        log "Plugin settings verified"
    fi

    # Determine overall success
    if [ $marketplace_failed -eq 0 ] && [ $plugin_failed -eq 0 ]; then
        log_success "All operations completed successfully"
        return 0
    else
        log_error "Some operations failed (marketplaces: $marketplace_failed, plugins: $plugin_failed)"
        return 1
    fi
}

# Execute main function
main "$@"