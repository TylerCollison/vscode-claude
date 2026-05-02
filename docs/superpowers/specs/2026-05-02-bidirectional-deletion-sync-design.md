# Bidirectional Deletion Synchronization Design

## Overview
This design specifies the implementation of proper bidirectional file deletion synchronization for the build-env tool. The goal is to ensure that files deleted on one side (host or container) are properly deleted on the other side before command execution.

## Current State Analysis
- The build-env tool currently uses simple `docker cp` commands for synchronization
- While bidirectional sync exists, it doesn't properly handle file deletions
- The `_synchronize_workspace_bidirectional` method exists but is complex and not fully functional

## Design Approach: Enhanced Simple Sync

### Core Principles
1. **Delete then copy**: Always delete files that exist in destination but not source before copying
2. **Minimal complexity**: Build on existing simple sync methods rather than complex bidirectional algorithms
3. **Performance focus**: Avoid unnecessary file comparisons when possible

### Implementation Strategy

#### Phase 1: Host → Container Sync (Before Command Execution)
```
1. Get list of files in container workspace
2. Get list of files in host workspace
3. Delete files in container that don't exist on host
4. Copy files from host to container
```

#### Phase 2: Container → Host Sync (After Command Execution)
```
1. Get list of files in container workspace
2. Get list of files in host workspace
3. Delete files on host that don't exist in container
4. Copy files from container to host
```

### Technical Implementation

#### Modified Methods
- `_synchronize_host_to_container()`: Enhanced to handle deletions
- `_synchronize_container_to_host()`: Enhanced to handle deletions

#### New Helper Methods
- `_get_file_list()`: Get recursive file list from directory
- `_delete_files_in_destination()`: Delete files that exist in destination but not source

### File Comparison Strategy
- Use simple filename-based comparison for efficiency
- Skip `.build-env/` directories to avoid UUID contamination
- Handle both files and directories recursively

### Error Handling
- Continue sync even if individual file operations fail
- Log errors but don't halt execution
- Provide debug output for troubleshooting

### Testing Strategy
- Test file creation/deletion synchronization
- Test nested directory structures
- Test edge cases (empty directories, symlinks)
- Verify existing functionality remains intact

## Integration Points
- Replace current simple `docker cp` calls with enhanced sync methods
- Maintain existing debug logging for transparency
- Ensure backward compatibility with existing workflows

## Success Criteria
- Files deleted on host are deleted in container before command execution
- Files deleted in container are deleted on host after command execution
- No performance regression in sync operations
- All existing functionality continues to work