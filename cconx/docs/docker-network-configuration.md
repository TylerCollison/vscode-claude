# Docker Network Configuration

cconx now supports optional Docker network configuration for container instances.

## Configuration

Add a `docker_network` field to your global configuration:

```json
{
  "port_range": {"min": 8000, "max": 9000},
  "docker_network": "my-custom-network",
  "environment": {...}
}
```

## Behavior

- **Network specified**: Containers are created on the specified Docker network
- **Network doesn't exist**: cconx exits gracefully with clear error message
- **No network specified**: Default Docker networking behavior

## Example

```bash
# Create a Docker network first
docker network create cconx-network

# Update global config with network
cat > ~/.cconx/global-config.json << EOF
{
  "port_range": {"min": 8000, "max": 9000},
  "docker_network": "cconx-network",
  "environment": {
    "PUID": "0",
    "PGID": "0"
  }
}
EOF

# Start instance - will use the specified network
cconx start my-instance
```

## Implementation Details

The Docker network configuration is implemented with the following features:

### Configuration Management

- Added `docker_network` field to `ConfigManager` class
- Default value is `None` for backward compatibility
- Existing configurations without the field continue to work unchanged

### Network Validation

- Before container creation, validates that the specified network exists
- Provides clear error message if network is missing
- Uses `DockerClient.network_exists()` method to check network availability

### Container Network Assignment

- Containers are created with the `network` parameter when a network is specified
- Uses Docker SDK's `network` parameter during container creation
- Falls back to default Docker networking when no network is specified

### Error Handling

- Graceful exit with informative error message when network validation fails
- Prevents container creation on non-existent networks
- Maintains backward compatibility with existing deployments

## Technical Architecture

```
ConfigManager.load_global_config()
    ↓
ConfigManager.get_docker_network()
    ↓
DockerClient.network_exists(network_name)
    ↓
Docker SDK container.create(network=network_name)
```

## Backward Compatibility

- Existing configurations without `docker_network` field work unchanged
- No impact on running containers or existing setups
- The field is optional and defaults to `None`

## Security Considerations

- Network names are validated through Docker's security mechanisms
- Only existing Docker networks can be specified
- No network injection vulnerabilities through proper input validation

## Testing

Comprehensive test coverage includes:

- Default network value (None)
- Network existence validation
- Error handling for non-existent networks
- Backward compatibility with legacy configurations

See the test files for detailed test cases:
- `tests/test_config.py` - Configuration management tests
- `tests/test_docker.py` - Docker client integration tests