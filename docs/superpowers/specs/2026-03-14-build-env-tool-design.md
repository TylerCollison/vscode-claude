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
- [x] Simple bash script implementation
- [x] UUID-based container naming for uniqueness
- [x] Error handling with clear messages
- [x] Fast startup time
- [x] Minimal dependencies

## Architecture

### Component Design

```
build-env (bash script)
├── Container Manager
│   ├── Container existence check
│   ├── Container startup logic
│   └── Container shutdown logic
├── Environment Handler
│   ├── BUILD_CONTAINER validation
│   ├── DEFAULT_WORKSPACE mounting
│   └── Host environment variable passing
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

```bash
docker exec -it \
  -e $(env | grep -v "^_" | xargs -I {} echo "-e {}") \
  build-env-{uuid} \
  bash -c "$command"
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
/usr/local/bin/build-env      # Main executable script
/var/lib/build-env/           # State directory (optional)
  ├── containers/             # Container state tracking
  └── uuids/                  # UUID mapping to workspaces
```

### Key Functions

1. **`get_container_uuid()`** - Generate/lookup UUID for workspace
2. **`container_exists()`** - Check if container exists
3. **`container_running()`** - Check if container is running
4. **`start_container()`** - Start/create container
5. **`execute_command()`** - Run command in container
6. **`shutdown_container()`** - Stop and remove container

### Environment Variable Handling

All host environment variables are passed to the container, filtered to avoid Docker-specific variables that might cause conflicts.

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
- Environment variables filtered to avoid sensitive data leakage
- UUID-based naming prevents container hijacking

## Performance Considerations

- Fast startup through container reuse
- Minimal overhead for repeated commands
- Efficient environment variable passing

## Future Enhancements

### Potential Features
- Container cleanup after inactivity
- Multiple container support per workspace
- Custom entrypoint scripts
- Build cache persistence

## Dependencies

- Docker CLI
- Bash shell
- Standard Unix utilities

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