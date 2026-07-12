#!/usr/bin/with-contenv bash

# Determine whether Claude Threads is enabled
if [[ "$ENABLE_THREADS" != "true" ]]; then
    echo "Claude Threads Disabled"
    exit 0
else
    echo "Claude Threads Enabled"
fi

echo "Setting up Claude Threads server..."

# Run Claude Threads server in the background
echo "Starting Claude Threads Server"
cd ${DEFAULT_WORKSPACE}
claude-threads