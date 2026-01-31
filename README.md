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
  -p 8443:8443 \
  -v /path/to/code-server/config:/config \
  -v /path/to/your/code:/workspace \
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
      # Claude Code permission settings
      - CLAUDE_CODE_PERMISSION_MODE=acceptEdits
      - CLAUDE_CODE_FULL_PERMISSIONS=0
      - CLAUDE_CODE_ENABLE_TELEMETRY=0
      - CLAUDE_CODE_HIDE_ACCOUNT_INFO=1
      - DISABLE_ERROR_REPORTING=1
      - DISABLE_TELEMETRY=1
      - BASH_DEFAULT_TIMEOUT_MS=120000
      - BASH_MAX_TIMEOUT_MS=300000
    ports:
      - "8443:8443"
    volumes:
      - /path/to/code-server/config:/config
      - /path/to/your/code:/workspace # Mount your code directory
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
2. Run `claude` to start Claude Code directly or `ccr code` to use Claude Code Router
3. If using Claude Code directly, follow the authentication prompts for your Claude account. If using Claude Code Router, see the [Claude Code Router GitHub Repository](https://github.com/musistudio/claude-code-router) for configuration instructions.

### Permission Control
This image includes advanced permission control for Claude Code operations. You can configure security settings using environment variables:

**Core Permission Variables:**
- `CLAUDE_CODE_PERMISSION_MODE` - Controls permission mode (`acceptEdits`, `bypassPermissions`, `default`, `plan`, `dontAsk`)
- `CLAUDE_CODE_FULL_PERMISSIONS` - Set to `1` to enable full permissions (equivalent to `bypassPermissions` mode)

**Security Variables:**
- `CLAUDE_CODE_ENABLE_TELEMETRY` - Enable/disable telemetry
- `CLAUDE_CODE_HIDE_ACCOUNT_INFO` - Hide personal info from UI
- `DISABLE_ERROR_REPORTING` - Opt out of error reporting
- `DISABLE_TELEMETRY` - Opt out of telemetry

**Tool Behavior Variables:**
- `BASH_DEFAULT_TIMEOUT_MS` - Default timeout for bash commands (default: 120000ms)
- `BASH_MAX_TIMEOUT_MS` - Maximum timeout model can set (default: 300000ms)

**Example Configuration:**
```bash
# Development mode with full permissions
docker run -d \
  --name=claude-dev \
  -e CLAUDE_CODE_PERMISSION_MODE=bypassPermissions \
  -e CLAUDE_CODE_FULL_PERMISSIONS=1 \
  -p 8443:8443 \
  tylercollison2089/vscode-claude

# Production mode with restricted permissions
docker run -d \
  --name=claude-prod \
  -e CLAUDE_CODE_PERMISSION_MODE=acceptEdits \
  -e CLAUDE_CODE_FULL_PERMISSIONS=0 \
  -p 8443:8443 \
  tylercollison2089/vscode-claude
```

**Security Considerations:**
- Default mode (`acceptEdits`) provides balanced security for most use cases
- `bypassPermissions` mode should only be used in trusted environments
- Sensitive file access is automatically restricted (`.env`, `secrets/**`)
- Git operations require explicit permissions for security 

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
```

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