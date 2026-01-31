#!/bin/bash
# Configure Claude Code permissions based on environment variables

# Create Claude Code settings directory
mkdir -p /config/.claude

# Generate settings.json based on environment variables
# Merge with existing settings if they exist
if [ -f /config/.claude/settings.json ]; then
    # Use jq to merge settings if available
    if command -v jq >/dev/null 2>&1; then
        jq --arg mode "${CLAUDE_CODE_PERMISSION_MODE:-acceptEdits}" '
        .permissions.defaultMode = $mode |
        .permissions.allow = (["Bash(npm run *)", "Bash(git commit *)"] + (.permissions.allow // [])) |
        .permissions.deny = (["Bash(curl *)", "Read(./.env)", "Read(./secrets/**)"] + (.permissions.deny // [])) |
        .permissions.ask = (["Bash(git push *)"] + (.permissions.ask // []))
        ' /config/.claude/settings.json > /config/.claude/settings.json.tmp && mv /config/.claude/settings.json.tmp /config/.claude/settings.json
    else
        # Fallback to basic JSON generation if jq is not available
        cat > /config/.claude/settings.json << EOF
{
  "permissions": {
    "defaultMode": "${CLAUDE_CODE_PERMISSION_MODE:-acceptEdits}",
    "allow": ["Bash(npm run *)", "Bash(git commit *)"],
    "deny": ["Bash(curl *)", "Read(./.env)", "Read(./secrets/**)"],
    "ask": ["Bash(git push *)"]
  }
}
EOF
    fi
else
    # Create new settings file
    cat > /config/.claude/settings.json << EOF
{
  "permissions": {
    "defaultMode": "${CLAUDE_CODE_PERMISSION_MODE:-acceptEdits}",
    "allow": ["Bash(npm run *)", "Bash(git commit *)"],
    "deny": ["Bash(curl *)", "Read(./.env)", "Read(./secrets/**)"],
    "ask": ["Bash(git push *)"]
  }
}
EOF
fi

# If full permissions enabled, create CLI wrapper
if [ "$CLAUDE_CODE_FULL_PERMISSIONS" = "1" ]; then
    # Create alias or wrapper script for full permissions mode
    cat > /usr/local/bin/claude-full << 'EOF'
#!/bin/bash
claude --dangerously-skip-permissions "$@"
EOF
    chmod +x /usr/local/bin/claude-full
fi

# This script runs as a pre-start hook, no need to exec commands