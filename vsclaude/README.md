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
    "ide_address_template": "http://localhost:{port}",
    "environment": {}
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
- **environment**: Global environment variables applied to all instances

### Global Environment Configuration

vsclaude supports global environment variables that are automatically applied to all instances. These variables can be overridden by instance-specific settings.

**Example global-config.json with environment field:**

```json
{
    "port_range": {"min": 8000, "max": 9000},
    "default_profile": "default",
    "ide_address_template": "http://localhost:{port}",
    "environment": {
        "GLOBAL_API_KEY": "shared-secret-key",
        "DEFAULT_THEME": "dark",
        "SHARED_CONFIG": "global-setting",
        "COMMON_VAR": "applied-to-all-instances"
    }
}
```

### Environment Variable Priority

vsclaude merges environment variables with the following priority (instance-specific overrides global):

1. **Global Environment**: Variables defined in `environment` field of global config
2. **Instance Environment**: Variables passed via `--env` flag when starting an instance
3. **Merging**: Instance variables override global settings with same names

**Example Override Behavior:**

```bash
# When global config has:
# {"environment": {"GLOBAL_VAR": "global", "SHARED": "global-version"}}

# Command:
vsclaude start test --env SHARED=instance-version --env INSTANCE_ONLY=instance-value

# Resulting environment:
{
    "GLOBAL_VAR": "global",           # From global (no override)
    "SHARED": "instance-version",     # From instance (overrides global)
    "INSTANCE_ONLY": "instance-value"  # Instance-only variable
}
```

**Usage Examples:**

```bash
# Start instance with global environment only
vsclaude start my-project --port-auto

# Start instance overriding specific global variables
vsclaude start my-project --port 8443 --env DEFAULT_THEME=light --env API_KEY="custom-key"

# Start instance with additional instance-specific variables
vsclaude start my-project --env INSTANCE_ONLY_VAR="value"
```

### MM_CHANNEL Auto-population

vsclaude automatically populates the `MM_CHANNEL` environment variable with the instance name, unless overridden by higher priority settings:

**Priority Order (Highest to Lowest):**
1. `--env MM_CHANNEL=value` (user override via CLI)
2. Global config `MM_CHANNEL` setting
3. Instance name auto-population (fallback)

**Examples:**

```bash
# Auto-population: MM_CHANNEL="my-project"
vsclaude start my-project

# User override: MM_CHANNEL="custom-channel"
vsclaude start my-project --env MM_CHANNEL=custom-channel

# Global config: MM_CHANNEL="global-channel" (if set in global-config.json)
vsclaude start my-project
```

### Instance-Specific Configurations

Each vsclaude instance creates its own configuration in:
`~/.vsclaude/{instance-name}/config.json`

These files contain instance-specific settings like port numbers, environment variables, and instance metadata.