#!/bin/bash
# Legacy wrapper script - now handled by pre-start hooks
# This is kept for backward compatibility but should not be used as main process

echo "Warning: startup-wrapper.sh should not be used as main process"
echo "Claude permissions are now configured via /etc/cont-init.d/ hooks"

# For backward compatibility, run permissions setup if needed
if [ -f "/etc/cont-init.d/99-configure-claude-permissions" ]; then
    /etc/cont-init.d/99-configure-claude-permissions
fi

# If this script is executed, just exit - let /init handle the main process
exit 0