# Mattermost Thread ID Storage Implementation

**Date**: 2026-02-28
**Author**: Claude Code Assistant
**Status**: Approved Design

## Overview

This document outlines the design for storing Mattermost thread IDs in a way that allows cross-process access while maintaining backward compatibility with existing environment variable usage.

## Requirements

- Store thread ID (post ID) from Mattermost API response in a persistent location
- Allow access by other processes (not just child processes)
- Maintain backward compatibility with `MM_THREAD_ID` environment variable
- Implement simple file-based storage solution
- Handle errors gracefully

## Architecture

### Components

1. **Thread ID Storage** (`/tmp/mm_thread_id`)
   - Temporary file accessible by all processes
   - Contains the post ID from Mattermost API response
   - Simple text format with just the thread ID

2. **Initial Post Script** (`mattermost-initial-post.sh`)
   - Modified to write thread ID to file after successful post
   - Maintains existing functionality

3. **Stop Hook Script** (`.claude/hooks/stop-hook.js`)
   - Updated to read thread ID from file first
   - Falls back to `MM_THREAD_ID` environment variable
   - Maintains backward compatibility

### Data Flow

```
Mattermost API Response → mattermost-initial-post.sh → /tmp/mm_thread_id
                                     ↓
stop-hook.js → Read /tmp/mm_thread_id → Fallback to MM_THREAD_ID env var → Post reply
```

## Implementation Details

### File-Based Storage

**Location:** `/tmp/mm_thread_id`

**Content Format:** Plain text containing only the thread ID

**Example:**
```
abc123def456
```

### Initial Post Script Modifications

**File:** `mattermost-initial-post.sh`

**Changes:**
1. After successful post (line 149), extract `post_id` from API response
2. Write `post_id` to `/tmp/mm_thread_id`
3. Add error handling for file write operations

**Code Addition:**
```bash
# After successful post, write thread ID to file
if [ -n "$post_id" ] && [ "$post_id" != "null" ] && [ "$post_id" != "" ]; then
    log "Message posted successfully with ID: $post_id"

    # Write thread ID to file for cross-process access
    echo "$post_id" > /tmp/mm_thread_id
    if [ $? -eq 0 ]; then
        log "Thread ID written to /tmp/mm_thread_id: $post_id"
    else
        log "WARNING: Failed to write thread ID to file"
    fi
fi
```

### Stop Hook Script Modifications

**File:** `.claude/hooks/stop-hook.js`

**Changes:**
1. Add file reading logic before environment variable fallback
2. Implement fallback mechanism
3. Update error handling

**Updated Logic:**
```javascript
// Get thread ID from file first, then fallback to environment variable
function getThreadId() {
    // Try to read from file
    try {
        const threadIdFile = '/tmp/mm_thread_id';
        if (fs.existsSync(threadIdFile)) {
            const threadId = fs.readFileSync(threadIdFile, 'utf8').trim();
            if (threadId) {
                console.log(`Using thread ID from file: ${threadId}`);
                return threadId;
            }
        }
    } catch (error) {
        console.log('Could not read thread ID from file, falling back to environment variable');
    }

    // Fallback to environment variable
    const threadId = process.env.MM_THREAD_ID;
    if (!threadId) {
        throw new Error('Thread ID not found in file or MM_THREAD_ID environment variable');
    }

    console.log(`Using thread ID from environment variable: ${threadId}`);
    return threadId;
}
```

## Error Handling

### Initial Post Script
- File write failures are logged as warnings
- Script continues execution (non-fatal)
- Existing functionality remains intact

### Stop Hook Script
- File read failures trigger fallback to environment variable
- Both file and environment variable failures result in error
- Appropriate error messages for debugging

## Testing

### Test Scenarios
1. **File exists:** Stop hook reads from `/tmp/mm_thread_id`
2. **File missing:** Stop hook falls back to `MM_THREAD_ID` environment variable
3. **Both missing:** Stop hook reports appropriate error
4. **Initial post:** Script successfully writes thread ID to file

### Manual Testing
```bash
# Test file write
./mattermost-initial-post.sh
cat /tmp/mm_thread_id

# Test stop hook with file
MM_THREAD_ID=fallback_value node .claude/hooks/stop-hook.js

# Test stop hook without file
rm /tmp/mm_thread_id
MM_THREAD_ID=env_value node .claude/hooks/stop-hook.js
```

## Security Considerations

- `/tmp` directory provides adequate isolation
- File permissions allow global read (intentional for cross-process access)
- No sensitive information stored in the file
- Environment variable fallback maintains existing security model

## Backward Compatibility

- ✅ Existing `MM_THREAD_ID` environment variable usage continues to work
- ✅ No breaking changes to current functionality
- ✅ Gradual migration path available
- ✅ Both mechanisms can coexist

## Future Enhancements

- Add file cleanup logic for multiple containers
- Consider persistent storage location for production use
- Add file locking for concurrent access scenarios
- Support multiple thread IDs for different channels

## References

- [Existing Mattermost Stop Hook Design](../2026-02-28-mattermost-stop-hook-design.md)
- [Mattermost Bot Implementation](../../mattermost-bot.js)
- [Linux Temporary Files Documentation](https://man7.org/linux/man-pages/man5/tmpfs.5.html)