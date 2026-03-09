# Delete Command Design Document

## Overview
This document outlines the design for implementing a `delete` command in the vsclaude CLI that provides transactional deletion of container instances and their configuration files.

## Requirements
- Delete both Docker container and configuration files
- Handle running containers by stopping them first
- Transactional approach: avoid leaving system in inconsistent state
- Best-effort cleanup with comprehensive error reporting
- No user confirmation required

## Architecture

### Command Structure
```bash
vsclaude delete <instance_name>
```

### Transactional Flow
1. **Check Container Status** - Determine if container exists and is running
2. **Stop Container** - If running, stop the container first
3. **Delete Configuration** - Remove instance configuration files
4. **Remove Container** - Delete the Docker container
5. **Report Results** - Provide detailed success/failure status

### Components

#### 1. CLI Registration (`vsclaude/cli.py`)
- Add `delete` subcommand to argument parser
- Implement `delete_command(args)` function

#### 2. InstanceManager Extension (`vsclaude/instances.py`)
- Add `delete_instance(name)` method
- Returns detailed status object

#### 3. DockerClient Enhancement (`vsclaude/docker.py`)
- Add `remove_container(container_name)` method
- Integrate with existing `stop_container()` method

### Error Handling Strategy

#### Success Scenarios
- **Container running**: Stop → Delete config → Remove container → All succeed
- **Container stopped**: Delete config → Remove container → All succeed
- **Container missing**: Delete config → Succeeds
- **Config missing**: Remove container → Succeeds

#### Failure Scenarios
- **Stop fails**: Don't proceed with deletion, report error
- **Config deletion fails**: Container remains stopped, report partial failure
- **Container removal fails**: Config deleted, container remains stopped

### Data Structures

#### Return Type
```python
{
    "container_stopped": bool,    # Whether container was stopped (if running)
    "container_removed": bool,    # Whether container was removed
    "config_deleted": bool        # Whether config was deleted
}
```

## Implementation Plan

### Phase 1: Core Functionality
1. Add `remove_container()` method to DockerClient
2. Add `delete_instance()` method to InstanceManager
3. Implement `delete_command()` in CLI

### Phase 2: Error Handling
1. Implement transactional logic
2. Add comprehensive error reporting
3. Handle edge cases

### Phase 3: Testing
1. Unit tests for each component
2. Integration tests for end-to-end scenarios
3. Edge case testing

## Testing Strategy

### Unit Tests
- Container removal functionality
- Configuration deletion
- Error scenarios

### Integration Tests
- Full transactional flow
- Various container/config states
- Permission and network failures

## Security Considerations
- Container name validation (reuse existing patterns)
- Safe path handling for config deletion
- Permission checks

## Future Enhancements
- Batch deletion (multiple instances)
- Dry-run mode
- Force deletion flag (skip container stop)

## Success Criteria
- Command successfully deletes both container and config
- Handles all expected error scenarios gracefully
- Maintains system consistency
- Provides clear status reporting