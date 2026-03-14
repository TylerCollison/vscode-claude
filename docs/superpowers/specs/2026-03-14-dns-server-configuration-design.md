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

### Component Changes

#### 1. ConfigManager (`/workspace/cconx/cconx/config.py`)
- **New method**: `get_dns_servers() -> Optional[List[str]]`
- **New method**: `_validate_dns_servers(dns_servers: List[str]) -> List[str]`
- **Updated**: `_default_global_config()` to include `"dns_servers": None`

#### 2. CLI (`/workspace/cconx/cconx/cli.py`)
- **New CLI flag**: `--dns` (multiple flags supported)
- **DNS handling**: Merge global config with CLI overrides
- **Container creation**: Pass validated DNS servers to Docker SDK

#### 3. Testing (`/workspace/cconx/tests/test_config.py`)
- **New tests**: DNS configuration loading and validation
- **New tests**: CLI DNS flag functionality
- **New tests**: Container DNS configuration

## Implementation Details

### DNS Configuration Flow
1. **Global Configuration**: Load DNS servers from `~/.cconx/global-config.json`
2. **CLI Override**: Apply `--dns` flags if provided
3. **Validation**: Validate IP addresses, skip invalid entries
4. **Docker Integration**: Pass validated DNS servers to container creation

### Priority Order
1. CLI `--dns` flags (highest priority)
2. Global configuration `dns_servers`
3. Docker defaults (lowest priority)

### Validation Rules
- **IP Format**: Basic IPv4/IPv6 validation using `ipaddress` module
- **Empty Lists**: Treated as "use Docker defaults"
- **Invalid Entries**: Skip with warning, continue with valid servers

### Error Handling
- **Invalid DNS servers**: Skip with warning message
- **Network issues**: DNS resolution failures handled by Docker/OS
- **Missing configuration**: Default to Docker behavior

## Backward Compatibility
- Existing configurations continue working without DNS settings
- No breaking changes to existing functionality
- Optional feature - can be enabled gradually

## Security Considerations
- Basic IP address validation prevents injection attacks
- No network connectivity testing (let Docker handle it)
- Input sanitization for CLI arguments

## Testing Strategy
- Unit tests for configuration loading and validation
- Integration tests for CLI DNS flag functionality
- Mock Docker client tests for DNS configuration

## Files Modified
1. `/workspace/cconx/cconx/config.py` - DNS configuration methods
2. `/workspace/cconx/cconx/cli.py` - CLI integration and Docker creation
3. `/workspace/cconx/tests/test_config.py` - Test coverage

## Success Criteria
- Users can configure DNS servers globally
- Users can override DNS per instance via CLI
- Invalid DNS servers are skipped with warnings
- Backward compatibility is maintained
- Tests pass for new functionality