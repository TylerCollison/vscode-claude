#!/usr/bin/with-contenv bash
# Configure Claude Code to skip onboarding

# Generate .claude.json that skips onboarding
cat > /config/.claude.json << EOF
{
  "hasCompletedOnboarding": true
}
EOF

# Ensure config folder is owned by the abc user (PUID/PGID) for non-root access
lsiown -R abc:abc /config