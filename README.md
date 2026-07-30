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
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /path/to/your/code:/workspace \
  --restart unless-stopped \
  tylercollison2089/claude-conx

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
| `HAPPIER_SERVER_URL` | `https://localhost:3005` (server) / `http://happier-server:3006` (agent) | URL of the Happier relay server to connect to |
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
| `BUILDX_BUILDER_NAME` | `buildkit-builder` | Name for the BuildKit builder container (only used when `USE_BUILDKIT_BUILDER=true`)

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
      - DEFAULT_WORKSPACE=/workspace
      - PWA_APPNAME=code-server # Optional
      - CLAUDE_CODE_PERMISSION_MODE=acceptEdits
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
    ports:
      - "8443:8443"
      - "3005:3005"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock # Optional for docker support
      - /path/to/code-server/config:/config # Only specify if using existing configuration
      - /path/to/your/code:/workspace # Only specify if GIT_REPO_URL is unset
      - /path/to/happier-cli-credentials:/config/.happier # Persist Happier CLI credentials & profiles
      - /path/to/happier-server:/config/.happy # Persist Happier server DB & TLS cert (server mode)
    restart: unless-stopped
```

## Configuration

### Claude Code Setup

Claude Code is pre-configured to route all requests through the LiteLLM proxy at `http://127.0.0.1:5090`. No additional setup is needed — just open the terminal in VS Code and run `claude`.

To override the default routing and use a specific model directly, set the model environment variable to the desired LiteLLM model or model group:

```yaml
environment:
  - ANTHROPIC_DEFAULT_SONNET_MODEL=lite-llm/think # Use complex-reasoning tier
  - ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-ai/deepseek-v4-flash # Use a fast model
```

### LiteLLM Router

The LiteLLM proxy provides a three-stage routing pipeline:

1. **Image detection** — requests with image data automatically route to `lite-llm/image` (Google Gemini 3.5 Flash)
2. **Web search detection** — requests with web search tools route to `lite-llm/webSearch` (Google Gemini 3.5 Flash)
3. **Complexity routing** — all other requests are scored by complexity and routed to either `lite-llm/default` (OpenCode Zen DeepSeek v4 Flash) for simple tasks or `lite-llm/think` (NVIDIA NIM DeepSeek v4 Pro) for complex reasoning

The routing configuration lives in `/lite-llm/lite-llm-default.yaml`. Key model groups:

| Group | Model | Provider |
|-------|-------|----------|
| `lite-llm/default` | DeepSeek V4 Flash | OpenCode Zen |
| `lite-llm/think` | DeepSeek V4 Pro | NVIDIA NIM |
| `lite-llm/webSearch` | Gemini 3.5 Flash | Google AI Studio |
| `lite-llm/image` | Gemini 3.5 Flash | Google AI Studio |
| `lite-llm/longContext` | DeepSeek V4 Pro | NVIDIA NIM |
| `lite-llm/background` | DeepSeek V4 Flash | OpenCode Zen |

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
cd claude-conx
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

## Credits

- **[linuxserver/code-server](https://hub.docker.com/r/linuxserver/code-server)** — Base VS Code Server environment
- **[Anthropic Claude Code](https://code.claude.com/docs/en/overview)** — AI coding assistant
- **[LiteLLM](https://github.com/BerriAI/litellm)** — Model routing and provider proxy
- **[Claude Threads](https://github.com/anneschuth/claude-threads)** — Real-time chat integration

## Support

### Documentation
- **VS Code**: [vscode server documentation](https://code.visualstudio.com/docs/remote/vscode-server)
- **Claude Code**: [Claude Code documentation](https://code.claude.com/docs/en/overview)
- **linuxserver/code-server**: [linuxserver/code-server documentation](https://hub.docker.com/r/linuxserver/code-server)
- **LiteLLM**: [LiteLLM Documentation](https://docs.litellm.ai)
- **Claude Threads**: [Claude Threads GitHub](https://github.com/anneschuth/claude-threads)
- **cconx**: [cconx GitHub](https://github.com/TylerCollison/vscode-claude/tree/main)
- **build-env**: [build-env GitHub](https://github.com/TylerCollison/vscode-claude/tree/main)
- **tylercollison2089/vscode-claude**: [ClaudeConX GitHub](https://github.com/TylerCollison/vscode-claude/tree/main)

### Issues
- **VS Code**: [vscode GitHub issue tracker](https://github.com/microsoft/vscode/issues)
- **linuxserver/code-server**: [linuxserver/code-server GitHub issue tracker](https://github.com/linuxserver/docker-code-server/issues)
- **Claude Code**: [Claude Code GitHub issue tracker](https://github.com/anthropics/claude-code/issues)
- **LiteLLM**: [LiteLLM GitHub issue tracker](https://github.com/BerriAI/litellm/issues)
- **Claude Threads**: [Claude Threads GitHub issue tracker](https://github.com/anneschuth/claude-threads/issues)
- **cconx**: [cconx GitHub issue tracker](https://github.com/TylerCollison/vscode-claude/issues)
- **build-env**: [build-env GitHub issue tracker](https://github.com/TylerCollison/vscode-claude/issues)
- **tylercollison2089/vscode-claude**: [ClaudeConX GitHub issue tracker](https://github.com/TylerCollison/vscode-claude/issues)

## License

This Docker image is provided as-is. Please refer to the individual component licenses for linuxserver/code-server, Claude Code, LiteLLM, and Claude Threads. 
