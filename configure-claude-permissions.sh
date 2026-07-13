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
  "skipDangerousModePermissionPrompt": true,
  "permissions": {
    "defaultMode": "$CLAUDE_MODE"
  }
}
EOF

# Ensure config folder is owned by the abc user (PUID/PGID) for non-root access
lsiown -R abc:abc /config