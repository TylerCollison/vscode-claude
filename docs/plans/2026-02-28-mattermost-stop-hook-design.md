# Claude Code Stop Hook for Mattermost Integration

**Date**: 2026-02-28
**Author**: Claude Code Assistant
**Status**: Approved Design

## Overview

This document outlines the design for a Claude Code Stop hook that sends the last assistant message as a reply to a Mattermost thread when a Claude Code session ends.

## Requirements

- Send the `last_assistant_message` from Claude Code session to Mattermost
- Reply to a specific thread identified by `MM_THREAD_ID` environment variable
- Use existing Mattermost API credentials (`MM_ADDRESS`, `MM_TOKEN`)
- Implement as a standalone script following Claude Code hooks specification
- Handle errors gracefully with proper exit codes

## Architecture

### Components

1. **Hook Configuration** (`.claude/settings.json`)
   - Defines the Stop hook with command execution
   - Points to the standalone script

2. **Script Implementation** (`.claude/hooks/stop-hook.js`)
   - Node.js script that reads Stop hook JSON from stdin
   - Validates environment variables
   - Calls Mattermost API to post reply

3. **Mattermost Integration**
   - Reuses Mattermost API logic from existing bot code
   - Posts replies to threads using thread ID

### Data Flow

```
Claude Code Session → Stop Hook Event → JSON Input → Script Processing → Mattermost API → Thread Reply
```

## Implementation Details

### Hook Configuration

Location: `.claude/settings.json`

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/stop-hook.js"
          }
        ]
      }
    ]
  }
}
```

### Script Implementation

**File**: `.claude/hooks/stop-hook.js`

**Input Format** (JSON received via stdin):
```json
{
  "session_id": "abc123",
  "cwd": "/workspace",
  "hook_event_name": "Stop",
  "last_assistant_message": "Final Claude response..."
}
```

**Environment Variables Required**:
- `MM_THREAD_ID`: Target Mattermost thread ID
- `MM_ADDRESS`: Mattermost server URL
- `MM_TOKEN`: Mattermost bot token

**Script Logic**:
1. Read and parse JSON from stdin
2. Validate required environment variables
3. Extract `last_assistant_message` from input
4. Call Mattermost API to post reply to thread
5. Handle errors and return appropriate exit codes

### Exit Codes
- **0**: Success - message sent successfully
- **1**: Error - failed to send message
- **2**: Block - should not be used for Stop hooks

## Error Handling

- Validate all environment variables exist
- Handle Mattermost API errors gracefully
- Log errors to stderr for debugging
- Return appropriate exit codes

## Dependencies

- Node.js runtime
- `ws` package (already available in project)
- Mattermost server connectivity

## Testing

### Manual Testing
1. Set environment variables
2. Run script manually with test JSON input
3. Verify Mattermost thread receives message

### Integration Testing
1. Configure hook in Claude Code
2. Complete a Claude Code session
3. Verify message appears in Mattermost

## Security Considerations

- Environment variables contain sensitive tokens
- Script should validate input to prevent injection
- Use HTTPS for Mattermost API calls
- Handle errors without exposing sensitive information

## Future Enhancements

- Add message formatting options
- Include session metadata (duration, etc.)
- Support multiple thread destinations
- Add retry logic for failed API calls

## References

- [Claude Code Hooks Guide](https://code.claude.com/docs/en/hooks-guide)
- [Existing Mattermost Bot Code](../mattermost-bot.js)
- [Mattermost API Documentation](https://api.mattermost.com/)