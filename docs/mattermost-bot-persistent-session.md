# Mattermost Bot Persistent Session Implementation

## Overview
Updated Mattermost bot to use single persistent Claude Code session instead of spawning new sessions per thread reply.

## Changes Made

### 1. PersistentSession Class
- Replaced ClaudeCodeSession with PersistentSession
- Maintains single Claude Code process with bidirectional communication
- Implements message queuing for sequential processing
- Automatic restart on process failure

### 2. Thread Filtering
- Only processes messages from the startup thread
- Ignores messages from other threads
- Maintains conversation context through Claude Code's session management

### 3. Performance Improvements
- Eliminates process startup overhead
- Reduces resource usage
- Maintains conversation context naturally

## Configuration
No configuration changes required. The bot automatically uses persistent sessions.

## Testing
Run: `node /workspace/test-persistent-session.js`

## Technical Details

The persistent session implementation provides several key benefits over the previous approach:

### Architecture Changes
- **Single Process**: Instead of creating new Claude Code processes for each message, the bot maintains a single persistent process
- **Bidirectional Communication**: Messages are sent to Claude Code through stdin and responses are read from stdout
- **Message Queueing**: Incoming messages are processed sequentially to maintain conversation context
- **Error Recovery**: Automatic process restart on failures or timeouts

### Implementation Files
- `/workspace/mattermost-bot.js` - Main bot implementation with PersistentSession integration
- `/workspace/test-persistent-session.js` - Comprehensive test script
- `/workspace/master-startup.sh` - Master startup script managing the persistent session

### Performance Benefits
- **Reduced Startup Time**: Eliminates ~2-3 second startup delay per message
- **Resource Efficiency**: Single process uses less memory than multiple processes
- **Conversation Continuity**: Claude Code maintains context across multiple messages
- **Scalability**: Better performance under high message volume

### Usage Notes
- The bot starts automatically with the persistent session
- No manual intervention required
- Restarts automatically if the session terminates unexpectedly
- Maintains thread-based conversation isolation

This implementation represents a significant improvement in both performance and user experience for Mattermost bot interactions.