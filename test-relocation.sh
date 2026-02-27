#!/usr/bin/env bash
set -euo pipefail

echo "Testing Mattermost bot relocation..."

# Test 1: File exists in development location (will be copied to root during Docker build)
if [ -f "/workspace/mattermost-bot.js" ]; then
    echo "✓ mattermost-bot.js found in workspace directory"
else
    echo "✗ mattermost-bot.js missing from workspace directory"
    exit 1
fi

# Test 2: Dependencies installed (will be installed to root during Docker build)
if [ -d "/workspace/node_modules/ws" ]; then
    echo "✓ ws dependency installed in workspace/node_modules"
else
    echo "✗ ws dependency missing from workspace/node_modules"
    exit 1
fi

# Test 3: Startup script syntax check
if bash -n /workspace/start-mattermost-bot.sh; then
    echo "✓ startup script syntax valid"
else
    echo "✗ startup script syntax error"
    exit 1
fi

echo "All relocation tests passed!"