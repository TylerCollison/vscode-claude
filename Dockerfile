# ── Stage: build bead-me-up-scotty (Beads web UI) ────────────────────────────
# Next.js 16 standalone server that shells out to the `bd` CLI. Built in an
# Alpine stage (matching the upstream project's own Dockerfile), then the
# standalone output is copied into the final image. Pinned to a commit SHA
# for reproducible builds.
FROM node:26.4.0-alpine AS scotty-builder
ARG SCOTTY_COMMIT=e26e446cba697a522ecceabdeeb11dc99239a071
RUN apk add --no-cache git
WORKDIR /scotty
RUN git clone https://github.com/brendan-appstart/bead-me-up-scotty.git . \
    && git checkout "${SCOTTY_COMMIT}"
RUN npm ci
# Standalone output is opt-in (see next.config.ts); local `next start` flows
# keep the default output.
ENV NEXT_STANDALONE=1
RUN npm run build

# ── Stage: full eleventy tree for the showcase publisher ─────────────────────
# The app locates node_modules/@11ty/eleventy/cmd.cjs by scanning the
# filesystem — it is deliberately never imported, so Next's standalone output
# tracing only includes a PARTIAL copy. Install the full tree here and copy it
# into the final image (see the rm+COPY below). Keep in sync with package.json.
FROM node:26.4.0-alpine AS scotty-eleventy
WORKDIR /eleventy
RUN npm install --no-save @11ty/eleventy@3.1.6

FROM lscr.io/linuxserver/code-server:latest

# Enable Docker BuildKit for faster builds
ENV DOCKER_BUILDKIT=1

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
# Add /usr/local/bin to PYTHONPATH so dispatch_utils can be imported
ENV PYTHONPATH=/usr/local/bin:$PYTHONPATH

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    ca-certificates \
    gnupg \
    lsb-release \
    jq \
    gettext-base \
    docker.io \
    docker-compose-v2 \
    docker-buildx \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*
RUN ln -s /usr/libexec/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose

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

# Install GitLab CLI (glab) — download the binary directly from GitLab releases
# since packages.gitlab.com doesn't support Ubuntu Noble (24.04) yet.
# When bumping, check https://gitlab.com/gitlab-org/cli/-/releases for new releases.
RUN GLAB_VERSION="v1.110.0" && \
    curl -fsSL "https://gitlab.com/gitlab-org/cli/-/releases/${GLAB_VERSION}/downloads/glab_${GLAB_VERSION#v}_linux_amd64.tar.gz" \
    | tar -xz -C /usr/local/bin --strip-components=1 bin/glab

# Install Claude Code and Claude Threads
RUN npm install -g @anthropic-ai/claude-code claude-threads

# Configure persistent internal paths
# HOME must be writable; the runner resolves $HOME/.cache by default
#RUN mkdir -p /config/.npm /config/.cache /config/.happy

# Install the happier-server runner (provides happier-server on PATH)
RUN npm install -g @happier-dev/relay-server@dev

# Install the Happier CLI (provides happier, happier daemon, auth, etc.)
RUN npm install -g @happier-dev/cli@dev

# Install Beads — distributed graph issue tracker for AI agents
# Uses the official install script which handles checksum verification,
# platform detection, and places the binary in /usr/local/bin.
RUN curl -fsSL https://raw.githubusercontent.com/gastownhall/beads/main/scripts/install.sh | bash

# Strip unused platform-specific binaries from happier CLI dependencies
# — macOS/Windows binaries are not needed in this Linux container
# — ONNX CUDA/TensorRT providers are not needed for CPU-only workloads
# (Linux arm architectures are kept for future compatibility)
RUN rm -rf \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/@anthropic-ai/claude-agent-sdk-darwin-* \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/@anthropic-ai/claude-agent-sdk-win32-* \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/onnxruntime-node/bin/napi-v3/darwin \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/onnxruntime-node/bin/napi-v3/win32 \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/@img/sharp-win32-* \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/@img/sharp-libvips-darwin-* \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/@img/sharp-libvips-win32-* \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/node-pty/prebuilds/darwin-* \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/node-pty/prebuilds/win32-* \
    && rm -f \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/onnxruntime-node/bin/napi-v3/linux/x64/libonnxruntime_providers_cuda.so \
    /usr/lib/node_modules/@happier-dev/cli/node_modules/onnxruntime-node/bin/napi-v3/linux/x64/libonnxruntime_providers_tensorrt.so

# Pre-cache the happier-server binary (downloaded by the runner) and extract
# the Prisma SQLite migration files so auto-migrate works on first container
# start without needing network access.
# We timeout after 2 minutes — the binary persists in cache even though
# the server is killed (it cannot initialise fully without a database yet).
# All /config files are chowned (using the default linuxserver PUID=911,
# PGID=911) in this same layer so no overlay2 copy-up is triggered at
# runtime — at runtime these files are already owned by 911:911.
RUN timeout 120 happier-server --ui > /dev/null 2>&1 || true; \
    HAPPIER_CACHE_DIR="/config/.cache" && \
    MIGRATIONS_SRC=$(find "$HAPPIER_CACHE_DIR/happier/server" -path "*/prisma/sqlite/migrations" -type d -print -quit 2>/dev/null || true) && \
    if [ -n "$MIGRATIONS_SRC" ] && [ -d "$MIGRATIONS_SRC" ]; then \
      mkdir -p /config/.happy/server-light/migrations && \
      cp -r "$MIGRATIONS_SRC" /config/.happy/server-light/migrations/sqlite && \
      echo "Migrations copied from $MIGRATIONS_SRC to /config/.happy/server-light/migrations/sqlite"; \
    else \
      echo "No SQLite migrations found in cache — flyway migration path needed?"; \
    fi && \
    rm -f /config/.happy/server-light/happier-server-light.sqlite && \
    # Use numeric IDs matching the linuxserver default PUID/PGID (911:911).
    # The base image defines abc with gid=1001, but at runtime the init
    # system sets abc's group to PGID (default 911). Using the runtime ID
    # here avoids overlay2 copy-up when the runtime chown runs.
    chown -R 911:911 /config && \
    echo "Pre-download attempt done"

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

# Install the Beads web UI (bead-me-up-scotty) — standalone Next.js server
# that shells out to the `bd` CLI. Runs as abc on /opt/bead-me-up-scotty.
COPY --from=scotty-builder /scotty/.next/standalone /opt/bead-me-up-scotty
COPY --from=scotty-builder /scotty/.next/static /opt/bead-me-up-scotty/.next/static
COPY --from=scotty-builder /scotty/public /opt/bead-me-up-scotty/public
# Drop the partial @11ty/eleventy that Next's tracing put into standalone (it
# would shadow the complete tree below), then provide the full eleventy install
# at /node_modules where the app's upward filesystem search can find it.
RUN rm -rf /opt/bead-me-up-scotty/node_modules/@11ty
COPY --from=scotty-eleventy /eleventy/node_modules /node_modules

# Copy startup scripts to root directory
COPY configure-code-server-theme.sh /92-configure-code-server-theme
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
COPY configure-buildx.sh /103-configure-buildx
COPY configure-beads.sh /104-configure-beads
COPY start-scotty.sh /105-start-scotty
COPY start-beads-dispatch.sh /106-start-beads-dispatch
COPY start-beads-sync.sh /107-start-beads-sync
COPY start-prompt-session.sh /108-start-prompt-session
COPY start-mr-pr-sync.sh /109-start-mr-pr-sync
COPY start-mr-pr-dispatch.sh /110-start-mr-pr-dispatch
COPY happier-tls-tunnel.js /app/happier-tls-tunnel.js

# Install the Beads dispatch watcher (dispatches a worker container/service when a task becomes ready)
COPY beads-dispatch/beads_dispatch.py /usr/local/bin/beads-dispatch
COPY beads-dispatch/dispatch_utils.py /usr/local/bin/dispatch_utils.py

# Install the MR/PR responder dispatcher
COPY mr_pr_dispatch.py /usr/local/bin/mr_pr_dispatch.py

# Copy master startup script to cont-init.d (so it runs automatically)
COPY master-startup.sh /etc/cont-init.d/90-master-startup

# Copy litellm-health-check script to bin
COPY litellm-health-check.py /usr/local/bin/litellm-health-check

# Set execute permissions
RUN chmod +x /92-configure-code-server-theme \
    /93-git-repo-setup \
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
    /103-configure-buildx \
    /104-configure-beads \
    /105-start-scotty \
    /106-start-beads-dispatch \
    /107-start-beads-sync \
    /109-start-mr-pr-sync \
    /110-start-mr-pr-dispatch \
    /108-start-prompt-session \
    /usr/local/bin/beads-dispatch \
    /usr/local/bin/dispatch_utils.py \
    /usr/local/bin/mr_pr_dispatch.py

# Remove build toolchain packages no longer needed at runtime
# (gcc, g++, binutils, and their dev headers were only needed to compile
# native npm addons like node-pty, sharp, and onnxruntime at install time)
RUN apt-get purge -y \
    gcc-13-x86-64-linux-gnu g++-13-x86-64-linux-gnu cpp-13-x86-64-linux-gnu \
    gcc-13 g++-13 cpp-13 \
    build-essential \
    libstdc++-13-dev libgcc-13-dev libc6-dev linux-libc-dev \
    binutils-x86-64-linux-gnu binutils-common libbinutils \
    && apt-get autoremove --purge -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /usr/lib/gcc

# Docker socket volume mount (to be used when running the container)
# This allows Docker commands inside the container to communicate with host Docker daemon
VOLUME /var/run/docker.sock

# Use the standard linuxserver/code-server entrypoint
ENTRYPOINT ["/init"]
