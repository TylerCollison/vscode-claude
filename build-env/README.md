# build-env

A standalone Python tool that provides persistent Docker container environments for build commands.

## Overview

`build-env` creates and manages persistent Docker containers where build commands can be executed. This ensures consistent build environments across different development machines and CI/CD pipelines.

## Features

- **Persistent containers**: Containers remain running between build commands
- **Environment isolation**: Each workspace gets its own dedicated container
- **Bidirectional synchronization**: Files are synchronized both from host to container and from container to host
- **Security filtering**: Only safe environment variables are passed to containers
- **Automatic cleanup**: Containers can be shutdown cleanly
- **Docker image validation**: Ensures only valid Docker images are used

## Installation

### Prerequisites

- Python 3.8+
- Docker Engine
- Docker Python SDK (`docker` package)

Note: The package installs the `docker` dependency automatically via `requirements.txt`

### From Source

```bash
# Clone the repository
git clone https://github.com/anthropic/cconx.git
cd cconx/build-env

# Install in development mode
pip install -e .

# Or install directly
pip install .
```

### Usage

```bash
# Set required environment variables
export BUILD_CONTAINER="python:3.12-slim"
export DEFAULT_WORKSPACE="/path/to/workspace"

# Run a command in the build environment
build-env python --version

# Run multiple commands
build-env npm install
build-env npm run build

# Shutdown the build environment container
build-env --exit
```

## Environment Variables

### Required

- `BUILD_CONTAINER`: Docker image to use for the build environment
- `DEFAULT_WORKSPACE`: Path to the workspace directory

### Optional

- Any other environment variables you want to pass to the container (filtered for security)
- Environment variables starting with `BUILD_` will be passed through safely

## Configuration

### Docker Images

The build environment uses Docker images specified via the `BUILD_CONTAINER` environment variable. Common images include:

- `python:3.12-slim` for Python projects
- `node:18-alpine` for Node.js projects
- `golang:1.21` for Go projects

### Bidirectional Synchronization

When running in Docker-in-Docker scenarios, the tool provides bidirectional file synchronization:

- **Host to Container**: Files are copied from the host workspace to the container before command execution
- **Container to Host**: After command execution, any changes made in the container are copied back to the host workspace
- **Automatic**: Synchronization happens automatically for Docker-in-Docker scenarios
- **Complete**: All files in the workspace directory are synchronized in both directions

### Security

The tool filters environment variables passed to containers to prevent exposure of sensitive information:

- **Safe environment variables**: `PATH`, `HOME`, `USER`, `PWD`, `SHELL`, `TERM`, `LANG`, `LC_ALL`, `BUILD_CONTAINER`, `DEFAULT_WORKSPACE`
- **Always filtered**: Environment variables containing "SECRET", "KEY", "PASSWORD", "TOKEN" patterns
- **Allowed patterns**: Variables starting with `BUILD_` are passed through
- **Docker image validation**: Ensures image names follow safe patterns
- **Container isolation**: Unique containers per workspace based on UUID generation

## Development

### Project Structure

```
build-env/
├── build_env.py          # Core build environment manager
├── build_env_cli.py      # CLI entry point
├── security.py          # Security utilities
├── setup.py            # Installation script
├── requirements.txt    # Dependencies
├── tests/              # Test suite
└── README.md           # This file
```

### Running Tests

```bash
# Install test dependencies
pip install -e .[test]

# Run tests
pytest
```

### Building and Distribution

```bash
# Build package
python setup.py sdist bdist_wheel

# Install locally
pip install dist/build_env-0.1.0-py3-none-any.whl
```

## License

This project is part of the cconx toolset. See the main repository for licensing information.

## Contributing

Please follow the contribution guidelines in the main cconx repository.

## Support

For issues and feature requests, please create an issue in the main cconx repository.