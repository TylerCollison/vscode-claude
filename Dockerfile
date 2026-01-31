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

# Create startup script for pre-start hook
COPY configure-claude-permissions.sh /etc/cont-init.d/99-configure-claude-permissions
RUN chmod +x /etc/cont-init.d/99-configure-claude-permissions

# Use the standard linuxserver/code-server entrypoint
ENTRYPOINT ["/init"]
