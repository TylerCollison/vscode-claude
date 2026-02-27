# Mattermost Bot Notification Integration Design

**Date**: 2026-02-27
**Author**: Claude Code Assistant
**Status**: Approved Design

## Overview

Integrate Mattermost notification functionality directly into the Mattermost bot, enabling thread-based interactions and eliminating the need for the separate `94-mattermost-notification.sh` script.

## Goals

1. **Thread-Based Interaction**: Bot creates initial post and only responds to replies on that specific thread
2. **Simplified Deployment**: Remove dependency on separate bash script
3. **Maintain Existing Functionality**: Keep Claude Code session management unchanged

## Design Decisions

### Architecture
- Add startup notification method to `MattermostBot` class
- Store thread ID (`root_id`) of initial post for message filtering
- Modify message handling to only process replies to bot's thread
- Remove `94-mattermost-notification.sh` script

### Startup Notification
- Content identical to existing bash script
- Posts to configured Mattermost channel
- Stores thread ID for future message filtering

### Thread Management
- Create new thread on each bot startup
- Only process messages where `post.root_id` matches bot's thread ID
- Ignore messages outside the bot's thread

### Error Handling
- Exit on startup notification failure (critical path)
- Continue existing retry logic for WebSocket connections
- Clear error messages for missing environment variables

## Implementation Plan

### Phase 1: Add Startup Notification
1. Add `sendStartupNotification()` method to `MattermostBot` class
2. Format message identical to bash script
3. Call during `initialize()` after channel resolution
4. Store thread ID in `this.botThreadId`

### Phase 2: Thread-Based Message Filtering
1. Modify `handlePostMessage()` to check `post.root_id`
2. Only process messages where `root_id === this.botThreadId`
3. Maintain existing Claude Code session logic

### Phase 3: Error Handling Integration
1. Update `initialize()` to exit on notification failure
2. Add validation for required environment variables
3. Ensure backward compatibility

### Phase 4: Script Removal
1. Remove `94-mattermost-notification.sh`
2. Update any documentation referencing the script

## Files Modified

- `mattermost-bot.js` - Add notification and thread filtering
- `94-mattermost-notification.sh` - Remove (deleted)

## Environment Variables

Reuse existing:
- `MM_ADDRESS` - Mattermost server address
- `MM_TOKEN` - Mattermost bot token
- `MM_CHANNEL` - Target channel name

Add/Reuse:
- `PROMPT` - Container prompt (from bash script)
- `IDE_ADDRESS` - IDE address (from bash script)

## Success Criteria

- Bot posts startup notification on initialization
- Bot only responds to replies on its specific thread
- `94-mattermost-notification.sh` is removed
- Existing Claude Code functionality remains intact
- Error handling properly exits on critical failures

## Risk Assessment

**Low Risk**:
- Thread-based filtering is additive functionality
- Existing message processing remains unchanged
- Error handling improvements enhance reliability

**Mitigation**:
- Thorough testing of thread filtering logic
- Validation of environment variable handling
- Verification of backward compatibility