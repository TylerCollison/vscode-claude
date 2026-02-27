# Mattermost Bot Notification Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate Mattermost notification functionality into the Mattermost bot to enable thread-based interactions and eliminate the separate bash script.

**Architecture:** Add startup notification method to MattermostBot class, store thread ID for message filtering, modify handlePostMessage to only process thread replies, and remove the separate notification script.

**Tech Stack:** Node.js, Mattermost WebSocket API, Claude Code CLI integration

---

## Task 1: Add Startup Notification Method

**Files:**
- Modify: `mattermost-bot.js:611-650` (main function)
- Modify: `mattermost-bot.js:137-147` (initialize method)
- Create: `mattermost-bot.js:850-900` (new sendStartupNotification method)

**Step 1: Add sendStartupNotification method**

```javascript
async sendStartupNotification() {
    const mmAddress = this.mmAddress;
    const mmToken = this.mmToken;
    const channelId = await this.getTargetChannelId();

    if (!mmAddress || !mmToken || !channelId) {
        throw new Error('Missing required configuration for startup notification');
    }

    const message = `🚀 **Claude Code Development Environment Started**\n\n**Container Information:**\n- **Prompt:** ${process.env.PROMPT || 'Not set'}\n- **IDE Address:** ${process.env.IDE_ADDRESS || 'Not set'}\n- **Started at:** ${new Date()}\n\nThis container is ready for development work!`;

    const payload = {
        channel_id: channelId,
        message: message
    };

    const url = `${mmAddress}/api/v4/posts`;

    return new Promise((resolve, reject) => {
        const urlObj = new URL(url);
        const protocol = urlObj.protocol === 'https:' ? require('https') : require('http');

        const request = protocol.request(urlObj, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${mmToken}`,
                'Content-Type': 'application/json'
            }
        }, (response) => {
            let data = '';
            response.on('data', chunk => data += chunk);
            response.on('end', () => {
                if (response.statusCode >= 200 && response.statusCode < 300) {
                    try {
                        const parsedResponse = JSON.parse(data);
                        resolve(parsedResponse);
                    } catch (parseError) {
                        reject(new Error(`Failed to parse API response: ${parseError.message}`));
                    }
                } else {
                    reject(new Error(`HTTP ${response.statusCode}: ${data}`));
                }
            });
        });

        request.on('error', reject);
        request.setTimeout(10000, () => {
            request.destroy();
            reject(new Error('Startup notification request timeout after 10 seconds'));
        });

        request.write(JSON.stringify(payload));
        request.end();
    });
}
```

**Step 2: Add botThreadId property to MattermostBot constructor**

Modify constructor around line 28:
```javascript
this.targetChannelId = null;
this.botThreadId = null; // Add this line
```

**Step 3: Update initialize method to call startup notification**

Modify initialize method:
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

**Step 4: Test the startup notification**

Run: `node mattermost-bot.js` with proper environment variables
Expected: Bot posts startup notification and stores thread ID

**Step 5: Commit**

```bash
git add mattermost-bot.js
git commit -m "feat: add startup notification method to Mattermost bot"
```

## Task 2: Add Thread-Based Message Filtering

**Files:**
- Modify: `mattermost-bot.js:285-311` (handlePostMessage method)

**Step 1: Modify handlePostMessage to filter by thread ID**

Update handlePostMessage method:
```javascript
async handlePostMessage(message) {
    let post;
    try {
        post = JSON.parse(message.data.post);
    } catch (error) {
        const errorId = this.handleError(error, 'message.data.post parsing');
        console.error(`[${errorId}] Failed to parse Mattermost post data: ${error.message}`);
        return;
    }

    // Validate post structure
    if (!this.isValidPost(post)) {
        console.error('Invalid post structure received');
        return;
    }

    // Only process messages in the target channel
    const targetChannelId = await this.getTargetChannelId();
    if (post.channel_id !== targetChannelId) {
        return;
    }

    // Only process replies to our bot thread
    if (!post.root_id || post.root_id !== this.botThreadId) {
        console.log(`Ignoring message not in bot thread: ${post.root_id}`);
        return;
    }

    // Handle thread replies
    this.processUserInput(post);
}
```

**Step 2: Add logging for thread filtering**

Add debug logging to help verify thread filtering:
```javascript
// Add after the thread ID check
console.log(`Processing message in bot thread: ${post.root_id}`);
```

**Step 3: Test thread filtering**

Run: `node mattermost-bot.js` and test:
- Post in bot thread: Should be processed
- Post outside bot thread: Should be ignored
- Post in different channel: Should be ignored

**Step 4: Commit**

```bash
git add mattermost-bot.js
git commit -m "feat: add thread-based message filtering to Mattermost bot"
```

## Task 3: Remove Separate Notification Script

**Files:**
- Delete: `94-mattermost-notification.sh`

**Step 1: Remove the script file**

Run: `rm 94-mattermost-notification.sh`

**Step 2: Update git to track deletion**

Run: `git add -u` to stage the deletion

**Step 3: Verify no other files reference the script**

Run: `grep -r "94-mattermost-notification.sh" .`
Expected: No references found

**Step 4: Commit the removal**

```bash
git commit -m "chore: remove 94-mattermost-notification.sh - functionality integrated into bot"
```

## Task 4: Add Error Handling Improvements

**Files:**
- Modify: `mattermost-bot.js:137-147` (initialize method error handling)
- Modify: `mattermost-bot.js:850-900` (sendStartupNotification error handling)

**Step 1: Improve error handling in sendStartupNotification**

Add validation for environment variables:
```javascript
// Add at the beginning of sendStartupNotification
if (!process.env.PROMPT || !process.env.IDE_ADDRESS) {
    console.warn('Missing PROMPT or IDE_ADDRESS environment variables');
}
```

**Step 2: Add graceful handling for missing thread ID**

Modify handlePostMessage to handle missing botThreadId:
```javascript
// Modify the thread ID check
if (!this.botThreadId) {
    console.log('Bot thread ID not set, ignoring message');
    return;
}

if (!post.root_id || post.root_id !== this.botThreadId) {
    console.log(`Ignoring message not in bot thread: ${post.root_id}`);
    return;
}
```

**Step 3: Test error scenarios**

Test:
- Missing PROMPT/IDE_ADDRESS: Should post notification with "Not set"
- Missing botThreadId: Should log warning and ignore messages

**Step 4: Commit error handling improvements**

```bash
git add mattermost-bot.js
git commit -m "feat: improve error handling for Mattermost bot notification integration"
```

## Task 5: Final Integration Testing

**Files:**
- All modified files

**Step 1: Comprehensive test**

Run: `node mattermost-bot.js` with full environment setup
Test:
1. Bot posts startup notification ✓
2. Bot stores thread ID ✓
3. Messages in bot thread are processed ✓
4. Messages outside bot thread are ignored ✓
5. Messages in different channel are ignored ✓

**Step 2: Verify script removal**

Verify: `94-mattermost-notification.sh` no longer exists

**Step 3: Final commit**

```bash
git add .
git commit -m "feat: complete Mattermost bot notification integration"
```

## Verification Checklist

- [ ] Bot posts startup notification on initialization
- [ ] Bot stores thread ID correctly
- [ ] Thread-based message filtering works
- [ ] Separate notification script is removed
- [ ] Error handling handles missing environment variables
- [ ] Backward compatibility maintained for existing functionality