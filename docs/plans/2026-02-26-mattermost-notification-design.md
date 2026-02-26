# Mattermost Notification Script Design

## Overview
A startup script that posts notifications to Mattermost when Claude Code containers start, providing visibility into new development sessions.

## Design Details

### Script Location
- **File**: `/etc/cont-init.d/94-mattermost-notification`
- **Priority**: 94 (runs early in startup sequence, before git operations)
- **Pattern**: Follows existing startup script conventions

### Environment Variables

**Required Variables:**
- `MM_ADDRESS`: Mattermost server URL (e.g., `http://portainer.home.com:8081`)
- `MM_CHANNEL`: Target channel name (e.g., `claude-code`)
- `MM_TOKEN`: Bot authentication token (e.g., `wkansc9mcjfqtr4oubkh4kwmmw`)
- `PROMPT`: Initial prompt text provided to Claude
- `IDE_ADDRESS`: Claude Code session web address

### Message Format (Markdown)

```markdown
## New Claude Code Session Started 🚀

**Prompt:** ${PROMPT}
**Session URL:** [${IDE_ADDRESS}](${IDE_ADDRESS})
**Container:** $(hostname)

Started at: $(date)
```

### API Integration

**Mattermost API Endpoint:**
- `POST ${MM_ADDRESS}/api/v4/posts`
- **Headers:**
  - `Authorization: Bearer ${MM_TOKEN}`
  - `Content-Type: application/json`

**Request Body:**
```json
{
  "channel_id": "${CHANNEL_ID}",
  "message": "Formatted markdown message"
}
```

**Note**: The script will need to resolve channel name to channel ID using the Mattermost API.

### Error Handling Strategy

1. **Missing Environment Variables**
   - Log specific missing variable
   - Exit gracefully with error code

2. **Authentication Failures**
   - Log authentication error details
   - Exit with appropriate error code

3. **Network/Connection Issues**
   - Log connection timeout/refusal
   - Exit gracefully

4. **API Response Handling**
   - Check HTTP status codes
   - Parse Mattermost error responses
   - Log specific error messages

### Implementation Steps

1. **Environment Validation**
   - Check all required variables exist
   - Validate URL format for MM_ADDRESS

2. **Channel Resolution**
   - Call Mattermost API to get channel ID from name
   - Handle channel not found errors

3. **Message Construction**
   - Format markdown message with variables
   - Include container hostname and timestamp

4. **API Request**
   - Send POST request with authentication
   - Handle response codes appropriately

5. **Logging**
   - Use existing logging patterns from other scripts
   - Log success/failure with details

### Testing Plan

**Manual Testing Scenarios:**
1. Valid environment variables - should post successfully
2. Missing MM_TOKEN - should log authentication error
3. Invalid channel name - should log channel resolution error
4. Network unreachable - should log connection error

**Test Environment:**
- Mattermost Server: `http://portainer.home.com:8081`
- Channel: `claude-code`
- Token: `wkansc9mcjfqtr4oubkh4kwmmw`

### Integration Considerations

- Runs as part of container startup process
- Uses existing bash scripting patterns
- Follows error handling conventions from other startup scripts
- Minimal impact on startup time (single API call)

### Security Considerations

- Bot token stored as environment variable
- No sensitive data in message content
- Error messages don't expose token details
- Follows existing security patterns

## Success Criteria

- Script posts formatted message to Mattermost on container startup
- Handles all error conditions gracefully
- Integrates seamlessly with existing startup process
- Provides useful notification for team visibility