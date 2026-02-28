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

## Environment Variables Reference

This container supports extensive configuration through environment variables. Below is a comprehensive reference organized by functionality:

### Container Configuration
- `PUID` - **User ID** for container processes (default: `1000`)
- `PGID` - **Group ID** for container processes (default: `1000`)
- `TZ` - **Timezone** configuration (default: `Etc/UTC`, examples: `America/New_York`, `Europe/London`)
- `PROXY_DOMAIN` - **Reverse proxy domain** for external access
- `DEFAULT_WORKSPACE` - **Default workspace directory** (default: `/config/workspace`)
- `PWA_APPNAME` - **Progressive Web App name** for browser installation

### Authentication & Access Control
- `PASSWORD` - **Plaintext password** for VS Code web interface
- `HASHED_PASSWORD` - **Argon2id-hashed password** (recommended for security)
- `SUDO_PASSWORD` - **Plaintext sudo password** for administrative operations
- `SUDO_PASSWORD_HASH` - **Hashed sudo password** for secure administrative access

### AI Model Configuration
- `NIM_API_KEY` - **NVIDIA NIM API key** - Required for NIM-hosted models
- `GOOGLE_API_KEY` - **Google AI Studio API key** - Required for Google models
- `CCR_PROFILE` - **Claude Code Router profile** - Uses `ccr <profile>` command when set and available, falls back to `claude`

### Claude Code Security
- `CLAUDE_CODE_PERMISSION_MODE` - **Permission control** for Claude Code operations:
  - `acceptEdits` (default) - Balanced security with user confirmation
  - `bypassPermissions` - Full access for trusted environments
  - `default` - Claude's default permission behavior
  - `plan` - Planning mode without execution
  - `dontAsk` - Suppress confirmation prompts

### Multi-Repository Knowledge
- `KNOWLEDGE_REPOS` - **Git repository URLs** for markdown documentation combining:
  ```bash
  # Format: REPO_URL[:BRANCH]:FILE1,FILE2;REPO_URL[:BRANCH]:FILE1
  KNOWLEDGE_REPOS="https://github.com/user/repo1.git:main:README.md,docs/guide.md;https://github.com/user/repo2.git:develop:docs/api.md"
  ```

## Security Best Practices

### Sensitive Environment Variables

When deploying this container, handle sensitive environment variables with care:

**High-Security Variables:**
- `PASSWORD` / `HASHED_PASSWORD` - Container access authentication
- `SUDO_PASSWORD` / `SUDO_PASSWORD_HASH` - Administrative privileges
- `MM_TOKEN` - Mattermost bot authentication token
- `NIM_API_KEY` - NVIDIA NIM API key
- `GOOGLE_API_KEY` - Google AI Studio API key

**Security Recommendations:**

1. **Use Docker Secrets or HashiCorp Vault** for production deployments:
   ```bash
   # Docker Swarm secrets
   echo "your-password" | docker secret create code-password -

   # Use in compose file
   secrets:
     - code-password
   ```

2. **Avoid plaintext passwords** in environment files:
   ```bash
   # Instead of plaintext:
   -e PASSWORD=mypassword

   # Use hashed passwords:
   -e HASHED_PASSWORD="$argon2id$v=19$m=65536,t=3,p=4$..."
   ```

3. **Restrict network access** when using Docker-in-Docker:
   ```yaml
   # In Docker Compose
   networks:
     - internal-only
   ```

4. **Use dedicated tokens** for Mattermost with minimal permissions:
   - Create bot accounts with channel-specific posting rights
   - Rotate tokens regularly
   - Avoid using personal account tokens

### Container Security Considerations

**Docker Socket Access:**
- Mounting `/var/run/docker.sock` gives container full Docker host control
- Only enable in trusted environments
- Consider using rootless Docker or Podman for added security

**File System Access:**
- Mount volumes with appropriate permissions (`ro` for read-only access)
- Avoid mounting sensitive host directories unnecessarily
- Use `:Z` SELinux labels when applicable

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
2. Run `claude` to start Claude Code directly or set `CCR_PROFILE` environment variable to automatically use Claude Code Router with the specified profile
3. If using Claude Code directly, follow the authentication prompts for your Claude account. If using Claude Code Router (via `CCR_PROFILE` or `ccr` command), see the [Claude Code Router GitHub Repository](https://github.com/musistudio/claude-code-router) for configuration instructions.

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
- `MM_ADDRESS` - **Mattermost server URL** (e.g., `http://mattermost.yourcompany.com:8065`) - Include protocol and port
- `MM_CHANNEL` - **Target channel name** (e.g., `claude-code`) - Exact name, case-sensitive
- `MM_TOKEN` - **Bot authentication token** - Create dedicated bot account for notifications
- `PROMPT` - **Initial prompt text** that started Claude session - Avoid special JSON-breaking characters
- `IDE_ADDRESS` - **Claude Code session web address** - Must be valid URL with http:// or https://

**Optional Variables:**
- `MM_TEAM` - **Mattermost team name** (default: "home") - Required if channel belongs to specific team
- `MM_BOT_ENABLED` - **Enable bidirectional integration** (set to "true") - WebSocket-based real-time communication

**Example Configuration:**
```bash
docker run -d \
  --name=claude-dev \
  -e PUID=1000 \
  -e PGID=1000 \
  -e TZ=Etc/UTC \
  -e MM_ADDRESS=http://portainer.home.com:8081 \
  -e MM_CHANNEL=claude-code \
  -e MM_TEAM=engineering \
  -e MM_TOKEN=your-bot-token \
  -e MM_BOT_ENABLED=true \
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
      - MM_TEAM=engineering # Optional, defaults to "home"
      - MM_TOKEN=your-bot-token
      - MM_BOT_ENABLED=true # Enable bidirectional integration
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

### Troubleshooting Mattermost Integration

#### Bidirectional Bot Issues

**WebSocket Connection Problems:**
- **Symptoms**: Bot doesn't respond to thread replies, connection timeouts
- **Debugging**: Check bot service logs:
  ```bash
  docker logs claude-dev | grep -E "(WebSocket|bot|session)"
  ```
- **Common Causes**:
  - Network firewall blocking WebSocket connections (port 8065 by default)
  - Mattermost WebSocket endpoint not accessible
  - MM_TEAM environment variable incorrect or missing

**Session Management Issues:**
- **Symptoms**: Conversation context lost, repeated introductions
- **Debugging**: Verify session timeout configuration:
  ```bash
  docker exec claude-dev env | grep -E "CC_SESSION_TIMEOUT|CC_MAX_CONTEXT_LENGTH"
  ```
- **Memory Management**: Monitor session count to prevent resource exhaustion

**Authentication & Permissions:**
- **Symptoms**: "401 Unauthorized" or bot unable to post replies
- **Debugging**: Test token validity and permissions:
  ```bash
  curl -H "Authorization: Bearer $MM_TOKEN" "$MM_ADDRESS/api/v4/users/me"
  ```

#### Notification Delivery Issues

**Common Error Scenarios:**

1. **Connection failures** (HTTP 000, 404, 401, 403 errors)
   - Verify Mattermost server URL is accessible from the container
   - Check MM_TOKEN authentication token validity
   - Confirm MM_CHANNEL exists and bot has permission to post

2. **Channel resolution failures**
   - Ensure MM_CHANNEL name is exact (case-sensitive)
   - Check bot permissions for the target channel
   - Verify channel exists and accessible (MM_TEAM may be required)

3. **Message formatting issues**
   - IDE_ADDRESS should be a valid URL starting with http:// or https://
   - PROMPT text should not contain special characters that break JSON formatting

**Debugging Steps:**

1. **Check container logs for Mattermost services:**
   - Notification script: `docker logs claude-dev | grep -i mattermost`
   - Bot service: `docker logs claude-dev | grep -E "(WebSocket|bot|session)"`

2. **Test Mattermost API connectivity:**
   ```bash
   curl -H "Authorization: Bearer $MM_TOKEN" "$MM_ADDRESS/api/v4/channels"
   ```

3. **Verify environment variables (including bidirectional settings):**
   ```bash
   docker exec claude-dev env | grep -E "MM_|IDE_|PROMPT|CC_|MAX_RECONNECT"
   ```

4. **Test WebSocket endpoint accessibility:**
   ```bash
   curl -H "Authorization: Bearer $MM_TOKEN" "$MM_ADDRESS/api/v4/websocket"
   ```

5. **Verify channel resolution with MM_TEAM:**
   ```bash
   curl -H "Authorization: Bearer $MM_TOKEN" "$MM_ADDRESS/api/v4/channels/name/${MM_TEAM}/${MM_CHANNEL}"
   ```

**Retry Behavior and Timeouts:**
- **Notifications**: Retry logic with exponential backoff (30s timeout, 2 attempts)
- **WebSocket**: Automatic reconnection with exponential backoff (5 max attempts)
- Failed communications exit gracefully without stopping container startup

**IDE_ADDRESS Format Expectations:**
- Must be a valid web address (http:// or https://)
- Should point to your Claude Code session URL
- Examples: `https://your-domain.com:8443`, `http://192.168.1.100:8443`

## Claude Code Stop Hook Integration

This image includes a **Claude Code Stop Hook** that automatically sends the last assistant message to a Mattermost thread when a Claude Code session ends, providing a complete audit trail of AI-assisted development sessions.

### How It Works

The Stop Hook executes when Claude Code finishes responding and:
1. Receives JSON input containing `last_assistant_message` via stdin
2. Validates required environment variables and input format
3. Posts the final Claude Code response as a reply to the specified Mattermost thread
4. Provides exit codes for success/failure monitoring

### Configuration

**Required Environment Variables:**
- `MM_THREAD_ID` - **Target Mattermost thread ID** - The thread where the final message should be posted
- `MM_ADDRESS` - **Mattermost server URL** - Same as bidirectional integration
- `MM_TOKEN` - **Bot authentication token** - Same as bidirectional integration

**Hook Configuration:**
The hook is automatically configured in `.claude/settings.json` and points to the stop-hook.js script:
```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/stop-hook.js",
            "description": "Mattermost Stop Hook: Sends last assistant message to Mattermost thread"
          }
        ]
      }
    ]
  }
}
```

**Example Configuration:**
```bash
docker run -d \
  --name=claude-dev \
  -e MM_ADDRESS=http://mattermost.example.com \
  -e MM_CHANNEL=claude-code \
  -e MM_THREAD_ID=your-thread-id \
  -e MM_TOKEN=your-bot-token \
  -p 8443:8443 \
  tylercollison2089/vscode-claude
```

### Testing

A test script is available to verify the hook functionality:
```bash
# Set environment variables
export MM_THREAD_ID="test-thread-id"
export MM_ADDRESS="https://your-mattermost-server.com"
export MM_TOKEN="your-test-token"

# Run the test
./test-stop-hook.js
```

### Error Handling

The hook includes comprehensive error handling:
- Validates all required environment variables
- Implements input size limits (1MB maximum)
- Includes timeout protection for API calls
- Provides meaningful error messages
- Returns proper exit codes (0=success, 1=error)

## Bidirectional Mattermost Integration

This image includes **bidirectional integration** with Mattermost using **WebSocket-based real-time communication**, allowing you to interact with Claude Code entirely through Mattermost threads.

### How It Works

The bidirectional integration establishes a persistent **WebSocket connection** to Mattermost, enabling:
- **Real-time message reception** - Instant processing of user replies in Mattermost threads
- **Conversation context management** - Claude Code maintains context per thread throughout the interaction
- **Session timeout handling** - Automatic cleanup of inactive sessions to manage memory usage
- **Error handling with retry logic** - Exponential backoff reconnection for network failures

### Configuration

Enable bidirectional integration by setting:

```bash
MM_BOT_ENABLED="true"
```

**Required Environment Variables:**
- `MM_ADDRESS` - Mattermost server URL (with protocol and port)
- `MM_CHANNEL` - Target channel name (case-sensitive)
- `MM_TOKEN` - Bot authentication token
- `MM_BOT_ENABLED` - Set to "true" to enable bidirectional functionality

**Optional Environment Variables:**
- `MM_TEAM` - Mattermost team name (default: "home")
- `CC_SESSION_TIMEOUT` - Session timeout in seconds (default: 3600)
- `CC_MAX_CONTEXT_LENGTH` - Claude Code context limit (default: 4000)
- `MAX_RECONNECT_ATTEMPTS` - WebSocket reconnection attempts (default: 5)

### Session Management & Memory Optimization

**Session Lifecycle:**
1. Session created when first user reply is detected in a thread
2. Maintains conversation context across multiple interactions
3. Automatically expires after `CC_SESSION_TIMEOUT` seconds of inactivity
4. Cleaned up to free memory resources

**Memory Management:**
- Conversation history trimmed to `CC_MAX_CONTEXT_LENGTH` characters
- Automatic session cleanup prevents memory leaks
- Input sanitization prevents malicious content injection

### Usage Workflow

1. **Startup Notification**: Container posts notification to Mattermost channel
2. **WebSocket Connection**: Bot establishes persistent connection to Mattermost
3. **User Interaction**: Reply to notification thread in Mattermost
4. **Real-time Processing**: WebSocket delivers message to Claude Code
5. **Response Delivery**: Claude Code response posted as thread reply
6. **Context Preservation**: Full conversation history maintained

### Example Configuration

```yaml
services:
  claude-dev:
    image: tylercollison2089/vscode-claude:latest
    environment:
      - MM_ADDRESS=http://mattermost.example.com
      - MM_CHANNEL=claude-code
      - MM_TEAM=engineering  # Optional, defaults to "home"
      - MM_TOKEN=your-bot-token
      - MM_BOT_ENABLED=true
      - CC_SESSION_TIMEOUT=3600  # 1 hour timeout
      - CC_MAX_CONTEXT_LENGTH=4000  # Claude Code context limit
      - MAX_RECONNECT_ATTEMPTS=5  # WebSocket retry attempts
    # ... other configuration
```

### Security Integration

This integration follows the security best practices outlined in the [Security Best Practices](#security-best-practices) section:
- Uses Mattermost bot tokens with minimal permissions
- Maintains Claude Code permission modes
- Input validation and sanitization
- No sensitive data exposure
- Secure error handling

## Claude Code Router Integration

The Mattermost bot supports Claude Code Router when the `CCR_PROFILE` environment variable is set and the `ccr` command is available.

**Configuration:**
- `CCR_PROFILE` - Set to the desired CCR profile name (e.g., "default")
- When set and `ccr` command is available, uses `ccr <profile>` instead of `claude`
- Falls back to `claude` command if conditions not met

**Example:**
```bash
docker run -d \
  --name=claude-dev \
  -e CCR_PROFILE=default \
  # ... other environment variables
  tylercollison2089/vscode-claude
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

## Error Handling and Troubleshooting

### Common Error Scenarios

#### Mattermost Integration Failures

**Notification Symptoms:** Container starts but no notification appears in Mattermost

**Bidirectional Bot Symptoms:** Bot doesn't respond to thread replies, WebSocket connection failures

**Diagnosis Steps:**
1. Check container logs for both notification and bot services:
   ```bash
   docker logs claude-dev | grep -E "(mattermost|WebSocket|bot|session)"
   ```
2. Test Mattermost API connectivity:
   ```bash
   curl -H "Authorization: Bearer $MM_TOKEN" "$MM_ADDRESS/api/v4/channels"
   ```
3. Verify environment variables (including MM_TEAM):
   ```bash
   docker exec claude-dev env | grep -E "MM_|CC_|MAX_RECONNECT"
   ```
4. Test WebSocket connection manually:
   ```bash
   curl -H "Authorization: Bearer $MM_TOKEN" "$MM_ADDRESS/api/v4/websocket"
   ```

**Common Causes:**
- **Channel/Team Resolution**: MM_TEAM required if channel not in "home" team
- **WebSocket Access**: Firewall blocking WebSocket connections (port 8065)
- **Token Permissions**: Bot token needs channel posting and WebSocket permissions
- **Network Connectivity**: Mattermost server unreachable from container

#### Claude Code Authentication Issues

**Symptoms:** `claude` command fails with authentication errors

**Diagnosis Steps:**
1. Verify Claude Code installation: `which claude`
2. Check authentication flow: `claude --help`
3. Review network connectivity: `ping api.claude.com`

**Solutions:**
- Ensure proper internet connectivity
- Check Claude account authentication status
- Verify API endpoint accessibility

#### VS Code Server Connection Issues

**Symptoms:** Unable to access VS Code web interface

**Diagnosis:**
1. Check container status: `docker ps`
2. Verify port mapping: `docker port claude-dev`
3. Test web interface: `curl -I http://localhost:8443`

**Common Issues:**
- Port conflicts with existing services
- Firewall blocking port 8443
- Container not starting properly

### Debugging Methodology

#### Container-Level Debugging

1. **Check container logs:**
   ```bash
   docker logs claude-dev
   ```

2. **Inspect container environment:**
   ```bash
   docker exec claude-dev env
   ```

3. **Test internal services:**
   ```bash
   docker exec claude-dev curl -I http://localhost:8443
   ```

#### Application-Level Debugging

1. **VS Code Server status:**
   ```bash
   docker exec claude-dev ps aux | grep code-server
   ```

2. **Claude Code functionality:**
   ```bash
   docker exec claude-dev claude --version
   ```

3. **Mattermost notification script:**
   ```bash
   docker exec claude-dev bash /etc/cont-init.d/94-mattermost-notification
   ```

### Network Troubleshooting

#### DNS Resolution Issues
- Check `/etc/resolv.conf` inside container
- Test external connectivity: `docker exec claude-dev ping 8.8.8.8`

#### Port Forwarding Problems
- Verify host firewall settings
- Check for port conflicts: `netstat -tulpn | grep 8443`

### Security Configuration Issues

#### Permission Mode Problems
- Claude Code permissions misconfigured
- Check `CLAUDE_CODE_PERMISSION_MODE` value
- Verify `/config/.claude/settings.json` file permissions

#### API Key Issues
- Missing or invalid API keys for NIM/Google services
- Check API key format and validity
- Verify API endpoint accessibility

### Recovery Procedures

#### Container Restart Sequence
```bash
docker stop claude-dev
docker rm claude-dev
docker run [original parameters]
```

#### Configuration Reset
```bash
docker exec claude-dev rm -rf /config/.claude
docker restart claude-dev
```

## License

This Docker image is provided as-is. Please refer to the individual component licenses for, linuxserver/code-server, Claude Code, and Claude Code Router.