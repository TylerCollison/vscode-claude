# Build Environment Tool Design Specification

**Date:** 2026-03-14
**Author:** Claude Code
**Status:** Draft

## Overview

The `build-env` tool provides a persistent container environment for running build, test, and development commands. It maintains a single container instance per workspace that persists indefinitely, allowing users to run commands in a consistent environment.

## Requirements

### Functional Requirements
- [x] Run commands in container defined by `BUILD_CONTAINER` environment variable
- [x] Persistent container instance (same container for all commands)
- [x] Auto-start container on first use if not running
- [x] Shutdown container via `--exit` flag
- [x] Access files in `DEFAULT_WORKSPACE` directory
- [x] Pass all host environment variables to container
- [x] Runnable from within containers
- [x] Full container privileges (without `--privileged` flag)

### Non-Functional Requirements
- [x] Standalone Python implementation (separate from cconx)
- [x] UUID-based container naming for uniqueness
- [x] Error handling with clear messages
- [x] Fast startup time
- [x] Security validation using Docker Python SDK directly

## Architecture

### Component Design

```
build-env (Standalone Python CLI)
├── Container Manager
│   ├── Container existence check (using Docker SDK directly)
│   ├── Container startup logic (with security validation)
│   └── Container shutdown logic
├── Environment Handler
│   ├── BUILD_CONTAINER validation (image name validation)
│   ├── DEFAULT_WORKSPACE mounting
│   └── Host environment variable filtering
└── Command Executor
    ├── Interactive command execution
    └── Exit flag handling
```

### Data Flow

1. **Tool Invocation** → Check `BUILD_CONTAINER` environment variable
2. **Container Check** → Verify container exists and is running
3. **Container Management** → Start/create container if needed
4. **Command Execution** → Run command in container with environment
5. **Result Return** → Pass through command output/exit code

## Detailed Design

### Container Naming Strategy

Containers use UUID-based naming for guaranteed uniqueness:
```bash
build-env-{uuid}
```

**Example:** `build-env-550e8400-e29b-41d4-a716-446655440000`

UUID generation ensures:
- No naming conflicts between projects
- Human-readable identification
- Easy cleanup management

### Container Configuration

**Container Creation Parameters:**
- **Image:** `$BUILD_CONTAINER` (required)
- **Name:** `build-env-{uuid}`
- **Volumes:** `$DEFAULT_WORKSPACE:/workspace`
- **Working Directory:** `/workspace`
- **Environment:** All host environment variables
- **TTY:** Enabled for interactive commands
- **Privileges:** Default Docker privileges

### Command Execution Pattern

```python
# Using Docker Python SDK with proper environment variable handling
container = docker_client.client.containers.get(container_name)
result = container.exec_run(
    command,
    environment=safe_environment_variables,
    workdir="/workspace",
    tty=True,
    stdin=True
)
```

### Error Handling

**Critical Errors:**
- `BUILD_CONTAINER` not set → Clear error message
- Docker daemon unavailable → Informative error
- Container creation failure → Detailed diagnostics

**Non-Critical Errors:**
- Command execution failures → Pass through exit codes
- Environment variable issues → Warn but continue

## Implementation Details

### File Structure

```
build-env/                    # Standalone tool directory
├── build_env.py              # Main Python implementation
├── build_env_cli.py          # CLI entry point
├── security.py               # Security validation utilities
├── tests/                    # Test suite
│   ├── test_build_env.py
│   └── test_security.py
└── setup.py                  # Installation script
```

### Key Functions

1. **`get_container_uuid()`** - Generate/lookup UUID for workspace
2. **`validate_image_name()`** - Security validation using standalone patterns
3. **`container_exists()`** - Check if container exists (using Docker SDK directly)
4. **`container_running()`** - Check if container is running
5. **`start_container()`** - Start/create container with security validation
6. **`execute_command()`** - Run command in container using exec_run
7. **`shutdown_container()`** - Stop and remove container

### Environment Variable Handling

Host environment variables are filtered to:
- Exclude Docker-specific variables
- Exclude sensitive variables (API keys, tokens)
- Include development/build-related variables
- Maintain security while preserving functionality

## Testing Strategy

### Unit Tests
- Container naming logic
- Environment variable parsing
- Command execution formatting

### Integration Tests
- End-to-end command execution
- Container lifecycle management
- File access validation

### Manual Testing Scenarios
1. Basic command execution
2. Container persistence across commands
3. Environment variable passing
4. File access in mounted workspace
5. `--exit` flag functionality

## Security Considerations

- No `--privileged` flag used
- Container runs with default Docker security profile
- Environment variables filtered using safe variable list
- UUID-based naming prevents container hijacking
- Image name validation using existing security patterns
- Command argument sanitization
- Input validation for all user inputs

### Security Implementation Details

**Image Validation:**
- Use standalone `validate_image_name()` function
- Pattern matching for safe image names
- Reject potentially dangerous image patterns

**Environment Variable Filtering:**
```python
# Safe environment variable whitelist
SAFE_ENV_VARS = {
    'PATH', 'HOME', 'USER', 'PWD', 'SHELL', 'TERM', 'LANG', 'LC_ALL',
    'BUILD_CONTAINER', 'DEFAULT_WORKSPACE', 'BUILD_*'
}

# Dangerous environment variable blacklist
DANGEROUS_ENV_PATTERNS = {
    'DOCKER_*', '_*', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
    'GITHUB_TOKEN', 'API_KEY', 'SECRET', 'PASSWORD', 'TOKEN'
}
```

**UUID Generation Security:**
- Use `uuid.uuid4()` for cryptographically secure random UUIDs
- Store UUID in workspace metadata for consistency
- Validate UUID format before use

**Container Privileges:**
- Use minimal Docker security profile
- No `--privileged` flag
- Capabilities limited to build requirements

**Command Execution Security:**
- Use Docker Python SDK `exec_run()` instead of shell
- Proper argument escaping using `shlex.quote()`
- Input validation using standalone patterns

## Performance Considerations

- Fast startup through container reuse
- Minimal overhead for repeated commands
- Efficient environment variable passing

## Container Cleanup Strategy

**Inactive Container Detection:**
- Track last usage timestamp
- Auto-cleanup after 24 hours of inactivity
- Manual cleanup via `build-env --cleanup` command

**Container Cleanup Process:**
1. Stop container gracefully
2. Remove container and associated resources
3. Clean up workspace metadata
4. Log cleanup actions for audit

## Future Enhancements

### Potential Features
- Multiple container support per workspace
- Custom entrypoint scripts
- Build cache persistence
- Resource usage monitoring

## Dependencies

- Docker Python SDK
- Python 3.8+
- Docker CLI available in PATH

## Success Criteria

- [ ] Commands execute successfully in container
- [ ] Container persists between commands
- [ ] File access works correctly
- [ ] Environment variables are passed through
- [ ] `--exit` flag shuts down container
- [ ] Clear error messages for misconfiguration

## Appendix

### Example Usage

```bash
# Set required environment variables
export BUILD_CONTAINER=python:3.11
export DEFAULT_WORKSPACE=$(pwd)

# Run commands in build environment
build-env python --version
build-env pip install -r requirements.txt
build-env pytest

# Shutdown container
build-env --exit
```

### Error Message Examples

```bash
# BUILD_CONTAINER not set
Error: BUILD_CONTAINER environment variable must be set
Example: export BUILD_CONTAINER=python:3.11

# Docker daemon unavailable
Error: Docker daemon is not available
Please ensure Docker is running and accessible

# Container creation failed
Error: Failed to create build container
Check Docker logs for more information: docker logs build-env-{uuid}
```