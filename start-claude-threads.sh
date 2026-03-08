#!/usr/bin/with-contenv bash

# Determine whether Claude Threads is enabled
if [[ "$ENABLE_THREADS" != "true" ]]; then
    echo "Claude Threads Disabled"
    exit 0
else
    echo "Claude Threads Enabled"
fi

echo "Setting up Claude Threads server..."

# Use a Claude Code Router profile if set
if [[ -v CCR_PROFILE ]]; then
    # Copy the Claude Code Router Threads profile to the config for environment activation
    echo "Applying Claude Code Router Threads Profile"
    cp /config/.claude-code-router/presets/${CCR_PROFILE}/manifest.json /config/.claude-code-router/config.json

    # Restart Claude Code Router to apply configuration update
    ccr restart

    # Activate Claude Code Router environment
    echo "Activating Claude Code Router Environment"
    eval "$(ccr activate)"
fi

# Run Claude Threads server in the background
echo "Starting Claude Threads Server"
cd ${DEFAULT_WORKSPACE}
claude-threads