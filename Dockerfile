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

# Install Claude Code and Claude Threads
RUN npm install -g @anthropic-ai/claude-code claude-threads

# Install Happier
WORKDIR /app

# Configure persistent internal paths for the cache and UI
ENV HOME=/app
ENV HAPPIER_SERVER_CACHE_DIR=/app/.cache/happier
ENV HAPPIER_SERVER_UI_DIR=/app/.cache/happier_ui
RUN mkdir -p /app/.npm ${HAPPIER_SERVER_CACHE_DIR} ${HAPPIER_SERVER_UI_DIR}
RUN npx --yes --package @happier-dev/relay-server happier-server --ui --help

# Configure Claude Code default environment variables
ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"
ENV CLAUDE_CODE_ENABLE_AWAY_SUMMARY="0"
ENV IS_SANDBOX="1"
ENV ANTHROPIC_BASE_URL="http://127.0.0.1:5090"
ENV ANTHROPIC_AUTH_TOKEN="bypass_token"
ENV ANTHROPIC_DEFAULT_OPUS_MODEL="lite-llm/router"
ENV ANTHROPIC_DEFAULT_SONNET_MODEL="lite-llm/router"
ENV ANTHROPIC_DEFAULT_HAIKU_MODEL="lite-llm/router"
ENV CLAUDE_CODE_SUBAGENT_MODEL="lite-llm/router"

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
RUN pip install --break-system-packages 'litellm[proxy]' 'semantic-router'

# Copy LiteLLM config files and custom routing callback
COPY lite-llm/ /lite-llm/

# Copy startup scripts to root directory
COPY git-repo-setup.sh /93-git-repo-setup
COPY combine-markdowns.sh /94-combine-markdowns
COPY configure-claude-skip-onboarding.sh /95-configure-claude-skip-onboarding
COPY start-lite-llm.sh /96-start-lite-llm
COPY configure-claude-permissions.sh /97-configure-claude-permissions
COPY configure-claude-plugins.sh /98-configure-claude-plugins
COPY mattermost-create-channel.sh /99-mattermost-create-channel
COPY configure-threads-settings.sh /100-configure-threads-settings
COPY start-claude-threads.sh /101-start-claude-threads
COPY start-happier.sh /102-start-happier

# Copy master startup script to cont-init.d (so it runs automatically)
COPY master-startup.sh /etc/cont-init.d/90-master-startup

# Set execute permissions
RUN chmod +x /93-git-repo-setup \
    /94-combine-markdowns \
    /95-configure-claude-skip-onboarding \
    /96-start-lite-llm \
    /97-configure-claude-permissions \
    /98-configure-claude-plugins \
    /99-mattermost-create-channel \
    /100-configure-threads-settings \
    /101-start-claude-threads \
    /102-start-happier \
    /etc/cont-init.d/90-master-startup

# Docker socket volume mount (to be used when running the container)
# This allows Docker commands inside the container to communicate with host Docker daemon
VOLUME /var/run/docker.sock

# Use the standard linuxserver/code-server entrypoint
ENTRYPOINT ["/init"]
