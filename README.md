# ClaudeConX

A Docker image providing a complete web-based development environment for Claude Code, built on top of the excellent [linuxserver/code-server](https://hub.docker.com/r/linuxserver/code-server) image.

## Overview

This Docker image bundles a web-based IDE (VS Code Server), Claude Code, a LiteLLM-powered model router, and Claude Threads into a comprehensive development environment accessible from any web browser and Mattermost client. Perfect for developers who want a self-contained, and highly flexible Claude Code workspace.

## What's Included

### Core Components

- **VS Code Server** - Full-featured VS Code running in your browser
  - Based on [linuxserver/code-server](https://hub.docker.com/r/linuxserver/code-server)
  - Complete VS Code experience with extensions, terminal, and debugging
  - Responsive design supporting mobile, tablet, and desktop screens

- **Claude Code** - Anthropic's agentic coding tool
  - [Claude Code Documentation](https://code.claude.com/docs/en/overview)
  - AI-powered code generation, debugging, and automation
  - Direct terminal integration for seamless development workflows

- **LiteLLM Router** - Advanced model routing and provider proxy
  - [LiteLLM Documentation](https://docs.litellm.ai)
  - Multi-provider support (Google AI Studio, NVIDIA NIM, Mistral, OpenCode Zen, Cerebras, EXA AI)
  - Content-aware routing (images → vision model, web search → search-capable model, complexity-based tiering)
  - Automatically routes requests to a curated collection of the most capable free models available based on API keys set (see "LiteLLM Router Configuration")
  - Fallback chains to overcome server side errors, availability, and rate limits

- **Claude Threads** - Real-time chat integration for Mattermost
  - [GitHub Repository](https://github.com/anneschuth/claude-threads)
  - WebSocket-based bidirectional communication
  - Multi-platform support (Mattermost)

### Development Tools

- **cconx** - ClaudeConX Docker Management Tool
  - Command-line interface for managing ClaudeConX instances
  - Instance lifecycle management (start, stop, delete, status)
  - DNS and network configuration
  - Environment variable management with append/override logic

- **build-env** - Persistent Build Environment Manager
  - Creates and manages persistent Docker containers for build commands
  - Bidirectional file synchronization between host and container
  - Environment isolation with dedicated containers per workspace
  - Smart conflict resolution using modification timestamps

- **Beads** - Distributed Graph Issue Tracker for AI Agents
  - [GitHub Repository](https://github.com/gastownhall/beads)
  - Persistent, dependency-aware memory system for coding agents
  - Replaces markdown TODO lists with a version-controlled graph database
  - Powered by Dolt (Git for data) for version control and branching
  - Enables long-horizon tasks without context loss
  - Run `bd init` in your workspace to initialize (or set `BEADS_ENABLED=true`)

- **Scotty (Bead UI)** - Web UI for the Beads issue tracker
  - [GitHub Repository](https://github.com/brendan-appstart/bead-me-up-scotty)
  - Five-column board (Backlog · Ready · In Progress · Blocked · Done) with drag-and-drop
  - Epics with progress bars, dependency graph, comments, and create/edit
  - Built-in as a standalone Next.js server; enable with `ENABLE_SCOTTY=true`
  - Available at `http://localhost:3000` (configurable via `SCOTTY_PORT`)

### Development Stack

- **Node.js 22** - Latest LTS version with npm package manager
- **Full Linux development environment** - Based on Ubuntu with common development tools
- **Web-based terminal** - Integrated terminal access within VS Code
- **Docker-in-Docker support** - Run Docker commands from within the container

## Quick Start

```bash
# Run the container
docker run -d \
  --name=claude-dev \
  -e PUID=1000 \
  -e PGID=1000 \
  -e TZ=Etc/UTC \
  -e SUDO_PASSWORD=password \
  -e DEFAULT_WORKSPACE=/workspace \
  -e PWA_APPNAME=code-server \
  -e NIM_API_KEY=your-nvidia-nim-api-key \
  -e GOOGLE_API_KEY=your-google-ai-studio-api-key \
  -e MISTRAL_API_KEY=your-mistral-api-key \
  -e CEREBRAS_API_KEY=your-cerebras-api-key \
  -e OPENCODE_ZEN_API_KEY=your-opencode-zen-api-key \
  -e EXA_API_KEY=your-exa-api-key \
  -p 8443:8443 \
  -p 3005:3005 \
  -p 4000:4000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /path/to/your/code:/workspace \
  --restart unless-stopped \
  tylercollison2089/vscode-claude

# Access at http://localhost:8443
```

## Environment Variables Reference

This container supports extensive configuration through environment variables.

### Container Configuration
| Variable | Description |
|----------|-------------|
| `PUID` | User ID for container processes |
| `PGID` | Group ID for container processes |
| `TZ` | Timezone configuration |
| `PROXY_DOMAIN` | Reverse proxy domain for external access |
| `DEFAULT_WORKSPACE` | Default workspace directory |
| `PWA_APPNAME` | Progressive Web App name |
| `VSCODE_THEME` | Default VS Code color theme (e.g., `Dark Modern`, `Monokai`) |

### Authentication & Access Control
| Variable | Description |
|----------|-------------|
| `PASSWORD` | Plaintext password for VS Code web interface |
| `HASHED_PASSWORD` | Argon2id-hashed password |
| `SUDO_PASSWORD` | Plaintext sudo password |
| `SUDO_PASSWORD_HASH` | Hashed sudo password |

### Claude Code Configuration
| Variable | Description |
|----------|-------------|
| `CLAUDE_CODE_PERMISSION_MODE` | Permission mode (`acceptEdits`, `bypassPermissions`, `default`, `plan`, `dontAsk`) |
| `CLAUDE_MARKETPLACES` | Comma-separated list of plugin marketplaces |
| `CLAUDE_PLUGINS` | Comma-separated list of plugins to install |

### LiteLLM Router Configuration
| Variable | Description |
|----------|-------------|
| `NIM_API_KEY` | Nvidia NIM API key (enables Nvidia NIM models, if set) |
| `GOOGLE_API_KEY` | Google AI Studio API key (enables Google AI Studio models, if set)  |
| `MISTRAL_API_KEY` | Mistral AI API key (enables Mistral models, if set)  |
| `CEREBRAS_API_KEY` | Cerebras API key (enables Cerebras models, if set)  |
| `OPENCODE_ZEN_API_KEY` | OpenCode Zen API key (enables OpenCode Zen models, if set)  |
| `EXA_API_KEY` | EXA AI web search API key (enables EXA AI web search, if set)  |

Claude Code is pre-configured to route all requests through the LiteLLM proxy at `http://127.0.0.1:5090`. The router automatically selects models based on request content:

| Model Group | Purpose | Default Provider |
|-------------|---------|-----------------|
| `lite-llm/router` | Main entry point — multi-stage routing pipeline | Auto-routed |
| `lite-llm/default` | Standard chat and coding tasks | OpenCode Zen  (DeepSeek v4 Flash) |
| `lite-llm/think` | Complex reasoning and deep analysis | NVIDIA NIM  (DeepSeek v4 Pro) |
| `lite-llm/webSearch` | Queries requiring web search | Google AI Studio (Gemini 3.5 Flash) |
| `lite-llm/image` | Image analysis and vision tasks | Google AI Studio (Gemini 3.5 Flash) |
| `lite-llm/longContext` | Long-context tasks | NVIDIA NIM (DeepSeek v4 Pro) |

### Claude Threads Configuration
| Variable | Description |
|----------|-------------|
| `ENABLE_THREADS` | Enable Claude Threads server |
| `MM_ADDRESS` | Mattermost server URL |
| `MM_TOKEN` | Mattermost bot authentication token |
| `MM_CHANNEL` | Target channel for this container to use |
| `MM_TEAM` | Mattermost team name (must exist in Mattermost) |
| `MM_BOT_NAME` | Bot display name (must match Mattermost configuration) |
| `THREADS_CHROME` | Chrome executable path |
| `THREADS_WORKTREE_MODE` | Git worktree mode |
| `THREADS_SKIP_PERMISSIONS` | Skip permission prompts |

### Happier UI Configuration

The container can act as a Happier relay server (hub) or an agent (client connecting to a remote server). When `HAPPIER_SERVER_URL` is set, the container automatically authenticates with the relay server and starts the Happier daemon on startup.

| Variable | Default | Description |
|----------|---------|-------------|
| `HAPPIER_MODE` | *(not set)* | Role of this container: `server` starts the relay server and web UI, `agent` connects to a remote relay server |
| `HAPPIER_SERVER_URL` | `https://localhost:3005` (server) | URL of the Happier relay server to connect to |
| `HAPPIER_ACCESS_KEY` | *(not set)* | **Fully automated authentication.** Set to the full JSON content of an `access.key` file (obtained from a previous `happier auth login` session). The script writes it to the correct location and starts the daemon — no manual approval needed. |
| `TUNNEL_PORT` | `3005` | (Server mode only) External port the TLS tunnel listens on — the port you access in the browser |
| `TUNNEL_TARGET_HOST` | `localhost` | (Server mode only) Where the TLS tunnel forwards plaintext traffic |
| `TUNNEL_TARGET_PORT` | `3006` | (Server mode only) Internal port `happier-server` listens on |

**Authentication flow:**
- **Existing credentials found** → daemon starts immediately
- **`HAPPIER_ACCESS_KEY` provided** → key is written, daemon starts immediately
- **Default** → the container submits a pairing request and prints a one-time connect URL in the logs. Open that URL in your browser to approve. After approval, credentials persist for future restarts. The URL looks like:

  ```
  https://<server>:3005/terminal/connect#key=<base64-key>&server=https%3A%2F%2F<server>%3A3005
  ```

**Data persistence for `HAPPIER_MODE=server`:**

To persist Happier server data and CLI credentials across container restarts, mount **both** of these paths as volumes:

| Container Path | Purpose | Contents |
|---------------|---------|----------|
| `/config/.happier` | CLI credentials and server profiles | `servers/<id>/access.key` files, pairing approvals |
| `/config/.happy` | Server data and TLS certs | `happier-server-light.sqlite` database, `tunnel.key`/`tunnel.crt` TLS certificate, Prisma migrations |

Without these mounts, the server loses all state on restart — registered agents, pairing approvals, and the SQLite database will be recreated from scratch and you'll need to re-pair every client.

**Using the Happier Cloud Relay (Mobile App Control):**

In addition to running a local relay server, you can connect to the Happier Cloud relay at `https://api.happier.dev` to control your agents through the [Happier mobile app](https://github.com/happier-dev/happier). Run these commands inside the container:

```bash
happier --server-url https://api.happier.dev auth login
happier --server-url https://api.happier.dev daemon start
```

This pairs the container's Happier CLI with the cloud relay, enabling you to approve pairing requests, manage sessions, and interact with your agents from your phone. This works alongside a local relay — you can have agents connected to both simultaneously.

### build-env Configuration

| Variable | Description |
|----------|-------------|
| `BUILD_CONTAINER` | Docker image to use for build environment |
| `DEFAULT_WORKSPACE` | Path to the workspace directory |

### Git Repository Setup
| Variable | Description |
|----------|-------------|
| `GIT_REPO_URL` | Repository URL to clone on startup |
| `GIT_BRANCH_NAME` | Branch name |

### BuildKit Builder Configuration
| Variable | Default | Description |
|----------|---------|-------------|
| `USE_BUILDKIT_BUILDER` | *(not set)* | Set to `true` to create a persistent BuildKit builder container at startup for faster Docker builds |
| `BUILDX_BUILDER_NAME` | `buildkit-builder` | Name for the BuildKit builder container (only used when `USE_BUILDKIT_BUILDER=true`) |

### Beads Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_ENABLED` | *(not set)* | Set to `true` to automatically initialize Beads (`bd init`) in the workspace on container startup |
| `BEADS_DIR` | *(not set)* | Enables **stealth mode**: stores the Beads database at this path (outside the workspace) and initializes with `bd init --quiet --stealth`, keeping beads files out of the workspace |
| `DOLT_USERNAME` | *(not set)* | Git/Dolt username for remote sync (configures `git config --global user.name`) |
| `DOLT_EMAIL` | *(not set)* | Git/Dolt email for remote sync (configures `git config --global user.email`) |

**Stealth mode:**

When `BEADS_DIR` is set, Beads runs in stealth mode — the database lives at `$BEADS_DIR` (e.g. under `/config` for persistence) instead of `.beads/` in the workspace, and `bd init --quiet --stealth` configures git excludes so no beads files are committed or tracked. This is ideal for personal use without affecting repo collaborators. Mount a volume on `BEADS_DIR` to persist the database:

```yaml
environment:
  - BEADS_ENABLED=true
  - BEADS_DIR=/config/.beads
volumes:
  - /path/to/beads-data:/config/.beads
```

**Beads (bd) Usage:**

Beads provides a persistent, version-controlled issue graph for AI agents. It replaces linear TODO lists with a dependency-aware graph database backed by Dolt (Git for data).

```bash
# Inside the container, after BEADS_ENABLED=true startup:
bd quickstart             # Interactive tutorial
bd create "Fix login bug"          # Create an issue
bd graph                  # Visualize the issue graph
bd list                   # List all issues
bd show <issue-id>        # Show issue details
bd close <issue-id>       # Mark an issue complete
```

**Remote Sync with DoltHub/DoltLab:**

```yaml
environment:
  - BEADS_ENABLED=true
  - DOLT_USERNAME=your-dolt-username
  - DOLT_EMAIL=your@email.com
```

Then inside the container:
```bash
bd remote add origin dolthub://user/repo
bd push origin main
bd pull origin main
```

**Data Persistence:**

In standard mode, Beads stores its data in a `.beads` directory within the workspace (`/workspace/.beads`). Since the workspace is already mounted as a volume in the standard configuration, **no additional volume mounts are required** — Beads data persists automatically with your code.

In stealth mode (when `BEADS_DIR` is set), data lives at `$BEADS_DIR` instead — mount a volume there to persist it (see above).

### Scotty (Beads UI) Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_SCOTTY` | *(not set)* | Set to `true` to start the Beads web UI (Scotty) on container startup |
| `SCOTTY_PORT` | `3000` | Port the Scotty web UI listens on |

**Scotty (Bead UI) Usage:**

Scotty is a five-column kanban board for Beads issues (Backlog · Ready · In Progress · Blocked · Done) with drag-and-drop, epics, a dependency graph, comments, and create/edit. It shells out to the `bd` CLI, which stays the single source of truth.

```yaml
environment:
  - ENABLE_SCOTTY=true
  - SCOTTY_PORT=3000 # Optional
```

Then open `http://localhost:3000` in your browser. The workspace (which contains the `.beads` database) is registered automatically as a project. If you also set `BEADS_DIR` (stealth mode), Scotty links the workspace's `.beads` to `BEADS_DIR` and passes the variable through to `bd`, so the database is found there.

*Note: the UI reads the database via the `bd` CLI, so set `BEADS_ENABLED=true` (or run `bd init` yourself) so a database exists.*

### Beads Dispatch (auto-provision workers for ready tasks on commit)

Every time you **commit** in the workspace repo, the dispatcher checks the Beads ready set (open issues with no active blockers) and creates a **worker** for each ready task not yet dispatched — a container/service from the running image with `GIT_BRANCH_NAME` set to a branch named after the task. The branch is created **off the current HEAD** (the state you just committed) and **pushed** to origin, so the worker pulls a branch that actually contains the task's work — the tool never commits anything itself. On a swarm manager node the worker is started as a swarm service; otherwise as a local Docker container. Workers mount **no volumes** (ephemeral — `git-repo-setup.sh` clones `GIT_REPO_URL` and checks out the branch on boot).

| Variable | Default | Description |
|----------|---------|-------------|
| `BEADS_DISPATCH` | *(unset)* | Set to `true` to enable the dispatcher on container startup |
| `BEADS_DISPATCH_BRANCH_PREFIX` | `task` | Git branch prefix: `<prefix>/<issue-id>-<slug>` |
| `BEADS_DISPATCH_PORT_BASE` | `8000` | Lowest host port considered for the worker's code-server (8443) mapping |
| `BEADS_DISPATCH_WORKER_PORT` | `8443` | Internal port published on the worker (code-server) |
| `BEADS_DISPATCH_STATE_DIR` | `/config/.beads-dispatch` | Where the seen-set state file lives |

**Usage:**

```yaml
environment:
  - BEADS_DISPATCH=true
  - BEADS_DISPATCH_BRANCH_PREFIX=task # Optional
  - BEADS_DISPATCH_PORT_BASE=8000     # Optional
  - GIT_REPO_URL=https://github.com/user/repo.git # Required (or the workspace must have a git origin)
```

**How the trigger works:** the dispatcher installs a `post-commit` hook in the workspace repo and runs a small root daemon. On every `git commit`, the hook (which runs as the committing user) pings the daemon over a local unix socket; the daemon (which has the docker-socket access) checks for ready tasks and dispatches. Commits are never blocked or modified.

When you commit and a task is ready (e.g. `probe-n5h`, "Task A"), the dispatcher:
1. creates the branch `task/probe-n5h-task-a` **off the current HEAD** and pushes it to origin,
2. restores the branch you were on (your working state is untouched),
3. starts a worker named `<container>-<issue-id>` (e.g. `claude-dev-probe-n5h`),
4. with code-server at `http://localhost:<free-port>` (first free port ≥ `BEADS_DISPATCH_PORT_BASE`),
5. as a **swarm service** if the node is a swarm manager, else a **local container**.

The worker inherits the full environment (API keys, providers) but sets `BEADS_DISPATCH=false`, so workers never dispatch their own workers. Each task is dispatched once — a later commit won't duplicate it (state is tracked in `/config/.beads-dispatch/state.json`).

> **Prerequisite:** the parent container must be able to `git push` to its origin (a credential helper / token), or the dispatcher logs a clear error and skips the task.

### Knowledge Repository Integration
| Variable | Description |
|----------|-------------|
| `KNOWLEDGE_REPOS` | Git repos with markdown files to load into CLAUDE.md (format: `URL[:branch]:file1,file2;...`) |

## Docker Compose

```yaml
services:
  claude-dev:
    image: tylercollison2089/claude-conx:latest
    container_name: claude-dev
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Etc/UTC
      - PASSWORD=password # Optional
      - HASHED_PASSWORD= # Optional
      - SUDO_PASSWORD=password # Optional
      - SUDO_PASSWORD_HASH= # Optional
      - PROXY_DOMAIN=code-server.my.domain # Optional
      # VSCode Configuration
      - DEFAULT_WORKSPACE=/workspace
      - PWA_APPNAME=code-server # Optional
      - VSCODE_THEME=Dark Modern # Optional
      - CLAUDE_CODE_PERMISSION_MODE=acceptEdits
      # API Key Configuration
      - NIM_API_KEY=your-nvidia-nim-api-key # Required to use NIM models
      - GOOGLE_API_KEY=your-google-ai-studio-api-key # Required to use Google models
      - MISTRAL_API_KEY=your-mistral-api-key # Required to use Mistral models
      - CEREBRAS_API_KEY=your-cerebras-api-key # Required to use Cerebras models
      - OPENCODE_ZEN_API_KEY=your-opencode-zen-api-key # Required to use OpenCode Zen models
      - EXA_API_KEY=your-exa-api-key # Required for EXA AI websearch
      # Claude Code Plugins (optional)
      - CLAUDE_MARKETPLACES=anthropics/claude-plugins-official
      - CLAUDE_PLUGINS=ralph-loop,superpowers
      # Git repository setup (optional)
      - GIT_REPO_URL=https://github.com/user/repo.git
      - GIT_BRANCH_NAME=feature-branch
      # Knowledge repositories (optional)
      - KNOWLEDGE_REPOS=https://github.com/user/docs.git:main:README.md,docs/guide.md
      # Happier Configuration (optional)
      - HAPPIER_MODE=server
      - HAPPIER_SERVER_URL=https://localhost:3005
      # Claude Threads (optional)
      - ENABLE_THREADS=true
      - IDE_ADDRESS=http://localhost:8443
      - MM_ADDRESS=http://mattermost.example.com:8065
      - MM_CHANNEL=claude-code
      - MM_TOKEN=your-bot-token
      - MM_TEAM=engineering
      - MM_BOT_NAME=claude-code
      - THREADS_CHROME=true
      - THREADS_WORKTREE_MODE=off
      - THREADS_SKIP_PERMISSIONS=true
      # Docker Buildkit Configuration (optional)
      - USE_BUILDKIT_BUILDER=true
      # Build Environment Configuration (optional)
      - BUILD_CONTAINER=python:3.13.14-trixie
      # Beads Configuration (optional)
      - BEADS_ENABLED=true
      - DOLT_USERNAME=your-dolt-username
      - DOLT_EMAIL=your@email.com
      # Beads stealth mode (optional) — store database at BEADS_DIR
      # - BEADS_DIR=/config/.beads
      # Scotty — Beads web UI (optional)
      - ENABLE_SCOTTY=true
      - SCOTTY_PORT=3000 # Optional
      # Beads Dispatch — auto-provision workers for ready tasks (optional)
      - BEADS_DISPATCH=true
      - BEADS_DISPATCH_BRANCH_PREFIX=task # Optional
      - BEADS_DISPATCH_PORT_BASE=8000     # Optional
    ports:
      - "8443:8443" # VSCode UI
      - "3005:3005" # Happier UI
      - "4000:4000" # LiteLLM UI
      - "3000:3000" # Scotty (Beads UI) — only if ENABLE_SCOTTY=true
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock # Optional for docker support
      - /path/to/code-server/config:/config # Only specify if using existing configuration
      - /path/to/your/code:/workspace # Only specify if GIT_REPO_URL is unset
      - /path/to/happier-cli-credentials:/config/.happier # Persist Happier CLI credentials & profiles
      - /path/to/happier-server:/config/.happy # Persist Happier server DB & TLS cert (server mode)
      # - /path/to/beads-data:/config/.beads # Persist Beads database in stealth mode
    restart: unless-stopped
```

## Configuration

### VS Code Theme

You can set the default color theme for VS Code using the `VSCODE_THEME` environment variable. This is useful for pre-configuring the IDE appearance without manual steps.

**Examples:**

```yaml
environment:
  - VSCODE_THEME=Dark Modern        # Default modern dark theme
  - VSCODE_THEME=Solarized Dark     # Classic solarized dark
  - VSCODE_THEME=Monokai            # Popular high-contrast theme
  - VSCODE_THEME=GitHub Dark        # Requires GitHub Theme extension
```

*Note: If the theme belongs to an extension, ensure the extension is either pre-installed or will be installed*

### Claude Code Setup

Claude Code is pre-configured to route all requests through the LiteLLM proxy at `http://127.0.0.1:5090`. No additional setup is needed — just open the terminal in VS Code and run `claude`.

To override the default routing and use a specific model directly, set the model environment variable to the desired model or model group:

```yaml
environment:
  - ANTHROPIC_DEFAULT_OPUS_MODEL="claude-opus-5" # Bypass litellm
  - ANTHROPIC_DEFAULT_SONNET_MODEL=lite-llm/think # Use complex-reasoning tier
  - ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-ai/deepseek-v4-flash # Use a fast model
```

### LiteLLM Router

The LiteLLM proxy provides a three-stage routing pipeline:

1. **Image detection** — requests with image data automatically route to `lite-llm/image` (Google Gemini 3.5 Flash)
2. **Web search detection** — requests with web search tools route to `lite-llm/webSearch` (Google Gemini 3.5 Flash)
3. **Complexity routing** — all other requests are scored by complexity and routed to either `lite-llm/default` (OpenCode Zen DeepSeek v4 Flash) for simple tasks or `lite-llm/think` (NVIDIA NIM DeepSeek v4 Pro) for complex reasoning

The routing configuration lives in `/lite-llm/lite-llm-default.yaml`. All configured models and model groups:

#### Model Groups

| Group | Primary Model | Provider | Purpose |
|-------|---------------|----------|---------|
| `lite-llm/router` | DeepSeek V4 Flash (OpenCode Zen) | OpenCode Zen | **Main entry point** — multi-stage routing pipeline (content → complexity) |
| `lite-llm/complexity` | Auto-router | — | Complexity-based router (SIMPLE/MEDIUM → default, COMPLEX/REASONING → think) |
| `lite-llm/default` | DeepSeek V4 Flash | OpenCode Zen | Standard chat and coding tasks |
| `lite-llm/think` | DeepSeek V4 Pro | NVIDIA NIM | Complex reasoning and deep analysis |
| `lite-llm/longContext` | DeepSeek V4 Pro | NVIDIA NIM | Long-context tasks |
| `lite-llm/webSearch` | Gemini 3.5 Flash | Google AI Studio | Queries requiring web search (EXA AI) |
| `lite-llm/image` | Gemini 3.5 Flash | Google AI Studio | Image analysis and vision tasks |

#### Underlying Models (Deployments)

| Model Name | Provider | API Key Required |
|------------|----------|------------------|
| `gemini-3.5-flash` | Google AI Studio | `GOOGLE_API_KEY` |
| `gemini-3-flash-preview` | Google AI Studio | `GOOGLE_API_KEY` |
| `gemini-2.5-flash` | Google AI Studio | `GOOGLE_API_KEY` |
| `gemini-embedding-2` | Google AI Studio | `GOOGLE_API_KEY` |
| `gemini-embedding-001` | Google AI Studio | `GOOGLE_API_KEY` |
| `zai-glm-4.7` | Cerebras | `CEREBRAS_API_KEY` |
| `minimaxai/minimax-m3` | NVIDIA NIM | `NIM_API_KEY` |
| `moonshotai/kimi-k2.6` | NVIDIA NIM | `NIM_API_KEY` |
| `deepseek-ai/deepseek-v4-flash` | NVIDIA NIM | `NIM_API_KEY` |
| `deepseek-ai/deepseek-v4-pro` | NVIDIA NIM | `NIM_API_KEY` |
| `z-ai/glm-5.1` | NVIDIA NIM | `NIM_API_KEY` |
| `nvidia/nv-embed-v1` | NVIDIA NIM | `NIM_API_KEY` |
| `nemotron-3-ultra-free` | OpenCode Zen | `OPENCODE_ZEN_API_KEY` |
| `big-pickle` | OpenCode Zen | `OPENCODE_ZEN_API_KEY` |
| `deepseek-v4-flash-free` | OpenCode Zen | `OPENCODE_ZEN_API_KEY` |
| `mistral-medium-latest` | Mistral | `MISTRAL_API_KEY` |
| `mistral-large-latest` | Mistral | `MISTRAL_API_KEY` |
| `mistral-embed` | Mistral | `MISTRAL_API_KEY` |

Each model group has a fallback chain defined in the YAML config, so if the primary model is unavailable, traffic routes to alternative providers automatically.

### Claude Threads

Enable real-time Mattermost integration:

```yaml
environment:
  - ENABLE_THREADS=true
  - MM_ADDRESS=http://mattermost.example.com:8065
  - MM_TOKEN=your-bot-token
  - MM_CHANNEL=claude-code
  - MM_TEAM=engineering
  - MM_BOT_NAME=claude-code
```

**Features:**
- WebSocket-based real-time communication
- Automatic channel creation if not exists
- User session management
- Support for worktree isolation mode

### cconx Usage

cconx provides command-line management of ClaudeConX instances:

```bash
# Start a new instance
cconx start my-instance

# Start with port and environment variable overrides
cconx start dev-instance --port 8080 --env CLAUDE_CODE_PERMISSION_MODE=bypassPermissions

# Show instance status
cconx status

# Stop an instance
cconx stop my-instance

# Delete an instance (container and config)
cconx delete my-instance
```

### build-env Usage

build-env creates persistent Docker containers for build commands:

```bash
# Set required environment variables
export BUILD_CONTAINER="python:3.12-slim"
export DEFAULT_WORKSPACE="/path/to/workspace"

# Run commands in the build environment
build-env python --version
build-env npm install
build-env npm run build

# Shutdown the build environment container
build-env --exit
```

### Git Repository Auto-Setup

Automatically clone and configure a repository on startup:

```yaml
environment:
  - GIT_REPO_URL=https://github.com/user/repo.git
  - GIT_BRANCH_NAME=feature/my-branch # Optional: auto-generated if not set
```

The container will:
1. Clone the repository to `/workspace`
2. Create/checkout the specified branch
3. Set appropriate permissions

### Knowledge Repository Integration

Combine markdown documentation from multiple repositories:

```yaml
environment:
  - KNOWLEDGE_REPOS=https://github.com/user/repo1.git:main:README.md,docs/guide.md;https://github.com/user/repo2.git:develop:docs/api.md
```

The combined documentation is saved as `/workspace/CLAUDE.md`.

**Format:**
- `;` separates repositories
- `:` separates URL, optional branch, and file list
- `,` separates files within a repository

### Permission Control

Configure Claude Code security settings:

| Mode | Description |
|------|-------------|
| `acceptEdits` | Default — balanced security with user confirmation |
| `bypassPermissions` | Full access for trusted environments |
| `default` | Claude's default permission behavior |
| `plan` | Planning mode without execution |
| `dontAsk` | Suppress confirmation prompts |

### Docker-in-Docker Support

Run Docker commands inside the container:

```bash
# List containers on the host
docker ps

# Build containers
docker build -t my-app .
```

**BuildKit Accelerated Builds:** For faster Docker builds, set `USE_BUILDKIT_BUILDER=true`:

```bash
docker run -d \
  --name=claude-dev \
  -e USE_BUILDKIT_BUILDER=true \
  ...
  -v /var/run/docker.sock:/var/run/docker.sock \
  tylercollison2089/claude-conx
```

This creates a persistent [BuildKit](https://github.com/moby/buildkit) builder container (`buildkit-builder`) managed by the host Docker daemon. It avoids the expensive layer-export step that the default `docker` builder incurs, significantly speeding up `docker build` and `docker buildx build` commands.

The builder is created once at startup and persists across container restarts. Multiple containers can share the same builder — only the first one creates it; subsequent containers detect and reuse it.

**Security Note:** Mounting `/var/run/docker.sock` gives the container full control over the host's Docker daemon.

## Features

### VS Code Integration
- Full VS Code feature set including extensions
- Integrated terminal and debugging
- Git version control support
- Multi-language support

### AI-Powered Development
- Code generation from natural language
- Automated debugging and issue resolution
- Codebase navigation and understanding
- Automated testing and documentation

### Model Flexibility
- Multiple AI provider support via LiteLLM
- Content-aware routing (images, web search, complexity-based tiering)
- Automatic fallback chains for high availability

### Auto-Configuration
- Git repository cloning and branch setup
- Knowledge repository markdown combination
- LiteLLM routing configuration loaded on startup
- Claude Code plugin and marketplace setup
- Mattermost channel auto-creation

## Building Locally

```bash
git clone https://github.com/TylerCollison/vscode-claude.git
cd vscode-claude
docker build -t tylercollison2089/vscode-claude:latest .
```

## Troubleshooting

### Container-Level Debugging

```bash
# Check container logs
docker logs claude-dev

# Inspect container environment
docker exec claude-dev env

# Test internal services
docker exec claude-dev curl -I http://localhost:8443
```

### Application-Level Debugging

```bash
# VS Code Server status
docker exec claude-dev ps aux | grep code-server

# Claude Code functionality
docker exec claude-dev claude --version

# Check LiteLLM proxy status
docker exec claude-dev curl -s http://127.0.0.1:5090/health

# Beads functionality
docker exec claude-dev bd --version

# Scotty (Beads UI) status
docker exec claude-dev ps aux | grep server.js
docker exec claude-dev curl -I http://localhost:3000
```

### Common Issues

**Claude Code Authentication:**
- Verify Claude Code installation: `which claude`
- Check network connectivity: `curl -I https://api.claude.com`

**VS Code Connection:**
- Verify port mapping: `docker port claude-dev`
- Check for port conflicts: `netstat -tulpn | grep 8443`

**Mattermost Integration:**
- Test API connectivity: `curl -H "Authorization: Bearer $MM_TOKEN" "$MM_ADDRESS/api/v4/channels"`
- Verify bot permissions for channel access
- Check WebSocket connectivity if using Claude Threads

**LiteLLM Configuration:**
- Verify LiteLLM is running: `curl -s http://127.0.0.1:5090/health`

**cconx Issues:**
- Verify cconx installation: `which cconx`
- Check instance configuration: `ls ~/.cconx/instances/`
- Validate Docker network: `docker network ls`

**build-env Issues:**
- Verify Docker daemon is running: `docker ps`
- Check workspace permissions: `ls -la $DEFAULT_WORKSPACE`
- Validate container image: `docker pull $BUILD_CONTAINER`

**Scotty (Beads UI) Issues:**
- Verify it's running: `docker exec claude-dev curl -I http://localhost:3000`
- Check the startup log: `docker exec claude-dev cat /tmp/scotty.log`
- Ensure `ENABLE_SCOTTY=true` is set and the port (`SCOTTY_PORT`, default `3000`) isn't already in use

**Beads Dispatch Issues:**
- Verify the daemon is running: `docker exec claude-dev ps aux | grep beads-dispatch`
- Check the daemon log: `docker exec claude-dev cat /tmp/beads-dispatch.log`
- Confirm the post-commit hook is installed: `docker exec claude-dev cat /workspace/.git/hooks/post-commit`
- Inspect the seen-set state: `docker exec claude-dev cat /config/.beads-dispatch/state.json`
- List dispatched workers: `docker service ls --filter label=beads.task` (swarm) or `docker ps --filter label=beads.task` (local)
- If you committed but no worker appeared: check the log for "Commit trigger received" and any "could not push branch" error (the parent needs git push credentials for its origin)
- Ensure `BEADS_DISPATCH=true`, the docker socket is mounted, and `GIT_REPO_URL` (or a workspace git origin) is set

## Credits

- **[linuxserver/code-server](https://hub.docker.com/r/linuxserver/code-server)** — Base VS Code Server environment
- **[Anthropic Claude Code](https://code.claude.com/docs/en/overview)** — AI coding assistant
- **[LiteLLM](https://github.com/BerriAI/litellm)** — Model routing and provider proxy
- **[Claude Threads](https://github.com/anneschuth/claude-threads)** — Real-time chat integration
- **[Happier](https://docs.happier.dev/)** — Relay server and mobile app for agent management
- **[Beads](https://github.com/gastownhall/beads)** — Distributed graph issue tracker for AI agents
- **[Scotty (Bead UI)](https://github.com/brendan-appstart/bead-me-up-scotty)** — Web UI for the Beads issue tracker

## Support

### Documentation
- **VS Code**: [vscode server documentation](https://code.visualstudio.com/docs/remote/vscode-server)
- **Claude Code**: [Claude Code documentation](https://code.claude.com/docs/en/overview)
- **linuxserver/code-server**: [linuxserver/code-server documentation](https://hub.docker.com/r/linuxserver/code-server)
- **LiteLLM**: [LiteLLM Documentation](https://docs.litellm.ai)
- **Claude Threads**: [Claude Threads GitHub](https://github.com/anneschuth/claude-threads)
- **Happier**: [Happier documentation](https://docs.happier.dev/)
- **Scotty (Bead UI)**: [bead-me-up-scotty GitHub](https://github.com/brendan-appstart/bead-me-up-scotty)
- **cconx**: [cconx GitHub](https://github.com/TylerCollison/vscode-claude/tree/main)
- **build-env**: [build-env GitHub](https://github.com/TylerCollison/vscode-claude/tree/main)
- **tylercollison2089/vscode-claude**: [ClaudeConX GitHub](https://github.com/TylerCollison/vscode-claude/tree/main)

### Issues
- **VS Code**: [vscode GitHub issue tracker](https://github.com/microsoft/vscode/issues)
- **linuxserver/code-server**: [linuxserver/code-server GitHub issue tracker](https://github.com/linuxserver/docker-code-server/issues)
- **Claude Code**: [Claude Code GitHub issue tracker](https://github.com/anthropics/claude-code/issues)
- **LiteLLM**: [LiteLLM GitHub issue tracker](https://github.com/BerriAI/litellm/issues)
- **Claude Threads**: [Claude Threads GitHub issue tracker](https://github.com/anneschuth/claude-threads/issues)
- **Happier**: [Happier issue tracker](https://github.com/happier-dev/happier/issues)
- **Scotty (Bead UI)**: [bead-me-up-scotty GitHub issue tracker](https://github.com/brendan-appstart/bead-me-up-scotty/issues)
- **cconx**: [cconx GitHub issue tracker](https://github.com/TylerCollison/vscode-claude/issues)
- **build-env**: [build-env GitHub issue tracker](https://github.com/TylerCollison/vscode-claude/issues)
- **tylercollison2089/vscode-claude**: [ClaudeConX GitHub issue tracker](https://github.com/TylerCollison/vscode-claude/issues)

## License

This Docker image is provided as-is. Please refer to the individual component licenses for linuxserver/code-server, Claude Code, LiteLLM, Claude Threads, Happier, and Beads. 
