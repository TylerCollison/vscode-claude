# Docker Network Configuration Design Specification

**Date:** 2026-03-11
**Author:** Claude Code
**Project:** vsclaude Docker Network Configuration Support

## Overview

This specification outlines the design for adding optional Docker network configuration support to vsclaude, allowing all container instances to use a specified Docker network.

## Requirements

### Functional Requirements
1. **Global Configuration**: Docker network configuration should be specified in the global configuration file (`~/.vsclaude/global-config.json`)
2. **Optional Field**: The `docker_network` field should be optional (default: `null`)
3. **Network Validation**: When a network is specified, vsclaude should validate that it exists before container creation
4. **Graceful Failure**: If the specified network doesn't exist, vsclaude should log an error and exit gracefully
5. **Default Behavior**: When no network is specified, containers should use default Docker networking

### Non-Functional Requirements
1. **Backward Compatibility**: Existing configurations without network settings should continue to work unchanged
2. **Error Handling**: Clear error messages for network validation failures
3. **Consistency**: Follow existing vsclaude patterns for configuration and error handling

## Architecture

### Configuration Structure
Add an optional `docker_network` field to the global configuration:

```json
{
  "port_range": {"min": 8000, "max": 9000},
  "docker_network": "vsclaude-network",  // Optional: Docker network name
  "environment": {...},
  "default_image": "tylercollison2089/vscode-claude:latest"
}
```

### Default Configuration
```json
{
  "port_range": {"min": 8000, "max": 9000},
  "default_profile": "default",
  "ide_address_template": "http://{host}:{port}",
  "environment": {},
  "enabled_volumes": [],
  "include_docker_sock": true,
  "default_image": "tylercollison2089/vscode-claude:latest",
  "docker_network": null  // Default: no network specified
}
```

## Implementation Details

### Modified Files

#### 1. `vsclaude/vsclaude/config.py`
- Add `docker_network` field to `_default_global_config()` method
- Add `get_docker_network()` method to retrieve network configuration

#### 2. `vsclaude/vsclaude/cli.py`
- Modify `start_command()` to pass network configuration to container creation
- Add network validation logic before container creation

#### 3. `vsclaude/vsclaude/docker.py`
- Modify container creation methods to accept optional network parameter
- Add network validation method
- Update error handling for network-related failures

#### 4. `vsclaude/vsclaude/compose.py`
- Update container creation to support network configuration

### Data Flow

1. **Configuration Loading**:
   ```python
   config_manager = ConfigManager()
   global_config = config_manager.load_global_config()
   docker_network = global_config.get("docker_network")
   ```

2. **Network Validation** (if network specified):
   ```python
   if docker_network:
       if not docker_client.network_exists(docker_network):
           print(f"Error: Docker network '{docker_network}' not found")
           print("Please create the network first or remove the 'docker_network' configuration")
           sys.exit(1)
   ```

3. **Container Creation**:
   ```python
   container = docker_client.client.containers.create(
       image=service_config["image"],
       name=container_name,
       ports=port_mapping,
       environment=environment_vars,
       volumes=volumes,
       network=docker_network if docker_network else None,
       detach=True
   )
   ```

### Error Handling

#### Network Validation Errors
- **Error**: Specified Docker network doesn't exist
- **Message**: "Docker network '[name]' not found. Please create the network first or remove the 'docker_network' configuration."
- **Action**: Exit with non-zero status code

#### Network Creation Errors
- **Error**: Network creation fails (if implemented in future)
- **Message**: "Failed to create Docker network '[name]': [error details]"
- **Action**: Exit with non-zero status code

### Testing Strategy

#### Unit Tests
1. **ConfigManager Tests**:
   - Test default configuration includes `docker_network: null`
   - Test loading configuration with network specified
   - Test `get_docker_network()` method

2. **DockerClient Tests**:
   - Test `network_exists()` method
   - Test container creation with network parameter
   - Test error handling for missing networks

3. **CLI Tests**:
   - Test `start_command()` with network configuration
   - Test graceful failure when network doesn't exist
   - Test backward compatibility (no network specified)

#### Integration Tests
1. **Happy Path**: Create container with existing network
2. **Error Path**: Attempt to create container with non-existent network
3. **Default Path**: Create container without network specification

## Security Considerations

- No special validation for network names (as requested)
- Network operations use existing Docker SDK security practices
- Error messages provide clear guidance without exposing sensitive information

## Backward Compatibility

- Existing configurations without `docker_network` field will continue to work unchanged
- Default behavior remains the same (default Docker networking)
- No breaking changes to existing APIs or configuration formats

## Future Enhancements

### Potential Extensions
1. **Network Creation**: Option to automatically create missing networks
2. **Network Configuration**: Support for network driver, subnet, and other options
3. **Multiple Networks**: Support for connecting containers to multiple networks
4. **CLI Override**: Per-instance network override via command-line flag

### Implementation Notes
- Current design focuses on minimal implementation meeting requirements
- Architecture allows for future enhancements without breaking changes
- Simple string-based configuration provides maximum flexibility

## Success Criteria

1. ✅ Containers can be created with specified Docker networks
2. ✅ Graceful failure when specified network doesn't exist
3. ✅ Backward compatibility maintained
4. ✅ Clear error messages for network validation failures
5. ✅ Consistent with existing vsclaude configuration patterns

## Approval

This design has been approved by the user and is ready for implementation.