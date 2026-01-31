FROM lscr.io/linuxserver/code-server:latest

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    lsb-release \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Add NodeSource repository for Node.js 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash -

# Install Node.js (which includes npm)
RUN apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code and Claude Code Router
RUN npm install -g @anthropic-ai/claude-code
RUN npm install -g @musistudio/claude-code-router

# Add environment variable definitions
ENV CLAUDE_CODE_PERMISSION_MODE=acceptEdits
ENV CLAUDE_CODE_FULL_PERMISSIONS=0
ENV CLAUDE_CODE_ENABLE_TELEMETRY=0
ENV CLAUDE_CODE_HIDE_ACCOUNT_INFO=1
ENV DISABLE_ERROR_REPORTING=1
ENV DISABLE_TELEMETRY=1
ENV BASH_DEFAULT_TIMEOUT_MS=120000
ENV BASH_MAX_TIMEOUT_MS=300000

# Create startup script
COPY configure-claude-permissions.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/configure-claude-permissions.sh

# Modify entrypoint to run configuration script
ENTRYPOINT ["/init", "configure-claude-permissions.sh", "--"]
