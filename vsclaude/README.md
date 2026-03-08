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