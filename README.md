# Claude Code Development Environment

A Docker image providing a complete web-based development environment with VS Code Server and Claude Code integration, built on top of the excellent [linuxserver/code-server](https://hub.docker.com/r/linuxserver/code-server) image.

## Overview

This Docker image combines the power of browser-based VS Code development with Anthropic's Claude Code AI coding assistant, creating a comprehensive development environment accessible from any web browser. Perfect for developers who want a portable, AI-enhanced coding workspace.

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

- **Claude Code Router** - Advanced model routing and customization
  - [GitHub Repository](https://github.com/musistudio/claude-code-router)
  - Multi-provider support (OpenRouter, DeepSeek, Ollama, Gemini, etc.)
  - Dynamic model switching and request/response transformation

### Development Stack

- **Node.js 22** - Latest LTS version with npm package manager
- **Full Linux development environment** - Based on Ubuntu with common development tools
- **Web-based terminal** - Integrated terminal access within VS Code

## Quick Start

```bash
# Run the container
docker run -d \
  --name=claude-dev \
  -e PUID=1000 \
  -e PGID=1000 \
  -e TZ=Etc/UTC \
  -e PASSWORD=password `#optional` \
  -e HASHED_PASSWORD= `#optional` \
  -e SUDO_PASSWORD=password `#optional` \
  -e SUDO_PASSWORD_HASH= `#optional` \
  -e PROXY_DOMAIN=code-server.my.domain `#optional` \
  -e DEFAULT_WORKSPACE=/config/workspace `#optional` \
  -e PWA_APPNAME=code-server `#optional` \
  -e NIM_API_KEY=your-nvidia-nim-api-key `#Only required if using NIM hosted models` \
  -e GOOGLE_API_KEY=your-google-ai-studio-api-key `#Only required if using Google hosted models` \
  -p 8443:8443 \
  -v /var/run/docker.sock:/var/run/docker.sock `#Optional host docker control` \
  -v /path/to/code-server/config:/config `#Optional: Path to config folder (note that this overrides the default configuration and ccr presets)` \
  -v /path/to/your/code:/workspace `#Optional: Mount your code directory` \
  --restart unless-stopped \
  tylercollison2089/vscode-claude

# Access at http://localhost:8443
```

## Docker Compose

For easier deployment and management, you can use Docker Compose. Create a `docker-compose.yml` file:

```yaml
services:
  claude-dev:
    image: tylercollison2089/vscode-claude:latest
    container_name: claude-dev
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Etc/UTC
      - PASSWORD=password # optional
      - HASHED_PASSWORD=hash # optional
      - SUDO_PASSWORD=password # optional
      - SUDO_PASSWORD_HASH=hash # optional
      - PROXY_DOMAIN=code-server.my.domain # optional
      - DEFAULT_WORKSPACE=/workspace # optional
      - PWA_APPNAME=code-server # optional
      - CLAUDE_CODE_PERMISSION_MODE=acceptEdits
      - NIM_API_KEY=your-nvidia-nim-api-key #Only required if using NIM hosted models
      - GOOGLE_API_KEY=your-google-ai-studio-api-key #Only required if using Google hosted models
    ports:
      - "8443:8443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock # Optional host docker control
      - /path/to/code-server/config:/config # Optional: Path to config folder (note that this overrides the default configuration and ccr presets)
      - /path/to/your/code:/workspace # Optional: Mount your code directory
    restart: unless-stopped
```

### Using Docker Compose

```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down

# Update to latest version
docker-compose pull
docker-compose up -d
```

## Configuration

### VS Code Configuration
For VS Code settings, themes, and extension management, please refer to the [linuxserver/code-server documentation](https://hub.docker.com/r/linuxserver/code-server) as this image inherits all configuration options from the base image.

### Claude Code Setup
After starting the container:
1. Open the terminal in VS Code
2. Run `claude` to start Claude Code directly or `ccr default` to use Claude Code Router with the default configuration (more presets coming soon!). Note that the default Claude Code Router preset requires the NIM_API_KEY and GOOGLE_API_KEY environment variables be set. 
3. If using Claude Code directly, follow the authentication prompts for your Claude account. If using Claude Code Router, see the [Claude Code Router GitHub Repository](https://github.com/musistudio/claude-code-router) for configuration instructions.

### Permission Control
This image includes advanced permission control for Claude Code operations. You can configure security settings using environment variables:

**Core Permission Variables:**
- `CLAUDE_CODE_PERMISSION_MODE` - Controls permission mode (`acceptEdits`, `bypassPermissions`, `default`, `plan`, `dontAsk`)

**Example Configuration:**
```bash
# Development mode with full permissions
docker run -d \
  --name=claude-dev \
  -e CLAUDE_CODE_PERMISSION_MODE=bypassPermissions \
  -p 8443:8443 \
  tylercollison2089/vscode-claude

# Production mode with restricted permissions
docker run -d \
  --name=claude-prod \
  -e CLAUDE_CODE_PERMISSION_MODE=acceptEdits \
  -p 8443:8443 \
  tylercollison2089/vscode-claude
```

**Security Considerations:**
- Default mode (`acceptEdits`) provides balanced security for most use cases
- `bypassPermissions` mode should only be used in trusted environments
- Sensitive file access is automatically restricted (`.env`, `secrets/**`)

### Docker-in-Docker Support

This image includes Docker CLI tools and supports Docker-in-Docker functionality, allowing you to run Docker commands inside the container that execute on the host machine.

2. **Use Docker commands:** Inside the VS Code terminal:
   ```bash
   # List containers on the host
   docker ps

   # Run a new container on the host
   docker run hello-world

   # Build and manage containers
   docker build -t my-app .
   ```

**Security Note:** Mounting the Docker socket gives the container full control over the host's Docker daemon. Only use this in trusted environments.

## Mattermost Notifications

This Docker image includes startup notifications that can be sent to Mattermost channels, allowing you to receive alerts when new Claude Code development environments are started.

### Configuration

To enable Mattermost notifications, set the following environment variables:

**Required Environment Variables:**
- `MM_ADDRESS` - Mattermost server URL (e.g., `http://portainer.home.com:8081`)
- `MM_CHANNEL` - Target channel name (e.g., `claude-code`)
- `MM_TOKEN` - Bot authentication token
- `PROMPT` - Initial prompt text provided to Claude
- `IDE_ADDRESS` - Claude Code session web address

**Example Configuration:**
```bash
docker run -d \
  --name=claude-dev \
  -e PUID=1000 \
  -e PGID=1000 \
  -e TZ=Etc/UTC \
  -e MM_ADDRESS=http://portainer.home.com:8081 \
  -e MM_CHANNEL=claude-code \
  -e MM_TOKEN=your-bot-token \
  -e PROMPT=Initial prompt text \
  -e IDE_ADDRESS=https://your-claude-session.example.com \
  -p 8443:8443 \
  tylercollison2089/vscode-claude
```

### Docker Compose Example

```yaml
services:
  claude-dev:
    image: tylercollison2089/vscode-claude:latest
    container_name: claude-dev
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Etc/UTC
      - PASSWORD=password # optional
      - MM_ADDRESS=http://portainer.home.com:8081
      - MM_CHANNEL=claude-code
      - MM_TOKEN=your-bot-token
      - PROMPT=Initial prompt text
      - IDE_ADDRESS=https://your-claude-session.example.com
    ports:
      - "8443:8443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock # Optional host docker control
      - /path/to/code-server/config:/config # Optional: Path to config folder
      - /path/to/your/code:/workspace # Optional: Mount your code directory
    restart: unless-stopped
```

## Use Cases

### Personal Development Environment
- Access your development environment from any device with a web browser
- Consistent environment across different machines
- AI-assisted coding for faster development

### Educational Purposes
- Learn coding with AI assistance
- Collaborative coding environments
- Classroom or workshop setups

### Team Development
- Standardized development environments
- Onboarding new team members quickly
- Remote pair programming sessions

## Features

### VS Code Integration
- Full VS Code feature set including extensions
- Integrated terminal and debugging
- Git version control support
- Multi-language support

### AI-Powered Development
- Code generation from natural language descriptions
- Automated debugging and issue resolution
- Codebase navigation and understanding
- Automated testing and documentation

### Model Flexibility
- Multiple AI provider support
- Dynamic model switching based on task requirements
- Custom request/response transformations

## Building Locally
If you want to make local modifications to these images for development purposes or just to customize the logic:
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

## Multi-Repository Markdown Combination
The `combine-markdowns.sh` script supports combining markdown files from multiple git repositories.

### Usage Examples

```bash
# Multiple repositories with structured config
KNOWLEDGE_REPOS="https://github.com/user/repo1.git:main:README.md,docs/guide.md;https://github.com/user/repo2.git:develop:docs/api.md"

# Repository without branch specified
KNOWLEDGE_REPOS="https://github.com/user/repo1.git:README.md,docs/guide.md;https://github.com/user/repo2.git:docs/api.md"

# Mixed - one with branch, one without
KNOWLEDGE_REPOS="https://github.com/user/repo1.git:develop:README.md,docs/guide.md;https://github.com/user/repo2.git:docs/api.md"
```

### Configuration Format

The `KNOWLEDGE_REPOS` environment variable uses this structured format:
- `;` separates different repositories
- `:` separates repository URL, branch (optional), and file list
- `,` separates files within a repository
- **Branch is optional** - if omitted, defaults to "main"

### Output Format

The combined markdown file includes:
- Header showing all source repositories
- Clear attribution for each file showing which repository it came from
- Files processed in repository order, then file order within each repository

## Credits

This image builds upon the excellent work of:
- **[linuxserver/code-server](https://hub.docker.com/r/linuxserver/code-server)** - Base VS Code Server environment
- **[Anthropic Claude Code](https://code.claude.com/docs/en/overview)** - AI coding assistant
- **[Claude Code Router](https://github.com/musistudio/claude-code-router)** - Model routing and customization

## Support

### Documentation
- **VS Code**: Refer to the [vscode server documentation](https://code.visualstudio.com/docs/remote/vscode-server)
- **Claude Code**: Refer to the [Claude Code documentation](https://code.claude.com/docs/en/overview)
- **linuxserver/code-server**: Refer to the [linuxserver/code-server documentation](https://hub.docker.com/r/linuxserver/code-server)
- **Claude Code Router**: Refer to the [Claude Code Router GitHub](https://github.com/musistudio/claude-code-router)

### Issues
- **VS Code**: Open an issue on the [vscode GitHub issue tracker](https://github.com/microsoft/vscode/issues)
- **linuxserver/code-server**: Open an issue on the [linuxserver/code-server GitHub issue tracker](https://github.com/linuxserver/docker-code-server/issues)
- **Claude Code**: Open an issue on the [Claude Code GitHub issue tracker](https://github.com/anthropics/claude-code/issues)
- **Claude Code Router**: Open an issue on the [Claude Code Router GitHub issue tracker](https://github.com/musistudio/claude-code-router/issues)
- **tylercollison2089/vscode-claude**: Open an issue on the [VSCode Claude GitHub issue tracker](https://github.com/TylerCollison/vscode-claude/issues)

## License

This Docker image is provided as-is. Please refer to the individual component licenses for, linuxserver/code-server, Claude Code, and Claude Code Router.