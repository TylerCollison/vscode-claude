# vsclaude - VS Code + Claude Docker Management Tool

A Python tool for managing VS Code + Claude Docker containers with automated port allocation and multi-instance support.

## Installation

```bash
./install.sh
source venv/bin/activate
```

## Usage Examples

```bash
# Start instance with auto port allocation
vsclaude start my-project --port-auto

# Start with custom environment variables
vsclaude start my-project --port 8443 --env PASSWORD=secret --env CUSTOM_VAR=value

# Check status (shows full IDE links)
vsclaude status

# Stop instance
vsclaude stop my-project
```

## Configuration

vsclaude stores its configuration files in the user's home directory.

### Configuration Files Location

**Primary Configuration Directory:** `~/.vsclaude/`

**Main Configuration File:** `~/.vsclaude/global-config.json`

### Default Configuration

When vsclaude first runs, it creates a default configuration file:

```json
{
    "port_range": {"min": 8000, "max": 9000},
    "default_profile": "default",
    "ide_address_template": "http://localhost:{port}"
}
```

### Editing Configuration

Users can edit the configuration file directly:

```bash
# Edit global configuration
nano ~/.vsclaude/global-config.json

# Or use any text editor
code ~/.vsclaude/global-config.json
```

### Configuration Options

- **port_range**: Defines the range of ports available for auto-allocation
- **default_profile**: Sets the default profile name for new instances
- **ide_address_template**: Template for generating IDE access URLs (uses `{port}` placeholder)

### Instance-Specific Configurations

Each vsclaude instance creates its own configuration in:
`~/.vsclaude/{instance-name}/config.json`

These files contain instance-specific settings like port numbers, environment variables, and instance metadata.