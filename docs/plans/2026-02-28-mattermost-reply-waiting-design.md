# Mattermost Reply Waiting Stop Hook Design

**Date**: 2026-02-28
**Author**: Claude Code Assistant
**Status**: Design Approved

## Overview

This document outlines the design for enhancing the Claude Code Stop Hook to wait for Mattermost replies from users and use JSON hook responses to block session termination when replies are received.

## Requirements

- Wait for non-bot replies in the Mattermost thread when stop hook is triggered
- Filter out replies from the bot itself using user ID comparison
- Use Claude Code JSON hook response format with `decision` and `reason` fields
- Implement configurable timeout for reply waiting
- Maintain backward compatibility with existing stop hook functionality

## Architecture

### Components

1. **Enhanced Stop Hook** (`.claude/hooks/stop-hook.js`)
   - Modified to include reply waiting logic
   - Polls Mattermost API for thread replies
   - Filters bot replies using user ID comparison
   - Returns JSON hook responses when blocking

2. **Reply Detection System**
   - Uses `GET /api/v4/posts/{thread_id}/thread` endpoint
   - Polls periodically for new replies
   - Filters by `user_id` to exclude bot posts

3. **Configuration System**
   - Environment variables for timeout and bot detection
   - Default values for backward compatibility

### Data Flow

```
Stop Hook Triggered →
Read Input & Validate →
Get Thread ID →
Start Reply Polling →
Filter Replies (exclude bot) →
Timeout Reached → Return Success (send final message)
OR
User Reply Found → Return JSON Block Response
```

## Implementation Details

### Hook Configuration

**Location**: `.claude/settings.json` (no changes needed)

### Enhanced Stop Hook Implementation

**File**: `.claude/hooks/stop-hook.js`

#### New Environment Variables

```javascript
// Timeout for waiting replies (milliseconds)
const REPLY_TIMEOUT_MS = parseInt(process.env.MM_REPLY_TIMEOUT_MS) || 86400000; // 24 hours

// Bot user ID for filtering (optional - can be auto-detected)
const BOT_USER_ID = process.env.MM_BOT_USER_ID;
```

#### New Methods

```javascript
class StopHook {
    // ... existing methods ...

    async waitForUserReply() {
        const startTime = Date.now();
        let lastCheckedPostId = await this.getLatestPostId();

        while (Date.now() - startTime < REPLY_TIMEOUT_MS) {
            const replies = await this.getThreadReplies();
            const userReply = this.findUserReply(replies, lastCheckedPostId);

            if (userReply) {
                return userReply;
            }

            lastCheckedPostId = this.getLatestPostIdFromReplies(replies);
            await this.sleep(2000); // Poll every 2 seconds
        }

        return null; // No reply within timeout
    }

    async getThreadReplies() {
        // Call GET /api/v4/posts/{thread_id}/thread
        // Return array of reply posts
    }

    findUserReply(replies, lastCheckedPostId) {
        const newReplies = replies.filter(post =>
            post.id > lastCheckedPostId &&
            !this.isBotReply(post)
        );

        return newReplies.length > 0 ? newReplies[0] : null;
    }

    isBotReply(post) {
        // Filter by user ID comparison
        // Optionally detect bot user ID if not configured
        return post.user_id === this.getBotUserId();
    }

    getBotUserId() {
        // Try to get from environment, or detect from API
    }
}
```

#### Modified Run Method

```javascript
async run() {
    try {
        const input = await this.readInput();
        const message = this.extractMessage(input);

        // Wait for user reply before sending final message
        const userReply = await this.waitForUserReply();

        if (userReply) {
            // Return JSON hook response to block stop
            this.returnBlockResponse(userReply.message);
            return;
        }

        // No reply received within timeout, send final message as before
        // No JSON response generated - maintain existing functionality
        await this.sendToMattermost(message);
        process.exit(0);

    } catch (error) {
        console.error('Stop hook error:', error.message);
        process.exit(1);
    }
}

returnBlockResponse(replyMessage) {
    const response = {
        decision: 'block',
        reason: replyMessage
    };

    console.log(JSON.stringify(response));
    process.exit(0);
}
```

### JSON Hook Response Format

When a user reply is found, the hook returns:

```json
{
    "decision": "block",
    "reason": "User reply content from Mattermost"
}
```

When no reply is found within timeout, the hook proceeds normally **without generating any JSON response**, maintaining existing functionality.

## Error Handling

### Reply Detection Errors
- API failures: Log warning and continue without reply waiting
- Bot detection failures: Fall back to simple username comparison
- Timeout reached: Proceed with normal stop hook flow

### Configuration Errors
- Missing timeout: Use default 24 hours
- Missing bot user ID: Attempt auto-detection or skip filtering

## Configuration

### Environment Variables

| Variable | Purpose | Default | Required |
|----------|---------|---------|----------|
| `MM_REPLY_TIMEOUT_MS` | Timeout for waiting replies | 86400000 (24h) | No |
| `MM_BOT_USER_ID` | Bot user ID for filtering | Auto-detected | No |
| Existing variables (`MM_ADDRESS`, `MM_TOKEN`, etc.) | Unchanged | - | Yes |

### Default Behavior

- **Timeout**: 24 hours (86400000 milliseconds)
- **Polling Interval**: 2 seconds
- **Bot Filtering**: Enabled (attempts auto-detection if not configured)
- **Timeout Handling**: When timeout reached without reply, existing functionality maintained (no JSON response generated)

## Testing

### Test Scenarios

1. **User Reply Received**: Hook returns block response with reply content
2. **No Reply Within Timeout**: Hook sends final message normally
3. **Bot Reply Only**: Hook ignores bot replies and waits for user
4. **API Failure**: Hook falls back to normal behavior
5. **Configuration Variations**: Test different timeout values

### Manual Testing

```bash
# Test with reply waiting enabled
export MM_REPLY_TIMEOUT_MS=10000
export MM_BOT_USER_ID=bot123
node .claude/hooks/stop-hook.js

# Test without reply waiting (backward compatibility)
unset MM_REPLY_TIMEOUT_MS
node .claude/hooks/stop-hook.js
```

## Security Considerations

- **API Credentials**: Uses existing Mattermost token (no new credentials)
- **Input Validation**: Validates reply content before using as reason
- **Timeout Limits**: Prevents indefinite waiting
- **Error Handling**: Graceful degradation on failures

## Backward Compatibility

- ✅ Existing functionality unchanged when new variables not set
- ✅ Default timeout ensures reasonable waiting period
- ✅ Fallback mechanisms for configuration errors
- ✅ No breaking changes to current behavior

## Performance Impact

- **Polling Frequency**: Every 2 seconds (configurable)
- **API Calls**: Additional calls during timeout period
- **Timeout Impact**: Maximum 24-hour delay before stop hook completes when waiting for replies

## Future Enhancements

- **WebSocket Integration**: Real-time reply detection for faster response
- **Multiple Reply Handling**: Support for collecting multiple replies
- **Reply Filtering**: More sophisticated filtering (keywords, patterns)
- **Configuration UI**: Web interface for timeout and filtering settings

## References

- [Claude Code Hooks JSON Output](https://code.claude.com/docs/en/hooks#json-output)
- [Mattermost API Documentation](https://developers.mattermost.com/api-documentation/)
- [Existing Stop Hook Design](../2026-02-28-mattermost-stop-hook-design.md)