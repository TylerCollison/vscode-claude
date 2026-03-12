# ClaudeConX

A Docker image providing a complete web-based development environment for Claude Code, built on top of the excellent [linuxserver/code-server](https://hub.docker.com/r/linuxserver/code-server) image.

## Overview

This Docker image bundles a web-based IDE (VSCode Server), Claude Code, Claude Code Router, and Claude Threads into a comprehensive development environment accessible from any web browser and Mattermost client. Perfect for developers who want a self-contained, and highly flexible Claude Code workspace. 

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
 - Pre-configured profiles: `default`, `nim-kimi`, `nim-deepseek`, `google-gemini`, `mistral-devstral`, `mistral-mistral-large`

- **Claude Threads** - Real-time chat integration for Mattermost
 - [GitHub Repository](https://github.com/anneschuth/claude-threads)
 - WebSocket-based bidirectional communication
 - Multi-platform support (Mattermost)

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
 -p 8443:8443 \
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

### Claude Code Router Configuration
| Variable | Description |
|----------|-------------|
| `CCR_PROFILE` | Claude Code Router profile to activate automatically |
| `NIM_API_KEY` | NVIDIA NIM API key |
| `GOOGLE_API_KEY` | Google AI Studio API key |
| `MISTRAL_API_KEY` | Mistral AI API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |

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

### Git Repository Setup
| Variable | Description |
|----------|-------------|
| `GIT_REPO_URL` | Repository URL to clone on startup |
| `GIT_BRANCH_NAME` | Branch name |

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
 - NIM_API_KEY=your-nvidia-nim-api-key # Only required if using NIM models
 - GOOGLE_API_KEY=your-google-ai-studio-api-key # Only required if using Google models
 - MISTRAL_API_KEY=your-mistral-api-key # Only required if using Mistral models
 - OPENROUTER_API_KEY=your-openrouter-api-key # Only required if using OpenRouter models
 - CCR_PROFILE=default # Optional
 # Claude Code Plugins (optional)
 - CLAUDE_MARKETPLACES=anthropics/claude-plugins-official
 - CLAUDE_PLUGINS=ralph-loop,superpowers
 # Git repository setup (optional)
 - GIT_REPO_URL=https://github.com/user/repo.git
 - GIT_BRANCH_NAME=feature-branch
 # Knowledge repositories (optional)
 - KNOWLEDGE_REPOS=https://github.com/user/docs.git:main:README.md,docs/guide.md
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
 volumes:
 - /var/run/docker.sock:/var/run/docker.sock # Optional for docker support
 - /path/to/code-server/config:/config # Only specify if using existing configuration
 - /path/to/your/code:/workspace # Only specify if GIT_REPO_URL is unset
 restart: unless-stopped
```

## Configuration

### Claude Code Setup

To run Claude Code directly without Claude Code Router, after starting the container:
1. Open the terminal in VS Code
2. Run `claude` to start Claude Code
3. Follow the authentication prompts for your Claude account

### Claude Code Router

To use CCR with a specific profile:

```bash
ccr nim-kimi
ccr google
ccr openrouter-free
ccr devstral
```

Available profiles:
- `default` - NIM DeepSeek v3.1 Terminus + Google Gemini (for images)
- `nim-kimi` - NVIDIA NIM with Kimi K2.5
- `nim-deepseek` - NVIDIA NIM with DeepSeek v3.1 Terminus
- `google-gemini` - Google Gemini 2.5 Flash
- `mistral-devstral` - Mistral Devstral + Mistral Large (for images)
- `mistral-mistral-large` - Mistral Large

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
git clone https://github.com/TylerCollison/claude-conx.git
cd claude-conx
docker build \
 --no-cache \
 --pull \
 -t tylercollison2089/claude-conx:latest .

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
- **[Claude Threads](https://github.com/anneschuth/claude-threads)** - Real-time chat integration

## Support

### Documentation
- **VS Code**: [vscode server documentation](https://code.visualstudio.com/docs/remote/vscode-server)
- **Claude Code**: [Claude Code documentation](https://code.claude.com/docs/en/overview)
- **linuxserver/code-server**: [linuxserver/code-server documentation](https://hub.docker.com/r/linuxserver/code-server)
- **Claude Code Router**: [Claude Code Router GitHub](https://github.com/musistudio/claude-code-router)
- **Claude Threads**: [Claude Threads GitHub](https://github.com/anneschuth/claude-threads)

### Issues
- **VS Code**: [vscode GitHub issue tracker](https://github.com/microsoft/vscode/issues)
- **linuxserver/code-server**: [linuxserver/code-server GitHub issue tracker](https://github.com/linuxserver/docker-code-server/issues)
- **Claude Code**: [Claude Code GitHub issue tracker](https://github.com/anthropics/claude-code/issues)
- **Claude Code Router**: [Claude Code Router GitHub issue tracker](https://github.com/musistudio/claude-code-router/issues)
- **Claude Threads**: [Claude Threads GitHub issue tracker](https://github.com/anneschuth/claude-threads/issues)
- **tylercollison2089/claude-conx**: [ClaudeConX GitHub issue tracker](https://github.com/TylerCollison/claude-conx/issues)

## License

This Docker image is provided as-is. Please refer to the individual component licenses for linuxserver/code-server, Claude Code, Claude Code Router, and Claude Threads.
