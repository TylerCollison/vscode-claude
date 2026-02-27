#!/bin/bash
# Test script for Mattermost bot integration

set -euo pipefail

echo "Testing Mattermost bot integration..."

# Test 1: Check if bot service file exists
if [ -f "/workspace/mattermost-bot.js" ]; then
    echo "✓ Mattermost bot service file exists"
else
    echo "✗ Mattermost bot service file missing"
    exit 1
fi

# Test 2: Check if startup script exists
if [ -f "/workspace/start-mattermost-bot.sh" ]; then
    echo "✓ Mattermost bot startup script exists"
else
    echo "✗ Mattermost bot startup script missing"
    exit 1
fi

# Test 3: Verify Node.js syntax
if node -c /workspace/mattermost-bot.js; then
    echo "✓ Mattermost bot service syntax valid"
else
    echo "✗ Mattermost bot service syntax invalid"
    exit 1
fi

# Test 4: Verify bash script syntax
if bash -n /workspace/start-mattermost-bot.sh; then
    echo "✓ Mattermost bot startup script syntax valid"
else
    echo "✗ Mattermost bot startup script syntax invalid"
    exit 1
fi

echo "All basic tests passed!"