# Mattermost Bot Single Persistent Claude Code Session Design

## Overview
Update the Mattermost bot to use a single persistent Claude Code session for its entire runtime instead of spawning new sessions for every thread reply.

## Design Decisions

### Approach Selected
**Approach 1: Persistent Session with Bidirectional Communication**
- Single Claude Code session runs for the entire bot lifetime
- Bidirectional communication via stdin/stdout pipes
- Messages processed sequentially through persistent session
- Only supports messages from the single startup thread

### Key Changes
1. **Replace ClaudeCodeSession with PersistentSession** - New class manages single Claude Code process
2. **Thread Filtering** - Only process messages from the startup thread (ignore other threads)
3. **Sequential Processing** - Queue messages to avoid concurrent writes to stdin
4. **Error Recovery** - Automatic restart if Claude Code process terminates

## Implementation Plan

### Phase 1: PersistentSession Class
1. **Create PersistentSession class** - Replace current ClaudeCodeSession
   - Manage single Claude Code process with open pipes
   - Implement message queuing for sequential processing
   - Handle stdout/stderr streams and response routing

2. **Process Management**
   - Start Claude Code during bot initialization
   - Maintain open stdin/stdout/stderr pipes
   - Implement health monitoring and automatic restart

### Phase 2: Message Handling Updates
1. **Thread Filtering Logic** - Only accept messages from `this.botThreadId`
2. **Sequential Processing** - Queue incoming messages and process one at a time
3. **Response Routing** - Ensure responses are sent back to the correct thread

### Phase 3: Error Handling and Recovery
1. **Process Monitoring** - Detect when Claude Code process terminates
2. **Automatic Restart** - Restart session with preserved configuration
3. **Graceful Degradation** - Handle temporary Claude Code unavailability

## Technical Specifications

### PersistentSession Class API
```javascript
class PersistentSession {
  constructor(config)
  async initialize()
  async sendMessage(message)
  async destroy()
  isAlive()
  restart()
}
```

### Message Processing Flow
1. Bot receives WebSocket message
2. Validate thread ID matches `this.botThreadId`
3. Queue message in PersistentSession
4. Process sequentially through Claude Code stdin
5. Receive response via stdout
6. Send reply back to Mattermost thread

### Error Recovery Strategy
- Monitor Claude Code process health
- Restart if process terminates unexpectedly
- Preserve conversation context through Claude Code's session management
- Log session lifecycle events for debugging

## Files to Modify

### mattermost-bot.js
- Replace `ClaudeCodeSession` class with `PersistentSession` class
- Update `processUserInput` method to use persistent session
- Modify bot initialization to start persistent session
- Add thread filtering logic

### Key Changes in mattermost-bot.js
- Line 736-976: Replace ClaudeCodeSession class
- Line 500-534: Update processUserInput method
- Line 145-162: Add persistent session initialization

## Success Criteria

### Functional Requirements
- ✅ Single Claude Code session runs for entire bot lifetime
- ✅ Only messages from startup thread are processed
- ✅ Conversation context maintained across interactions
- ✅ Automatic recovery if Claude Code process terminates
- ✅ Sequential processing of queued messages

### Performance Requirements
- ✅ No process startup overhead for each message
- ✅ Efficient message queuing and processing
- ✅ Minimal resource usage for persistent session

### Reliability Requirements
- ✅ Graceful handling of Claude Code failures
- ✅ Proper cleanup on bot shutdown
- ✅ Comprehensive error logging

## Risk Assessment

### Low Risk
- Thread filtering logic (already partially implemented)
- Message queuing (straightforward implementation)
- Process management (standard Node.js child_process)

### Medium Risk
- Bidirectional pipe management (requires careful error handling)
- Concurrent message handling (sequential processing avoids race conditions)
- Session recovery (needs robust testing)

### Mitigation Strategies
- Comprehensive unit testing for pipe management
- Integration testing with mock Claude Code
- Monitoring and logging for production deployment

## Testing Plan

### Unit Tests
- PersistentSession initialization and message sending
- Thread filtering logic
- Error recovery and restart mechanisms

### Integration Tests
- End-to-end message flow from Mattermost to Claude Code and back
- Session recovery scenarios
- Concurrent message handling (should be sequential)

### Performance Tests
- Message processing throughput
- Memory usage of persistent session
- Recovery time from process failures

## Migration Strategy

### Step 1: Implement PersistentSession alongside ClaudeCodeSession
- Add new class without breaking existing functionality
- Test persistent session in isolation

### Step 2: Gradual Migration
- Route some messages through persistent session
- Compare behavior with existing implementation
- Fix any issues discovered

### Step 3: Full Migration
- Replace ClaudeCodeSession with PersistentSession
- Remove legacy session management code
- Update all message handling to use persistent session

## Dependencies

### External Dependencies
- Node.js child_process module (already available)
- Claude Code CLI (already available)
- Mattermost WebSocket API (already available)

### Internal Dependencies
- Existing Mattermost bot infrastructure
- Environment variable configuration
- Logging and error handling systems

## Timeline

### Phase 1 (1-2 days)
- Design and implement PersistentSession class
- Unit tests for basic functionality

### Phase 2 (1-2 days)
- Integrate PersistentSession with bot message handling
- Thread filtering implementation

### Phase 3 (1 day)
- Error recovery and automatic restart
- Comprehensive testing

### Phase 4 (1 day)
- Performance optimization
- Production deployment preparation

---
*Design approved: 2026-02-27*
*Implementation to follow design specifications*