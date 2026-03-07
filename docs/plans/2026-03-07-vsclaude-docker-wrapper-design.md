# vsclaude Docker Wrapper Tool Design

**Date**: 2026-03-07
**Author**: Claude Sonnet 4.6
**Status**: Approved Design

## Overview

`vsclaude` is a Python-based Docker wrapper tool designed to simplify the management of VS Code + Claude development containers. It provides automated port allocation, flexible configuration management, and multi-instance support for running multiple isolated development environments.

## Design Decisions

### Implementation Language: Python
- **Rationale**: Robust error handling, rich CLI experience, extensible architecture
- **Dependencies**: Python 3.8+, `docker` package only
- **Distribution**: Both host-side tool and container-included version

### Configuration Management: Single Compose File Approach
- **Primary Configuration**: docker-compose.yml per instance
- **Configuration Layers**: Defaults → Global Config → Instance Config → CLI Overrides
- **Storage**: `~/.vsclaude/` directory with instance-specific subdirectories

### Port Management: Dynamic Allocation
- **Range**: Configurable port range (default: 8000-9000)
- **Allocation**: Automatic scanning for first available port
- **Conflict Resolution**: Track running instances to avoid conflicts

### Environment Variables: Flexible Handling
- **Any Variable Support**: All key-value pairs in `environment` section passed to container
- **No Validation**: No whitelist or validation of variable names
- **Template Support**: IDE_ADDRESS with `{host}` and `{port}` placeholders

## Architecture

### Command Structure
```bash
vsclaude <subcommand> [options]

Subcommands:
  start     Start a new VS Code + Claude instance
  stop      Stop a running instance
  status    Show status of instances
  config    Show configuration for an instance
  list      List all instances
  logs      Show logs for an instance
```

### File Structure
```
~/.vsclaude/
├── global-config.json          # Global settings
├── instances/                  # Instance configurations
│   ├── my-project/
│   │   ├── docker-compose.yml  # Generated compose file
│   │   ├── config.json         # Instance configuration
│   │   └── logs/               # Instance logs
│   └── another-project/
└── state.json                 # Runtime state tracking
```

### Code Structure
```
vsclaude/
├── vsclaude/                   # Python package
│   ├── __init__.py
│   ├── cli.py                 # Command-line interface
│   ├── config.py              # Configuration management
│   ├── docker.py              # Docker client interactions
│   ├── ports.py               # Port allocation logic
│   └── instances.py           # Instance management
├── tests/                     # Test suite
├── setup.py                  # Package installation
└── README.md                 # Documentation
```

## Detailed Design

### Configuration Management

**Global Configuration** (`~/.vsclaude/global-config.json`):
```json
{
  "port_range": {
    "min": 8000,
    "max": 9000
  },
  "default_profile": "default",
  "ide_address_template": "http://{host}:{port}",
  "volumes": {
    "docker_sock": "/var/run/docker.sock"
  }
}
```

**Instance Configuration** (`~/.vsclaude/instances/<name>/config.json`):
```json
{
  "name": "my-project",
  "profile": "default",
  "port": 8443,
  "volumes": {
    "config": "/path/to/config",
    "workspace": "/path/to/workspace"
  },
  "environment": {
    "PASSWORD": "password",
    "CCR_PROFILE": "default",
    "CUSTOM_VAR": "custom_value"
  }
}
```

### Port Allocation Algorithm

1. **Input**: Requested port or auto-allocation flag
2. **Validation**: Check if port is within configured range
3. **Availability Check**: Scan system ports and running instances
4. **Allocation**: Assign first available port
5. **Reservation**: Record allocation in instance state

### Docker Compose Generation

**Template-based Generation**:
```yaml
services:
  vscode-claude:
    image: tylercollison2089/vscode-claude:latest
    container_name: vsclaude-{instance_name}
    ports:
      - "{port}:8443"
    environment:
      IDE_ADDRESS: "{ide_address}"
      PASSWORD: "{password}"
      # ... all environment variables
    volumes:
      - {config_volume}:/config
      - {workspace_volume}:/workspace
      - {docker_sock}:/var/run/docker.sock
```

### Multi-instance Management

**Instance Isolation**:
- Separate directories and configuration files
- Independent port allocations
- Isolated Docker container names

**State Tracking**:
- Track running instances and their ports
- Persistent state in `~/.vsclaude/state.json`
- Recovery on tool restart

## Error Handling Strategy

### Minimal Validation Approach
- **Basic Syntax**: Validate compose file generation
- **Port Availability**: Check port conflicts
- **Docker Connectivity**: Verify Docker daemon access
- **Fail Fast**: Clear error messages, no complex recovery

### Error Messages
- **Human-readable**: Clear descriptions of issues
- **Action-oriented**: Suggest fixes when possible
- **Minimal logging**: Only essential status information

## User Experience

### Success Cases
```bash
# Start instance with auto port allocation
$ vsclaude start my-project
Instance 'my-project' started on port 8443
Access at: http://localhost:8443

# Show status with full IDE links
$ vsclaude status
my-project: RUNNING - http://localhost:8443
other-project: STOPPED
```

### Error Cases
```bash
# Port conflict
$ vsclaude start my-project --port 8443
Error: Port 8443 is already in use by instance 'other-project'
Try: vsclaude start my-project --port-auto

# Docker not available
$ vsclaude start my-project
Error: Docker daemon is not accessible
Please ensure Docker is running
```

## Implementation Plan

### Phase 1: Core Foundation (Week 1)
- Project structure and basic CLI framework
- Configuration management system
- Port allocation logic

### Phase 2: Docker Integration (Week 2)
- Docker-compose.yml generation
- Instance lifecycle management (start/stop/status)
- Multi-instance support

### Phase 3: Advanced Features (Week 3)
- IDE_ADDRESS template support
- Flexible environment variable handling
- Basic error handling and logging

### Phase 4: Testing and Polish (Week 4)
- Comprehensive pytest test suite
- CLI usability improvements
- Documentation and examples

## Testing Strategy

### Unit Tests
- Port allocation algorithm
- Configuration parsing and validation
- Docker compose template generation

### Integration Tests
- Docker API interactions (mocked)
- Multi-instance lifecycle scenarios
- Configuration persistence

### End-to-End Tests
- Full instance lifecycle
- Port conflict resolution
- Error handling scenarios

## Security Considerations

### Sensitive Data Handling
- **Plaintext Storage**: Environment variables stored in config files as requested
- **No Encryption**: No automatic encryption of sensitive data
- **User Responsibility**: Users manage file permissions and security

### Docker Security
- **Socket Access**: `/var/run/docker.sock` mounting requires explicit configuration
- **Container Isolation**: Instances run with standard Docker security
- **No Privilege Escalation**: Uses standard user permissions

## Future Extensibility

### Plugin Architecture
- Modular design supports future feature additions
- Configuration templates for different use cases
- External plugin support for advanced functionality

### Distribution Options
- **Host-side Tool**: Standalone Python package
- **Container-included**: Built into Docker image
- **Package Managers**: deb, rpm, brew packaging ready

## Success Criteria

- **Usability**: Users can start/stop instances with minimal configuration
- **Reliability**: Port allocation works correctly without conflicts
- **Flexibility**: Supports any environment variable and custom configurations
- **Performance**: Fast startup and status checks
- **Maintainability**: Clean code structure with comprehensive tests

---

**Approval**: This design has been reviewed and approved through collaborative discussion.

**Next Step**: Proceed with implementation plan using writing-plans skill.