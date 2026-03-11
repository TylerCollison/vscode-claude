# Claude Code Development Environment

A Docker image providing a complete web-based development environment with VS Code Server and Claude Code integration, built on top of the excellent [linuxserver/code-server](https://hub.docker.com/r/linuxserver/code-server) image.

## Overview

This Docker image combines the power of browser-based VS Code development with Anthropic's Claude Code AI coding assistant and Claude Threads for Mattermost integration, creating a comprehensive development environment accessible from any web browser. Perfect for developers who want a portable, AI-enhanced coding workspace.

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

- **Claude Code Router (CCR)** - Advanced model routing and customization
 - [GitHub Repository](https://github.com/musistudio/claude-code-router)
 - Multi-provider support (OpenRouter, NVIDIA NIM, Google, Ollama, Mistral, etc.)
 - Dynamic model switching and request/response transformation
 - Pre-configured profiles: `default`, `nim-kimi`, `google`, `openrouter-free`, `devstral`

- **Claude Threads** - Real-time chat integration for Mattermost
 - WebSocket-based bidirectional communication
 - Multi-platform support (Mattermost)
 - Session management with configurable timeouts

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
 -e PASSWORD=password \
 -e HASHED_PASSWORD= \
 -e SUDO_PASSWORD=password \
 -e SUDO_PASSWORD_HASH= \
 -e PROXY_DOMAIN=code-server.my.domain \
 -e DEFAULT_WORKSPACE=/config/workspace \
 -e PWA_APPNAME=code-server \
 -e NIM_API_KEY=your-nvidia-nim-api-key \
 -e GOOGLE_API_KEY=your-google-ai-studio-api-key \
 -e MISTRAL_API_KEY=your-mistral-api-key \
 -e OPENROUTER_API_KEY=your-openrouter-api-key \
 -p 8443:8443 \
 -v /var/run/docker.sock:/var/run/docker.sock \
 -v /path/to/code-server/config:/config \
 -v /path/to/your/code:/workspace \
 --restart unless-stopped \
 tylercollison2089/vscode-claude

# Access at http://localhost:8443
```

## Environment Variables Reference

This container supports extensive configuration through environment variables.

### Container Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `PUID` | User ID for container processes | `1000` |
| `PGID` | Group ID for container processes | `1000` |
| `TZ` | Timezone configuration | `Etc/UTC` |
| `PROXY_DOMAIN` | Reverse proxy domain for external access | - |
| `DEFAULT_WORKSPACE` | Default workspace directory | `/config/workspace` |
| `PWA_APPNAME` | Progressive Web App name | `code-server` |

### Authentication & Access Control
| Variable | Description |
|----------|-------------|
| `PASSWORD` | Plaintext password for VS Code web interface |
| `HASHED_PASSWORD` | Argon2id-hashed password (recommended) |
| `SUDO_PASSWORD` | Plaintext sudo password |
| `SUDO_PASSWORD_HASH` | Hashed sudo password |

### Claude Code Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `CLAUDE_CODE_PERMISSION_MODE` | Permission mode (`acceptEdits`, `bypassPermissions`, `default`, `plan`, `dontAsk`) | `acceptEdits` |
| `CLAUDE_MARKETPLACES` | Comma-separated list of plugin marketplaces | - |
| `CLAUDE_PLUGINS` | Comma-separated list of plugins to install | - |

### Claude Code Router Configuration
| Variable | Description |
|----------|-------------|
| `CCR_PROFILE` | CCR profile to activate (uses `ccr <profile>` command) |
| `NIM_API_KEY` | NVIDIA NIM API key |
| `GOOGLE_API_KEY` | Google AI Studio API key |
| `MISTRAL_API_KEY` | Mistral AI API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |

### Claude Threads Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_THREADS` | Enable Claude Threads server | `false` |
| `CCR_PROFILE` | CCR profile to use with Threads | - |
| `MM_ADDRESS` | Mattermost server URL | - |
| `MM_TOKEN` | Mattermost bot authentication token | - |
| `MM_CHANNEL` | Target channel name | - |
| `MM_CHANNEL_ID` | Target channel ID | - |
| `MM_TEAM` | Mattermost team name | `home` |
| `MM_BOT_NAME` | Bot display name | `Claude Threads` |
| `THREADS_CHROME` | Chrome executable path | - |
| `THREADS_WORKTREE_MODE` | Git worktree mode | `true` |
| `THREADS_SKIP_PERMISSIONS` | Skip permission prompts | `false` |

### Git Repository Setup
| Variable | Description |
|----------|-------------|
| `GIT_REPO_URL` | Repository URL to clone on startup |
| `GIT_BRANCH_NAME` | Branch name (auto-generated if not specified) |

### Knowledge Repository Integration
| Variable | Description |
|----------|-------------|
| `KNOWLEDGE_REPOS` | Git repos with markdown files (format: `URL[:branch]:file1,file2;...`) |

### Volume Configuration
| Variable | Description | Default |
|----------|-------------|---------|
| `enabled_volumes` | Array of container paths to mount as persistent volumes | `[]` |
| `include_docker_sock` | Whether to mount Docker socket | `true` |

**Example:**
```json
{
  "enabled_volumes": ["/config", "/workspace", "/data"],
  "include_docker_sock": false
}
```

This creates named volumes: `{instance_name}-config`, `{instance_name}-workspace`, `{instance_name}-data`

### Docker Image Configuration

You can customize the Docker image used for VSClaude instances:

#### Global Configuration
Set a default Docker image in the global configuration:

```bash
# Configure default image
vsclaude config set default_image custom-registry/my-image:latest
```

Or edit the global configuration file directly (located at `~/.vsclaude/global-config.json`):

```json
{
  "default_image": "custom-registry/my-image:latest",
  "port_range": {"min": 8000, "max": 9000},
  "default_profile": "default",
  "ide_address_template": "http://{host}:{port}",
  "environment": {},
  "enabled_volumes": ["/config", "/workspace"],
  "include_docker_sock": true
}
```

#### CLI Usage
Start instances with custom Docker images:

```bash
# Use custom image
vsclaude start my-instance --image custom-registry/my-image:v1.2.3

# Use custom registry with specific tag
vsclaude start dev-instance --image registry.example.com/vscode-claude:stable

# Use default image configured in global settings
vsclaude start test-instance
```

#### Supported Formats
- Full image string: `registry/image:tag`
- Image name only (uses default tag): `custom-registry/my-image`
- Custom tag with default image: `tylercollison2089/vscode-claude:v2.0.0`

**Examples:**
```bash
# Full image specification
vsclaude start prod --image myregistry.example.com/vscode-claude:v2.1.0

# Custom registry, default tag
vsclaude start dev --image myregistry.example.com/vscode-claude

# Default registry, custom tag
vsclaude start test --image tylercollison2089/vscode-claude:stable
```

### Docker Network Configuration

vsclaude supports optional Docker network configuration for container instances. You can specify a custom Docker network in your global configuration:

#### Global Configuration
Set a Docker network in the global configuration:

```bash
# Configure Docker network
vsclaude config set docker_network my-custom-network
```

Or edit the global configuration file directly:

```json
{
  "docker_network": "vsclaude-network",
  "port_range": {"min": 8000, "max": 9000},
  "default_profile": "default",
  "ide_address_template": "http://{host}:{port}",
  "environment": {},
  "enabled_volumes": ["/config", "/workspace"],
  "include_docker_sock": true
}
```

#### Usage
```bash
# Create the Docker network first
docker network create vsclaude-network

# Start instance on the specified network
vsclaude start my-instance
```

#### Behavior
- **Network specified**: Containers are created on the specified Docker network
- **Network doesn't exist**: vsclaude exits gracefully with clear error message
- **No network specified**: Default Docker networking behavior

See [docker-network-configuration.md](docs/docker-network-configuration.md) for detailed documentation.

## Security Best Practices

### Sensitive Environment Variables

**High-Security Variables:**
- `PASSWORD` / `HASHED_PASSWORD` - Container access authentication
- `SUDO_PASSWORD` / `SUDO_PASSWORD_HASH` - Administrative privileges
- `MM_TOKEN` - Mattermost bot authentication token
- `NIM_API_KEY`, `GOOGLE_API_KEY`, `MISTRAL_API_KEY`, `OPENROUTER_API_KEY` - AI service API keys

**Security Recommendations:**

1. **Use hashed passwords** when possible:
 ```bash
 # Generate hashed password
 echo -n "your-password" | argon2 $(openssl rand -hex 16) -e
 ```

2. **Restrict Docker socket access** in production:
 ```yaml
 networks:
 - internal-only
 ```

3. **Use dedicated tokens** for Mattermost with minimal permissions

## Docker Compose

```yaml
services:
 claude-dev:
 # Use default image
 image: tylercollison2089/vscode-claude:latest
 # Or use custom image:
 # image: custom-registry/my-image:v1.2.3
 container_name: claude-dev
 environment:
 - PUID=1000
 - PGID=1000
 - TZ=Etc/UTC
 - PASSWORD=password
 - HASHED_PASSWORD=
 - SUDO_PASSWORD=password
 - SUDO_PASSWORD_HASH=
 - PROXY_DOMAIN=code-server.my.domain
 - DEFAULT_WORKSPACE=/config/workspace
 - PWA_APPNAME=code-server
 - CLAUDE_CODE_PERMISSION_MODE=acceptEdits
 - NIM_API_KEY=your-nvidia-nim-api-key
 - GOOGLE_API_KEY=your-google-ai-studio-api-key
 - MISTRAL_API_KEY=your-mistral-api-key
 - OPENROUTER_API_KEY=your-openrouter-api-key
 # Git repository setup
 - GIT_REPO_URL=https://github.com/user/repo.git
 - GIT_BRANCH_NAME=feature-branch
 # Knowledge repositories
 - KNOWLEDGE_REPOS=https://github.com/user/docs.git:main:README.md,docs/guide.md
 # Claude Threads
 - ENABLE_THREADS=true
 - MM_ADDRESS=http://mattermost.example.com:8065
 - MM_CHANNEL=claude-code
 - MM_TOKEN=your-bot-token
 - MM_TEAM=engineering
 - MM_BOT_NAME=Claude AI
 ports:
 - "8443:8443"
 volumes:
 - /var/run/docker.sock:/var/run/docker.sock
 - /path/to/code-server/config:/config
 - /path/to/your/code:/workspace
 restart: unless-stopped
```

## Configuration

### Claude Code Setup

After starting the container:
1. Open the terminal in VS Code
2. Run `claude` to start Claude Code
3. Follow the authentication prompts for your Claude account

### Claude Code Router

To use CCR with a specific profile:

```bash
# Set the profile environment variable
export CCR_PROFILE=default

# Or use ccr command directly
ccr nim-kimi
ccr google
ccr openrouter-free
ccr devstral
```

Available profiles:
- `default` - NIM Kimi + Google Gemini hybrid
- `nim-kimi` - NVIDIA NIM with Kimi K2.5
- `google` - Google Gemini models
- `openrouter-free` - Free models via OpenRouter
- `devstral` - Mistral Devstral models

### Claude Threads

Enable real-time Mattermost integration:

```yaml
environment:
 - ENABLE_THREADS=true
 - MM_ADDRESS=http://mattermost.example.com:8065
 - MM_TOKEN=your-bot-token
 - MM_CHANNEL=claude-code
 - MM_TEAM=engineering
 - MM_BOT_NAME=Claude AI
 - CCR_PROFILE=default # Optional: use CCR profile
```

**Features:**
- WebSocket-based real-time communication
- Automatic channel creation if not exists
- User session management
- Support for worktree isolation mode

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
| `acceptEdits` | Default - balanced security with user confirmation |
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
- Multiple AI provider support via CCR
- Dynamic model switching based on task requirements
- Custom request/response transformations

### Auto-Configuration
- Git repository cloning and branch setup
- Knowledge repository markdown combination
- CCR preset configuration with environment substitution
- Claude Code plugin and marketplace setup
- Mattermost channel auto-creation

## Building Locally

```bash
git clone https://github.com/TylerCollison/vscode-claude.git
cd vscode-claude
docker build \
 --no-cache \
 --pull \
 -t tylercollison2089/vscode-claude:latest .

# Test the container starts properly
./test-container.sh
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

# Check CCR profiles
docker exec claude-dev ls -la /config/.claude-code-router/presets/
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

**CCR Configuration:**
- Verify preset files exist: `ls /ccr-presets/`
- Check environment variable substitution in `/config/.claude-code-router/presets/`

## Credits

- **[linuxserver/code-server](https://hub.docker.com/r/linuxserver/code-server)** - Base VS Code Server environment
- **[Anthropic Claude Code](https://code.claude.com/docs/en/overview)** - AI coding assistant
- **[Claude Code Router](https://github.com/musistudio/claude-code-router)** - Model routing and customization
- **[Claude Threads](https://github.com/tylercollison/claude-threads)** - Real-time chat integration

## Support

### Documentation
- **VS Code**: [vscode server documentation](https://code.visualstudio.com/docs/remote/vscode-server)
- **Claude Code**: [Claude Code documentation](https://code.claude.com/docs/en/overview)
- **linuxserver/code-server**: [linuxserver/code-server documentation](https://hub.docker.com/r/linuxserver/code-server)
- **Claude Code Router**: [Claude Code Router GitHub](https://github.com/musistudio/claude-code-router)
- **Claude Threads**: [Claude Threads GitHub](https://github.com/tylercollison/claude-threads)

### Issues
- **VS Code**: [vscode GitHub issue tracker](https://github.com/microsoft/vscode/issues)
- **linuxserver/code-server**: [linuxserver/code-server GitHub issue tracker](https://github.com/linuxserver/docker-code-server/issues)
- **Claude Code**: [Claude Code GitHub issue tracker](https://github.com/anthropics/claude-code/issues)
- **Claude Code Router**: [Claude Code Router GitHub issue tracker](https://github.com/musistudio/claude-code-router/issues)
- **Claude Threads**: [Claude Threads GitHub issue tracker](https://github.com/tylercollison/claude-threads/issues)
- **tylercollison2089/vscode-claude**: [VSCode Claude GitHub issue tracker](https://github.com/TylerCollison/vscode-claude/issues)

## License

This Docker image is provided as-is. Please refer to the individual component licenses for linuxserver/code-server, Claude Code, Claude Code Router, and Claude Threads.
