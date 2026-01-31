#!/bin/bash
# Wrapper script to configure Claude permissions and then start VS Code server

# Configure Claude Code permissions
/usr/local/bin/configure-claude-permissions.sh

# Check if the original command is provided
if [ $# -eq 0 ]; then
    # No command provided, use default code-server startup
    echo "Starting VS Code server with default configuration..."

    # Use password authentication if PASSWORD is set, otherwise use none
    if [ -n "$PASSWORD" ] || [ -n "$HASHED_PASSWORD" ]; then
        exec code-server --bind-addr 0.0.0.0:8443 --auth password
    else
        exec code-server --bind-addr 0.0.0.0:8443 --auth none
    fi
else
    # Execute the original command (preserving the linuxserver/code-server behavior)
    echo "Executing provided command: $@"
    exec "$@"
fi