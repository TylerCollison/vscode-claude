# Mattermost Bot Persistent Session Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Update mattermost-bot to use a single persistent Claude Code session for entire runtime instead of spawning new sessions per thread reply.

**Architecture:** Replace ClaudeCodeSession class with PersistentSession class that maintains single Claude Code process with bidirectional communication via stdin/stdout pipes. Only process messages from startup thread.

**Tech Stack:** Node.js child_process, Mattermost WebSocket API, Claude Code CLI

---

## Task 1: Create PersistentSession Class

**Files:**
- Create: `/workspace/mattermost-bot.js` (replace ClaudeCodeSession class)

**Step 1: Write the PersistentSession class structure**

```javascript
class PersistentSession {
    constructor(config = {}) {
        this.config = config;
        this.process = null;
        this.stdoutBuffer = '';
        this.stderrBuffer = '';
        this.messageQueue = [];
        this.processing = false;
        this.messageCallbacks = new Map();
        this.messageIdCounter = 0;
        this.isAlive = false;
        this.restartAttempts = 0;
        this.maxRestartAttempts = config.maxRestartAttempts || 3;
    }

    async initialize() {
        await this.startClaudeProcess();
    }

    async startClaudeProcess() {
        // Implementation will be added in next task
    }

    async sendMessage(message) {
        // Implementation will be added in next task
    }

    checkAlive() {
        return this.isAlive && this.process && !this.process.killed;
    }

    async restart() {
        // Implementation will be added in next task
    }

    async destroy() {
        // Implementation will be added in next task
    }
}
```

**Step 2: Remove existing ClaudeCodeSession class**

Delete lines 736-976 in `/workspace/mattermost-bot.js` (the entire ClaudeCodeSession class)

**Step 3: Add PersistentSession export**

At end of file, replace:
```javascript
module.exports = { MattermostBot, ClaudeCodeSession };
```
with:
```javascript
module.exports = { MattermostBot, PersistentSession };
```

**Step 4: Commit initial structure**

```bash
git add /workspace/mattermost-bot.js
git commit -m "feat: add PersistentSession class structure"
```

---

## Task 2: Implement Claude Code Process Management

**Files:**
- Modify: `/workspace/mattermost-bot.js` (PersistentSession class)

**Step 1: Implement startClaudeProcess method**

```javascript
async startClaudeProcess() {
    return new Promise((resolve, reject) => {
        // Security Fix 2: Configurable permission mode
        const permissionMode = process.env.CLAUDE_PERMISSION_MODE || 'default';

        // Determine which command to use
        const ccrProfile = process.env.CCR_PROFILE;
        const useCCR = ccrProfile && ccrProfile.trim() !== '';

        // Check CCR availability
        let ccrAvailable = false;
        try {
            const { spawnSync } = require('child_process');
            ccrAvailable = spawnSync('which', ['ccr']).status === 0;
        } catch (error) {
            console.warn('Failed to check ccr command availability:', error.message);
        }

        const command = useCCR && ccrAvailable ? 'ccr' : 'claude';
        const args = useCCR && ccrAvailable ?
            [ccrProfile, '--permission-mode', permissionMode] :
            ['--permission-mode', permissionMode];

        console.log(`Starting Claude Code process: ${command} ${args.join(' ')}`);

        const { spawn } = require('child_process');
        this.process = spawn(command, args, {
            stdio: ['pipe', 'pipe', 'pipe']
        });

        this.stdoutBuffer = '';
        this.stderrBuffer = '';

        this.process.stdout.on('data', (data) => {
            this.stdoutBuffer += data.toString();
        });

        this.process.stderr.on('data', (data) => {
            const stderrData = data.toString();
            this.stderrBuffer += stderrData;
            console.error('Claude stderr:', stderrData);
        });

        this.process.on('close', (code) => {
            console.log(`Claude Code process exited with code ${code}`);
            this.isAlive = false;
            this.process = null;

            // Attempt automatic restart if not manually destroyed
            if (this.restartAttempts < this.maxRestartAttempts) {
                this.restartAttempts++;
                console.log(`Attempting restart ${this.restartAttempts}/${this.maxRestartAttempts}`);
                setTimeout(() => this.startClaudeProcess(), 2000);
            }
        });

        this.process.on('error', (error) => {
            console.error('Failed to start Claude process:', error.message);
            reject(error);
        });

        // Wait for process to be ready
        setTimeout(() => {
            this.isAlive = true;
            resolve();
        }, 1000);
    });
}
```

**Step 2: Implement destroy method**

```javascript
async destroy() {
    if (this.process) {
        this.process.kill();
        this.process = null;
    }
    this.isAlive = false;
    this.messageQueue = [];
    this.messageCallbacks.clear();
    console.log('PersistentSession destroyed');
}
```

**Step 3: Implement restart method**

```javascript
async restart() {
    await this.destroy();
    this.restartAttempts = 0;
    await this.startClaudeProcess();
}
```

**Step 4: Commit process management implementation**

```bash
git add /workspace/mattermost-bot.js
git commit -m "feat: implement Claude Code process management in PersistentSession"
```

---

## Task 3: Implement Message Sending and Response Handling

**Files:**
- Modify: `/workspace/mattermost-bot.js` (PersistentSession class)

**Step 1: Implement sendMessage method**

```javascript
async sendMessage(message) {
    return new Promise((resolve, reject) => {
        if (!this.checkAlive()) {
            reject(new Error('Claude Code process is not alive'));
            return;
        }

        const messageId = this.messageIdCounter++;

        // Add message to queue
        this.messageQueue.push({
            id: messageId,
            content: message,
            resolve,
            reject,
            timestamp: Date.now()
        });

        // Process queue if not already processing
        if (!this.processing) {
            this.processQueue();
        }
    });
}
```

**Step 2: Implement processQueue method**

```javascript
async processQueue() {
    if (this.processing || this.messageQueue.length === 0) {
        return;
    }

    this.processing = true;
    const message = this.messageQueue.shift();

    try {
        // Clear buffers for new response
        this.stdoutBuffer = '';
        this.stderrBuffer = '';

        // Send message to Claude Code
        this.process.stdin.write(message.content + '\n');

        // Wait for response with timeout
        const response = await this.waitForResponse(30000); // 30 second timeout
        message.resolve(response);

    } catch (error) {
        message.reject(error);
    } finally {
        this.processing = false;

        // Process next message in queue
        if (this.messageQueue.length > 0) {
            setTimeout(() => this.processQueue(), 100);
        }
    }
}
```

**Step 3: Implement waitForResponse method**

```javascript
waitForResponse(timeoutMs) {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
            reject(new Error('Response timeout exceeded'));
        }, timeoutMs);

        const checkResponse = () => {
            // Look for complete response (Claude Code typically ends with specific markers)
            if (this.stdoutBuffer.includes('\n') && this.stdoutBuffer.trim().length > 0) {
                clearTimeout(timeout);
                const response = this.stdoutBuffer.trim();
                this.stdoutBuffer = '';
                resolve(response);
                return;
            }

            // Check if process died
            if (!this.checkAlive()) {
                clearTimeout(timeout);
                reject(new Error('Claude Code process terminated'));
                return;
            }

            // Continue checking
            setTimeout(checkResponse, 100);
        };

        // Start checking
        setTimeout(checkResponse, 500);
    });
}
```

**Step 4: Commit message handling implementation**

```bash
git add /workspace/mattermost-bot.js
git commit -m "feat: implement message sending and response handling in PersistentSession"
```

---

## Task 4: Integrate PersistentSession with MattermostBot

**Files:**
- Modify: `/workspace/mattermost-bot.js` (MattermostBot class)

**Step 1: Replace sessions Map with single PersistentSession**

Replace line 24:
```javascript
this.sessions = new Map(); // threadId -> ClaudeCodeSession
```
with:
```javascript
this.persistentSession = null;
```

**Step 2: Update initialize method to start persistent session**

Replace lines 145-162:
```javascript
async initialize() {
    try {
        await this.resolveChannelId();
        await this.connect();

        // Critical: startup notification must succeed
        const notificationResponse = await this.sendStartupNotification();
        this.botThreadId = notificationResponse.id;
        console.log(`Startup notification posted with thread ID: ${this.botThreadId}`);

        this.startSessionCleanupInterval();
        console.log('Mattermost bot initialized successfully');
    } catch (error) {
        const errorId = this.handleError(error, 'Bot initialization');
        console.error(`Bot initialization failed (errorId: ${errorId}), exiting...`);
        process.exit(1); // Exit on critical failure
    }
}
```

with:
```javascript
async initialize() {
    try {
        await this.resolveChannelId();
        await this.connect();

        // Critical: startup notification must succeed
        const notificationResponse = await this.sendStartupNotification();
        this.botThreadId = notificationResponse.id;
        console.log(`Startup notification posted with thread ID: ${this.botThreadId}`);

        // Initialize persistent session
        const { PersistentSession } = require('./mattermost-bot.js');
        this.persistentSession = new PersistentSession({
            maxRestartAttempts: 3
        });
        await this.persistentSession.initialize();
        console.log('Persistent Claude Code session initialized');

        console.log('Mattermost bot initialized successfully');
    } catch (error) {
        const errorId = this.handleError(error, 'Bot initialization');
        console.error(`Bot initialization failed (errorId: ${errorId}), exiting...`);
        process.exit(1); // Exit on critical failure
    }
}
```

**Step 3: Remove session cleanup interval**

Remove lines 644-666 (the entire startSessionCleanupInterval method and cleanupExpiredSessions method)

**Step 4: Commit integration changes**

```bash
git add /workspace/mattermost-bot.js
git commit -m "feat: integrate PersistentSession with MattermostBot"
```

---

## Task 5: Update Message Processing Logic

**Files:**
- Modify: `/workspace/mattermost-bot.js` (processUserInput method)

**Step 1: Update processUserInput method**

Replace lines 500-534:
```javascript
processUserInput(post) {
    const threadId = post.root_id;
    const message = post.message || '';

    // Sanitize and validate user input before processing
    const sanitizedMessage = this.sanitizeUserInput(message);

    if (!this.isSafeUserInput(sanitizedMessage)) {
        console.error('Potential security risk detected in user input');
        return;
    }

    // Use direct Map operations as specified in the spec
    if (!this.sessions.has(threadId)) {
        this.sessions.set(threadId, new ClaudeCodeSession(threadId));
    }
    const session = this.sessions.get(threadId);

    session.sendToClaude(sanitizedMessage)
        .then(response => {
            return this.sendReply(post, response);
        })
        .then(() => {
            console.log('Reply sent successfully');
        })
        .catch(error => {
            console.error('Error processing user input:', error);
            // Attempt to send error message
            this.sendReply(post, `Error processing request: ${error.message}`)
                .catch(e => console.error('Failed to send error message:', e));
        });

    console.log(`Processing user input for thread ${threadId}:`, sanitizedMessage.substring(0, 100));
    console.log(`Active sessions: ${this.getActiveSessionCount()}`);
}
```

with:
```javascript
processUserInput(post) {
    const threadId = post.root_id;
    const message = post.message || '';

    // Only process messages from the startup thread
    if (!this.botThreadId || threadId !== this.botThreadId) {
        console.log(`Ignoring message from non-startup thread: ${threadId}`);
        return;
    }

    // Sanitize and validate user input before processing
    const sanitizedMessage = this.sanitizeUserInput(message);

    if (!this.isSafeUserInput(sanitizedMessage)) {
        console.error('Potential security risk detected in user input');
        return;
    }

    // Use persistent session for all messages
    if (!this.persistentSession || !this.persistentSession.checkAlive()) {
        console.error('Persistent session not available');
        this.sendReply(post, 'Claude Code session is currently unavailable. Please try again later.')
            .catch(e => console.error('Failed to send error message:', e));
        return;
    }

    this.persistentSession.sendMessage(sanitizedMessage)
        .then(response => {
            return this.sendReply(post, response);
        })
        .then(() => {
            console.log('Reply sent successfully via persistent session');
        })
        .catch(error => {
            console.error('Error processing user input via persistent session:', error);
            // Attempt to send error message
            this.sendReply(post, `Error processing request: ${error.message}`)
                .catch(e => console.error('Failed to send error message:', e));
        });

    console.log(`Processing user input via persistent session:`, sanitizedMessage.substring(0, 100));
}
```

**Step 2: Remove getActiveSessionCount method**

Remove lines 684-689 (getActiveSessionCount method)

**Step 3: Remove validateSession method**

Remove lines 668-682 (validateSession method)

**Step 4: Commit message processing updates**

```bash
git add /workspace/mattermost-bot.js
git commit -m "feat: update message processing to use persistent session"
```

---

## Task 6: Add Cleanup on Bot Shutdown

**Files:**
- Modify: `/workspace/mattermost-bot.js` (main function and signal handlers)

**Step 1: Update main function cleanup**

Replace lines 711-720:
```javascript
// Keep the process alive
process.on('SIGINT', () => {
    console.log('Shutting down Mattermost bot service...');
    process.exit(0);
});

process.on('SIGTERM', () => {
    console.log('Shutting down Mattermost bot service...');
    process.exit(0);
});
```

with:
```javascript
// Keep the process alive
process.on('SIGINT', async () => {
    console.log('Shutting down Mattermost bot service...');
    if (bot.persistentSession) {
        await bot.persistentSession.destroy();
    }
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('Shutting down Mattermost bot service...');
    if (bot.persistentSession) {
        await bot.persistentSession.destroy();
    }
    process.exit(0);
});
```

**Step 2: Commit cleanup implementation**

```bash
git add /workspace/mattermost-bot.js
git commit -m "feat: add proper cleanup for persistent session on shutdown"
```

---

## Task 7: Test the Implementation

**Files:**
- Test: `/workspace/mattermost-bot.js`

**Step 1: Create simple test script**

Create `/workspace/test-persistent-session.js`:

```javascript
const { PersistentSession } = require('./mattermost-bot.js');

async function testPersistentSession() {
    console.log('Testing PersistentSession...');

    const session = new PersistentSession();

    try {
        await session.initialize();
        console.log('Session initialized successfully');

        // Test sending a message
        const response = await session.sendMessage('Hello, can you tell me what time it is?');
        console.log('Response received:', response.substring(0, 100));

        // Test sending another message to verify persistence
        const response2 = await session.sendMessage('What was my previous question?');
        console.log('Second response received:', response2.substring(0, 100));

        await session.destroy();
        console.log('Test completed successfully');

    } catch (error) {
        console.error('Test failed:', error);
        await session.destroy();
    }
}

if (require.main === module) {
    testPersistentSession().catch(console.error);
}
```

**Step 2: Run the test**

```bash
node /workspace/test-persistent-session.js
```

Expected: Should start Claude Code process and receive responses

**Step 3: Commit test script**

```bash
git add /workspace/test-persistent-session.js
git commit -m "test: add persistent session test script"
```

---

## Task 8: Update Documentation

**Files:**
- Modify: `/workspace/README.md` (if exists) or create new documentation

**Step 1: Create implementation summary**

Create `/workspace/docs/mattermost-bot-persistent-session.md`:

```markdown
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
```

**Step 2: Commit documentation**

```bash
git add /workspace/docs/mattermost-bot-persistent-session.md
git commit -m "docs: add persistent session implementation documentation"
```

---

Plan complete and saved to `docs/plans/2026-02-27-mattermost-bot-persistent-session-implementation.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**