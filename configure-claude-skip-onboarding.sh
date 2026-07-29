#!/usr/bin/with-contenv bash
# Configure Claude Code to skip onboarding

WORKSPACE="${DEFAULT_WORKSPACE:-/workspace}"

# Generate .claude.json that skips onboarding
cat > /config/.claude.json << EOF
{
  "hasCompletedOnboarding": true,
  "projects": {
    "$WORKSPACE": {
      "hasTrustDialogAccepted": true,
      "projectOnboardingSeenCount": 0,
      "hasCompletedProjectOnboarding": true
    }
  }
}
EOF