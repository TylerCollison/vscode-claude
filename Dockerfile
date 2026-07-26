FROM lscr.io/linuxserver/code-server:latest

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

# Configure Happier default environment variables
ENV HAPPIER_CACHE_DIR=/config/.cache

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
WORKDIR /config

# Configure persistent internal paths
# HOME must be writable; the runner resolves $HOME/.cache by default
RUN mkdir -p /config/.npm /config/.cache /config/.happy

# Install the happier-server runner (provides happier-server on PATH)
RUN npm install -g @happier-dev/relay-server@dev

# Install the Happier CLI (provides happier, happier daemon, auth, etc.)
RUN npm install -g @happier-dev/cli@dev

# Pre-download the server binary and UI web bundle.
# The runner downloads + extracts both to the cache dir, then spawns the server.
# We timeout after 2 min — the binary and UI persist in cache even though
# the server is killed (it cannot fully initialise without a database yet).
RUN timeout 120 happier-server --ui > /dev/null 2>&1; \
    echo "Pre-download attempt done"

# Copy the Prisma SQLite migration files from the extracted binary
# to a stable path in the data dir.  This allows auto-migrate to work
# at every container start without needing network access or the
# exact cache path (which contains a version tag).
RUN HAPPIER_CACHE_DIR="/config/.cache" && \
    MIGRATIONS_SRC=$(find "$HAPPIER_CACHE_DIR/happier/server" -path "*/prisma/sqlite/migrations" -type d 2>/dev/null | head -1) && \
    if [ -n "$MIGRATIONS_SRC" ] && [ -d "$MIGRATIONS_SRC" ]; then \
      mkdir -p /config/.happy/server-light/migrations && \
      cp -r "$MIGRATIONS_SRC" /config/.happy/server-light/migrations/sqlite && \
      echo "Migrations pre-copied ($(find "$MIGRATIONS_SRC" -type f | wc -l) files)"; \
    else \
      echo "WARNING: migrations not found in cache, auto-migrate will require fallback at runtime"; \
    fi

# Remove any SQLite database created during build — each container
# initialises its own database on first start via auto-migrate.
RUN rm -f /config/.happy/server-light/happier-server-light.sqlite

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
COPY happier-tls-tunnel.js /config/happier-tls-tunnel.js

# Copy master startup script to cont-init.d (so it runs automatically)
COPY master-startup.sh /etc/cont-init.d/90-master-startup

# Copy litellm-health-check script to bin
COPY litellm-health-check.py /usr/local/bin/litellm-health-check

# Set execute permissions
RUN chmod +x /93-git-repo-setup \
    /usr/local/bin/litellm-health-check \
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
