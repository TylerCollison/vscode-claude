#!/usr/bin/with-contenv bash
# Configure Claude Code permissions based on environment variables

# Explicitly handle environment variables with fallbacks
CLAUDE_MODE="${CLAUDE_CODE_PERMISSION_MODE:-acceptEdits}"

# Debug: log environment variable status
echo "Claude configuration:"
echo "  MODE: $CLAUDE_MODE"

# Create Claude Code settings directory
mkdir -p /config/.claude

# Generate settings.json based on environment variables
# Create new settings file
cat > /config/.claude/settings.json << EOF
{
  "permissions": {
    "defaultMode": "$CLAUDE_MODE"
  }
}
EOF

# Grant open permissions for the config folder
chmod -R 777 /config

# This script runs as a pre-start hook, no need to exec commands