FROM lscr.io/linuxserver/code-server:latest

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    lsb-release \
    jq \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI tools
RUN apt-get update && apt-get install -y \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Add NodeSource repository for Node.js 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash -

# Install Node.js (which includes npm)
RUN apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code and Claude Code Router
RUN npm install -g @anthropic-ai/claude-code
RUN npm install -g @musistudio/claude-code-router

# Copy ccr-presets to the container
COPY ccr-presets /ccr-presets

# Create startup script for pre-start hook
COPY 94-mattermost-notification.sh /etc/cont-init.d/94-mattermost-notification
COPY git-repo-setup.sh /etc/cont-init.d/95-git-repo-setup
COPY combine-markdowns.sh /etc/cont-init.d/96-combine-markdowns
COPY configure-ccr-settings.sh /etc/cont-init.d/97-configure-ccr-settings
COPY configure-claude-permissions.sh /etc/cont-init.d/98-configure-claude-permissions
COPY configure-claude-plugins.sh /etc/cont-init.d/99-configure-claude-plugins
RUN chmod +x /etc/cont-init.d/94-mattermost-notification
RUN chmod +x /etc/cont-init.d/95-git-repo-setup
RUN chmod +x /etc/cont-init.d/96-combine-markdowns
RUN chmod +x /etc/cont-init.d/97-configure-ccr-settings
RUN chmod +x /etc/cont-init.d/98-configure-claude-permissions
RUN chmod +x /etc/cont-init.d/99-configure-claude-plugins

# Docker socket volume mount (to be used when running the container)
# This allows Docker commands inside the container to communicate with host Docker daemon
VOLUME /var/run/docker.sock

# Use the standard linuxserver/code-server entrypoint
ENTRYPOINT ["/init"]
