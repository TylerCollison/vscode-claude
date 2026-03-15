# DNS Server Configuration Design

## Overview
This document outlines the design for adding DNS server configuration capability to ClaudeConX (cconx), allowing users to specify custom DNS servers for Docker containers similar to Docker's `--dns` flag functionality.

## Requirements
- Configure DNS servers globally via `~/.cconx/global-config.json`
- Allow per-instance DNS override via CLI `--dns` flags
- Support multiple DNS servers
- Maintain backward compatibility
- Basic IP address validation

## Architecture

### Configuration Structure
```json
{
  "port_range": {"min": 8000, "max": 9000},
  "default_profile": "default",
  "docker_network": null,
  "dns_servers": ["8.8.8.8", "1.1.1.1"]
}
```

**Note**: Empty array `[]` vs `null` distinction:
- `null`: Use Docker defaults (no DNS override)
- `[]`: Explicitly use Docker defaults (empty DNS list)
- `["8.8.8.8"]`: Use specified DNS servers

### Component Changes

#### 1. ConfigManager (`/workspace/cconx/cconx/config.py`)
- **New method**: `get_dns_servers() -> Optional[List[str]]`
- **New method**: `_validate_dns_servers(dns_servers: List[str]) -> List[str]`
- **Updated**: `_default_global_config()` to include `"dns_servers": None`

#### 2. CLI (`/workspace/cconx/cconx/cli.py`)
- **New CLI flag**: `--dns` (multiple flags supported via `action="append"`)
- **DNS handling**: CLI flags override global configuration
- **Container creation**: Pass validated DNS servers to Docker SDK's `dns` parameter
- **CLI argument**: `start_parser.add_argument("--dns", action="append", help="DNS server IP address")`

#### 3. Testing (`/workspace/cconx/tests/test_config.py`)
- **New tests**: DNS configuration loading and validation
- **New tests**: CLI DNS flag functionality
- **New tests**: Container DNS configuration

## Implementation Details

### DNS Configuration Flow
1. **Global Configuration**: Load DNS servers from `~/.cconx/global-config.json`
2. **CLI Override**: Apply `--dns` flags if provided (CLI overrides global config)
3. **Network Mode Check**: Skip DNS configuration if `network` parameter is `"host"` or `"none"`
4. **Validation**: Validate IP addresses using `ipaddress.ip_address()` with try/catch, skip invalid entries with warning
5. **Docker Integration**: Pass validated DNS servers to `docker_client.client.containers.create(dns=validated_dns_servers)`

### Container Creation Syntax
```python
container_params = {
    "image": service_config["image"],
    "name": container_name,
    "ports": port_mapping,
    "environment": env_dict,
    "volumes": service_config["volumes"],
    "network": docker_network if docker_network else None,
    "detach": True
}

# Add DNS if configured and network mode allows it
if dns_servers and validated_dns_servers and docker_network not in ["host", "none"]:
    container_params["dns"] = validated_dns_servers

container = docker_client.client.containers.create(**container_params)
```

### Priority Order
1. CLI `--dns` flags (highest priority)
2. Global configuration `dns_servers`
3. Docker defaults (lowest priority)

### Validation Rules
- **IP Format**: Basic IPv4/IPv6 validation using `ipaddress.ip_address()` with try/catch
- **Empty Lists**: Treated as "use Docker defaults"
- **Invalid Entries**: Skip with warning, continue with valid servers
- **Duplicates**: Keep duplicates (Docker handles this internally)
- **Ordering**: Maintain user-specified order
- **Mixed Types**: Support both IPv4 and IPv6 addresses

### Error Handling
- **Invalid DNS servers**: Skip with warning message to stdout
- **Network issues**: DNS resolution failures handled by Docker/OS
- **Missing configuration**: Default to Docker behavior
- **Network mode conflicts**: DNS settings ignored when using `host` or `none` network modes
- **Docker API errors**: Handle gracefully, fall back to default DNS behavior
- **Validation failures**: Continue with valid servers, skip invalid ones

## Backward Compatibility
- Existing configurations continue working without DNS settings
- No breaking changes to existing functionality
- Optional feature - can be enabled gradually

## Security Considerations
- Basic IP address validation prevents injection attacks
- No network connectivity testing (let Docker handle it)
- Input sanitization for CLI arguments
- Private/reserved IP ranges allowed (local DNS servers)
- DNS poisoning prevention via Docker's internal handling

## Testing Strategy
- Unit tests for configuration loading and validation
- Integration tests for CLI DNS flag functionality
- Mock Docker client tests for DNS configuration
- Test cases:
  - CLI `--dns` flag override
  - Invalid DNS server handling
  - Empty DNS server list behavior
  - Docker default fallback
  - Network mode compatibility (`host`, `none`, custom networks)
  - Mixed IPv4/IPv6 addresses
  - Duplicate DNS server handling
  - Docker API error handling

## Files Modified
1. `/workspace/cconx/cconx/config.py` - DNS configuration methods
2. `/workspace/cconx/cconx/cli.py` - CLI integration and Docker creation
3. `/workspace/cconx/tests/test_config.py` - Test coverage
4. `/workspace/cconx/cconx/docker.py` - DNS parameter handling

## Success Criteria
- Users can configure DNS servers globally
- Users can override DNS per instance via CLI
- Invalid DNS servers are skipped with warnings
- Backward compatibility is maintained
- Tests pass for new functionality
- DNS settings respect network mode compatibility
- Both IPv4 and IPv6 addresses are supported