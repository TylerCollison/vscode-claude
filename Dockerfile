FROM lscr.io/linuxserver/code-server:latest

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    lsb-release \
    jq \
    gettext-base \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Add NodeSource repository for Node.js 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash -

# Install Node.js (which includes npm)
RUN apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code and Claude Code Router
RUN npm install -g @anthropic-ai/claude-code @musistudio/claude-code-router

# Copy ccr-presets to the container
COPY ccr-presets /ccr-presets

# Copy startup scripts to root directory
COPY git-repo-setup.sh /95-git-repo-setup
COPY combine-markdowns.sh /96-combine-markdowns
COPY configure-ccr-settings.sh /97-configure-ccr-settings
COPY configure-claude-permissions.sh /98-configure-claude-permissions
COPY configure-claude-plugins.sh /99-configure-claude-plugins
COPY start-mattermost-bot.sh /100-mattermost-bot

# Copy master startup script to cont-init.d (so it runs automatically)
COPY master-startup.sh /etc/cont-init.d/90-master-startup

# Set execute permissions
RUN chmod +x /95-git-repo-setup \
    /96-combine-markdowns \
    /97-configure-ccr-settings \
    /98-configure-claude-permissions \
    /99-configure-claude-plugins \
    /100-mattermost-bot \
    /etc/cont-init.d/90-master-startup

# Copy Mattermost bot service
COPY mattermost-bot.js /mattermost-bot.js

# Install Node.js dependencies for Mattermost bot securely
RUN mkdir -p /app && npm install --prefix /app --production --no-audit --save-exact ws@8.14.2

# Set NODE_PATH to ensure ws dependency can be found
ENV NODE_PATH=/app/node_modules

# Docker socket volume mount (to be used when running the container)
# This allows Docker commands inside the container to communicate with host Docker daemon
VOLUME /var/run/docker.sock

# Use the standard linuxserver/code-server entrypoint
ENTRYPOINT ["/init"]
