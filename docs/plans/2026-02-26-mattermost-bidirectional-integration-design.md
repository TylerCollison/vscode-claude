# Mattermost Bidirectional Integration Design

## Overview
A bidirectional integration system that enables full communication between Claude Code and Mattermost, allowing users to interact with Claude Code entirely through Mattermost threads.

## Design Details

### Architecture Components

#### 1. Mattermost Bot Service (`/workspace/mattermost-bot.js`)
- **Type**: Node.js persistent daemon service
- **Connection**: WebSocket-based real-time messaging
- **State Management**: Maintains Claude Code session per Mattermost thread
- **Authentication**: Uses existing MM_TOKEN environment variable

#### 2. Claude Code Hook Integration
- **Output Hook**: Captures Claude Code responses and sends as Mattermost replies
- **Input Processing**: Processes Mattermost replies as Claude Code input
- **Session Management**: Maintains conversation context per thread

#### 3. Extended Configuration
```bash
# Existing Mattermost notification variables
MM_ADDRESS="http://mattermost.example.com"
MM_CHANNEL="claude-code"
MM_TOKEN="your-bot-token"
PROMPT="Initial prompt"
IDE_ADDRESS="https://claude-session.example.com"

# New bot functionality variables
MM_BOT_ENABLED="true"
CC_SESSION_TIMEOUT="3600"  # 1 hour inactivity timeout
CC_MAX_CONTEXT_LENGTH="4000"  # Claude Code context limit
```

### Data Flow Sequence

1. **Container Startup**
   - Existing notification script posts initial message
   - Message includes session info and Claude Code instance details

2. **Bot Activation**
   - Mattermost bot detects notification message
   - Starts monitoring the thread for user replies
   - Initializes Claude Code session for the thread

3. **User Interaction Loop**
   - User replies in Mattermost thread
   - Bot processes message as Claude Code input
   - Claude Code generates response
   - Response posted as Mattermost reply in same thread
   - Conversation context maintained throughout

4. **Session Management**
   - Session persists for CC_SESSION_TIMEOUT seconds
   - Automatic cleanup after inactivity period
   - Graceful handling of network interruptions

### Technical Implementation

#### Mattermost Bot Features
- WebSocket connection for real-time message reception
- Thread-aware message routing and context separation
- Session timeout management with configurable intervals
- Error handling with exponential backoff reconnection
- Support for file attachments and code blocks

#### Claude Code Integration
- Uses Claude Code CLI with appropriate permission modes
- Maintains conversation history per thread
- Handles file operations and code generation safely
- Respects Claude Code security boundaries
- Supports both text and code responses

#### Security Considerations
- Uses Mattermost bot token with minimal channel permissions
- Maintains Claude Code security model and permission modes
- No sensitive data exposed in Mattermost messages
- Proper session cleanup on timeout or error
- Input validation and sanitization

### Error Handling Strategy

#### Connection Failures
- WebSocket reconnection with exponential backoff
- Graceful degradation to polling if WebSocket unavailable
- Clear error messages in Mattermost for user visibility

#### Claude Code Errors
- Handle Claude Code authentication failures
- Manage Claude Code context limits
- Proper error reporting to Mattermost users
- Session recovery mechanisms

#### Mattermost API Errors
- Handle rate limiting and API quota exceeded
- Authentication token expiration handling
- Channel permission verification

### Testing Plan

#### Integration Testing Scenarios
1. **Successful Bidirectional Flow**
   - Container startup notification
   - User reply processing
   - Claude Code response delivery
   - Multi-turn conversation persistence

2. **Error Conditions**
   - Mattermost server unreachable
   - Claude Code authentication failure
   - Network interruptions
   - Session timeout behavior

3. **Edge Cases**
   - Empty user messages
   - Very long responses
   - File attachment handling
   - Concurrent user interactions

#### Performance Testing
- Message processing latency measurements
- Concurrent session management
- Memory usage under load
- Session timeout accuracy

### Deployment Considerations

#### Container Integration
- Bot service runs as separate process alongside Claude Code
- Proper process supervision and restart mechanisms
- Resource allocation and monitoring
- Logging integration with existing system

#### Configuration Management
- Environment variable validation
- Default values for optional parameters
- Configuration reload capability
- Secure handling of sensitive tokens

### Success Criteria

- ✅ Claude Code output appears as Mattermost replies in notification threads
- ✅ Mattermost replies are processed as Claude Code input
- ✅ Conversation context maintained throughout thread interactions
- ✅ Session timeout properly enforced after inactivity
- ✅ Error handling provides clear user feedback
- ✅ Security boundaries maintained for both systems
- ✅ Performance meets interactive response expectations

### Next Steps

1. **Implementation Planning** - Detailed task breakdown
2. **Prototype Development** - Core bidirectional functionality
3. **Testing Framework** - Automated integration tests
4. **Documentation** - User guide and deployment instructions
5. **Production Readiness** - Monitoring and operational procedures

---

*Design approved for implementation on 2026-02-26*