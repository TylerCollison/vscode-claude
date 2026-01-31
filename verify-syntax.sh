#!/bin/bash
# Syntax verification script for the Docker setup

echo "🔍 Verifying Dockerfile syntax..."
if grep -q "ENTRYPOINT \[\"/init\"\]" Dockerfile && grep -q "CMD \[\"startup-wrapper.sh\"\]" Dockerfile; then
    echo "✅ Dockerfile entrypoint and command are correctly configured"
else
    echo "❌ Dockerfile entrypoint/command configuration issue"
    exit 1
fi

echo "🔍 Verifying wrapper script exists..."
if [ -f "startup-wrapper.sh" ] && [ -x "startup-wrapper.sh" ]; then
    echo "✅ Wrapper script exists and is executable"
else
    echo "❌ Wrapper script missing or not executable"
    exit 1
fi

echo "🔍 Verifying wrapper script content..."
if grep -q "configure-claude-permissions.sh" startup-wrapper.sh && grep -q "code-server" startup-wrapper.sh; then
    echo "✅ Wrapper script contains required components"
else
    echo "❌ Wrapper script missing required content"
    exit 1
fi

echo "🔍 Verifying permissions script exists..."
if [ -f "configure-claude-permissions.sh" ] && [ -x "configure-claude-permissions.sh" ]; then
    echo "✅ Permissions script exists and is executable"
else
    echo "❌ Permissions script missing or not executable"
    exit 1
fi

echo "🔍 Verifying docker-compose file exists..."
if [ -f "docker-compose.yml" ]; then
    echo "✅ Docker compose file exists"
else
    echo "❌ Docker compose file missing"
    exit 1
fi

echo "🔍 Verifying test script exists..."
if [ -f "test-container.sh" ] && [ -x "test-container.sh" ]; then
    echo "✅ Test script exists and is executable"
else
    echo "❌ Test script missing or not executable"
    exit 1
fi

echo "🎉 All syntax checks passed! The configuration should resolve the VS Code server connection issue."
echo ""
echo "To test locally:"
echo "1. docker build -t vscode-claude-test ."
echo "2. ./test-container.sh"
echo "3. Check that port 8443 is listening and accessible"