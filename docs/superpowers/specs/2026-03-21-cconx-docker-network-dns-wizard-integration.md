# cconx Docker Network and DNS Servers Wizard Integration Design Specification

## Overview

This document specifies the design for integrating `docker_network` and `dns_servers` configuration fields into the existing cconx setup wizard.

## Purpose

Add interactive configuration for Docker network and DNS servers settings to the cconx setup wizard, allowing users to configure these advanced Docker container settings through an intuitive interface.

## Current State Analysis

- `docker_network` and `dns_servers` fields are already implemented in ConfigManager
- CLI supports DNS configuration via `--dns` flags
- Docker network validation exists in CLI startup
- Wizard currently handles: port_range, default_image, include_docker_sock, environment, enabled_volumes

## Requirements

### Docker Network Configuration
- Default: `None` (empty) = use Docker's default bridge network
- Support special values: `host`, `none`
- Validate network name format
- Check if network exists
- Offer to create network if it doesn't exist

### DNS Servers Configuration
- Default: `None` (empty list) = use Docker defaults
- Multi-line input for multiple DNS servers
- IP address validation
- Filter invalid entries with warnings

## Architecture

### New Field Handler Classes

#### DockerNetworkFieldHandler
- Extends `FieldHandler` base class
- Validates Docker network name format
- Checks network existence using Docker client
- Offers network creation if not found
- Handles special values: `host`, `none`

#### DnsServersFieldHandler
- Extends `FieldHandler` base class
- Multi-line input similar to `VolumesFieldHandler`
- IP address validation using `ipaddress` module
- Empty list handling for Docker defaults

### Integration Points

#### Wizard Registration
Add to `setup_command()` in `cli.py`:
```python
wizard.register_field_handler("docker_network", DockerNetworkFieldHandler())
wizard.register_field_handler("dns_servers", DnsServersFieldHandler())
```

#### Field Order
Place after `include_docker_sock` and before `environment` for logical flow:
1. port_range
2. default_image
3. ide_address_template
4. include_docker_sock
5. docker_network
6. dns_servers
7. environment
8. enabled_volumes

## Implementation Details

### DockerNetworkFieldHandler Implementation

```python
class DockerNetworkFieldHandler(FieldHandler):
    def __init__(self, field_name: str = "docker_network"):
        super().__init__(field_name)

    def prompt(self, current_value: Any) -> Any:
        print("=== DOCKER NETWORK ===")
        print("Description: Docker network name for container instances")
        print("Leave empty to use Docker's default bridge network")
        print("Options: 'host' for host networking, 'none' for no networking")

        current_display = current_value if current_value else "(empty) - using default bridge network"
        print(f"Current value: {current_display}")

        while True:
            user_input = input("Enter network name (empty for default, 'host', 'none', or custom): ").strip()

            # Handle empty input (use default)
            if not user_input:
                return ""

            # Handle special values
            if user_input in ["host", "none"]:
                return user_input

            # Validate format
            if not self._validate_network_format(user_input):
                print("Invalid network name format. Use alphanumeric characters, hyphens, or underscores.")
                continue

            # Check network existence
            if not self._network_exists(user_input):
                create = input(f"Network '{user_input}' not found. Create it? (yes/no): ").lower().strip()
                if create in ["yes", "y"]:
                    if self._create_network(user_input):
                        return user_input
                    else:
                        print("Failed to create network. Please try again.")
                        continue
                else:
                    print("Network creation cancelled. Please choose a different network.")
                    continue

            return user_input
```

### DnsServersFieldHandler Implementation

```python
class DnsServersFieldHandler(FieldHandler):
    def __init__(self, field_name: str = "dns_servers"):
        super().__init__(field_name)

    def prompt(self, current_value: Any) -> Any:
        print("=== DNS SERVERS ===")
        print("Description: Custom DNS servers for container instances")
        print("Enter one IP address per line, empty line when finished")
        print("Leave empty to use Docker's default DNS servers")

        current_display = current_value if current_value else "(empty) - using Docker defaults"
        print(f"Current value: {current_display}")

        dns_servers = []
        print("Enter DNS server IP addresses:")

        line_num = 1
        while True:
            user_input = input(f"{line_num}. ").strip()

            if not user_input:
                break

            if self._validate_ip_address(user_input):
                dns_servers.append(user_input)
                print(f"Added: {user_input}")
                line_num += 1
            else:
                print(f"Invalid IP address: {user_input}. Please enter a valid IPv4 or IPv6 address.")

        return dns_servers if dns_servers else []
```

## Validation Rules

### Docker Network Validation
- **Format**: `^[a-zA-Z0-9][a-zA-Z0-9_.-]*$` (Docker network naming rules)
- **Special Values**: `host`, `none` always valid
- **Existence Check**: Use Docker client to check if network exists
- **Creation**: Offer to create network if it doesn't exist

### DNS Servers Validation
- **IP Validation**: Valid IPv4 or IPv6 addresses
- **Empty List**: Allowed (use Docker defaults)
- **Invalid Entries**: Filtered out with warnings

## User Interaction Flow

### Docker Network Configuration
1. Display current value and explanation
2. Prompt for network name with options
3. Validate format
4. Check network existence
5. If not found, offer to create
6. Return validated network name

### DNS Servers Configuration
1. Display current value and explanation
2. Prompt for IP addresses one per line
3. Validate each IP address
4. Empty line to finish
5. Return list of valid IPs

## Error Handling

### Docker Network Errors
- Invalid format: Clear error message with format requirements
- Network not found: Offer creation or retry
- Creation failure: Inform user and allow retry

### DNS Servers Errors
- Invalid IP: Clear error message with example
- Empty list: Use Docker defaults

## Testing Strategy

### Unit Tests
- Test Docker network format validation
- Test DNS IP address validation
- Test empty/default value handling
- Test network existence checking

### Integration Tests
- Test full wizard flow with new fields
- Test network creation functionality
- Test DNS configuration in container startup

## Backward Compatibility

### Existing Configurations
- Preserve existing `docker_network` and `dns_servers` values
- Empty values default to Docker behavior
- No breaking changes to existing functionality

### Field Changes
- Add new fields to default configuration
- Handle missing fields in old configs
- Maintain compatibility with existing instances

## Security Considerations

### Network Creation
- Only create networks with user confirmation
- Use appropriate network drivers
- Clear warnings about network implications

### DNS Configuration
- Validate DNS server IPs to prevent misconfiguration
- Clear documentation about security implications

## Performance Considerations

### Network Existence Checking
- Network checks require Docker API calls
- Cache results during wizard session
- Fast failure for invalid network names

### DNS Validation
- IP validation is lightweight
- Real-time validation provides good UX

## Success Criteria

### Functional
- Users can configure Docker network through wizard
- Users can configure DNS servers through wizard
- Network existence checking works correctly
- DNS IP validation prevents misconfiguration

### User Experience
- Clear explanations and helpful defaults
- Intuitive multi-line input for DNS servers
- Graceful error handling and recovery

### Technical
- Code follows existing patterns
- Integration with Docker client
- Proper error handling and validation

## Implementation Plan

### Phase 1: Field Handler Implementation
- Implement `DockerNetworkFieldHandler`
- Implement `DnsServersFieldHandler`
- Add unit tests

### Phase 2: Wizard Integration
- Register handlers in `setup_command()`
- Update field order
- Add integration tests

### Phase 3: Validation & Polish
- Test network creation functionality
- Test DNS configuration in containers
- Refine error messages and UX