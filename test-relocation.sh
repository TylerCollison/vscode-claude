#!/usr/bin/env bash
set -euo pipefail

echo "Testing Mattermost bot relocation configuration..."

# Test 1: Verify Dockerfile has correct relocation paths
echo "Checking Dockerfile configuration..."
if grep -q "COPY mattermost-bot.js /mattermost-bot.js" /workspace/Dockerfile; then
    echo "✓ Dockerfile copies to correct root location"
else
    echo "✗ Dockerfile missing correct copy destination"
    exit 1
fi

if grep -q "npm install --prefix /" /workspace/Dockerfile; then
    echo "✓ Dockerfile installs dependencies to root"
else
    echo "✗ Dockerfile missing correct npm install prefix"
    exit 1
fi

# Test 2: Verify startup script uses correct paths
echo "Checking startup script configuration..."
if grep -q "node /mattermost-bot.js" /workspace/start-mattermost-bot.sh; then
    echo "✓ Startup script uses root bot path"
else
    echo "✗ Startup script missing correct bot path"
    exit 1
fi

if grep -q "DEFAULT_WORKSPACE" /workspace/start-mattermost-bot.sh; then
    echo "✓ Startup script handles DEFAULT_WORKSPACE"
else
    echo "✗ Startup script missing DEFAULT_WORKSPACE handling"
    exit 1
fi

# Test 3: Verify bot code is ready for relocation
echo "Checking bot code compatibility..."
if ! grep -q "/workspace/mattermost-bot.js" /workspace/mattermost-bot.js; then
    echo "✓ Bot code has no hardcoded workspace paths"
else
    echo "✗ Bot code contains workspace-specific paths"
    exit 1
fi

if grep -q "require('ws')" /workspace/mattermost-bot.js; then
    echo "✓ Bot code uses correct ws dependency loading"
else
    echo "✗ Bot code missing correct dependency loading"
    exit 1
fi

# Test 4: Verify startup script syntax
if bash -n /workspace/start-mattermost-bot.sh; then
    echo "✓ Startup script syntax valid"
else
    echo "✗ Startup script syntax error"
    exit 1
fi

echo ""
echo "All relocation configuration tests passed!"
echo "The implementation is ready for Docker build and relocation."