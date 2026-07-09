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
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Add NodeSource repository for Node.js 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash -

# Install Node.js (which includes npm)
RUN apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code, Claude Code Router, and Claude Threads
RUN npm install -g @anthropic-ai/claude-code @musistudio/claude-code-router claude-threads

# Copy ccr-presets to the container
COPY ccr-presets /ccr-presets

# Copy cconx to the container
COPY cconx /cconx

# Copy build-env to the container
COPY build-env /build-env

# Copy claude-threads config to the container
COPY claude-threads /claude-threads

# Install cconx Python package using virtual environment
RUN python3 -m venv /opt/cconx-venv \
    && /opt/cconx-venv/bin/pip install /cconx \
    && ln -sf /opt/cconx-venv/bin/cconx /usr/local/bin/cconx

# Install build-env Python package using virtual environment
RUN python3 -m venv /opt/build-env-venv \
    && /opt/build-env-venv/bin/pip install /build-env \
    && ln -sf /opt/build-env-venv/bin/build-env /usr/local/bin/build-env

# Install LiteLLM along with proxy features
RUN pip install --break-system-packages 'litellm[proxy]'

# Copy LiteLLM config files and custom routing callback
COPY ccr-presets/default/lite-llm-default.yaml /lite-llm/
COPY lite-llm/router_callback.py /lite-llm/
COPY lite-llm/router.json /lite-llm/

# Copy startup scripts to root directory
COPY git-repo-setup.sh /93-git-repo-setup
COPY combine-markdowns.sh /94-combine-markdowns
COPY configure-ccr-settings.sh /95-configure-ccr-settings
COPY start-lite-llm.sh /96-start-lite-llm
COPY configure-claude-permissions.sh /97-configure-claude-permissions
COPY configure-claude-plugins.sh /98-configure-claude-plugins
COPY mattermost-create-channel.sh /99-mattermost-create-channel
COPY configure-threads-settings.sh /100-configure-threads-settings
COPY start-claude-threads.sh /101-start-claude-threads

# Copy master startup script to cont-init.d (so it runs automatically)
COPY master-startup.sh /etc/cont-init.d/90-master-startup

# Set execute permissions
RUN chmod +x /93-git-repo-setup \
    /94-combine-markdowns \
    /95-configure-ccr-settings \
    /96-start-lite-llm \
    /97-configure-claude-permissions \
    /98-configure-claude-plugins \
    /99-mattermost-create-channel \
    /100-configure-threads-settings \
    /101-start-claude-threads \
    /etc/cont-init.d/90-master-startup

# Docker socket volume mount (to be used when running the container)
# This allows Docker commands inside the container to communicate with host Docker daemon
VOLUME /var/run/docker.sock

# Use the standard linuxserver/code-server entrypoint
ENTRYPOINT ["/init"]
