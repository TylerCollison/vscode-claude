#!/usr/bin/env node
// Claude Code Stop Hook for Mattermost Integration
// Sends last assistant message as reply to Mattermost thread

const https = require('https');
const http = require('http');
const fs = require('fs');

class StopHook {
    constructor() {
        this.validateEnvironment();
    }

    validateEnvironment() {
        const requiredVars = ['MM_ADDRESS', 'MM_TOKEN'];
        const missingVars = requiredVars.filter(varName => !process.env[varName]);

        if (missingVars.length > 0) {
            console.error(`Missing required environment variables: ${missingVars.join(', ')}`);
            process.exit(1);
        }

        // Get thread ID using file-first approach
        this.threadId = this.getThreadId();
        if (!this.threadId) {
            console.error('No thread ID available from file (/tmp/mm_thread_id) or environment variable (MM_THREAD_ID)');
            process.exit(1);
        }

        // Validate URL format
        try {
            const url = new URL(process.env.MM_ADDRESS);
            if (!['http:', 'https:'].includes(url.protocol)) {
                throw new Error('Invalid URL protocol');
            }
        } catch (error) {
            console.error(`Invalid MM_ADDRESS format: ${process.env.MM_ADDRESS}`);
            process.exit(1);
        }

        // Set reply timeout (default: 24 hours)
        this.replyTimeoutMs = parseInt(process.env.MM_REPLY_TIMEOUT_MS) || 24 * 60 * 60 * 1000;

        // Set bot user ID for filtering replies
        this.botUserId = process.env.MM_BOT_USER_ID || null;
    }

    getThreadId() {
        const filePath = '/tmp/mm_thread_id';
        let threadId = null;
        let source = null;

        // File-first approach: Try to read from file first
        if (fs.existsSync(filePath)) {
            console.log('📝 Reading thread ID from file: /tmp/mm_thread_id');
            try {
                const content = fs.readFileSync(filePath, 'utf8').trim();
                if (content) {
                    threadId = content;
                    source = 'file';
                    console.log(`📝 Using thread ID from file: ${threadId}`);
                } else {
                    console.log('📝 File exists but is empty, falling back to environment variable');
                }
            } catch (error) {
                console.log('📝 Error reading file, falling back to environment variable:', error.message);
            }
        }

        // Environment variable fallback
        if (!threadId && process.env.MM_THREAD_ID) {
            console.log('📝 Using thread ID from environment variable: MM_THREAD_ID');
            threadId = process.env.MM_THREAD_ID;
            source = 'env';
            console.log(`📝 Using thread ID from environment: ${threadId}`);
        }

        // Log which source was used
        if (threadId && source) {
            console.log(`📝 Thread ID source: ${source}`);
        }

        return threadId;
    }

    // Helper method to sleep for specified milliseconds
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Get all replies in the thread
    async getThreadReplies() {
        const mmAddress = process.env.MM_ADDRESS;
        const mmToken = process.env.MM_TOKEN;

        const url = `${mmAddress}/api/v4/posts/${this.threadId}/thread`;
        const urlObj = new URL(url);
        const protocol = urlObj.protocol === 'https:' ? https : http;

        return new Promise((resolve, reject) => {
            const request = protocol.request(urlObj, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${mmToken}`,
                    'Content-Type': 'application/json'
                }
            }, (response) => {
                let data = '';
                response.on('data', chunk => data += chunk);
                response.on('end', () => {
                    if (response.statusCode === 200) {
                        try {
                            const posts = JSON.parse(data);
                            resolve(posts.posts || {});
                        } catch (error) {
                            reject(new Error('Failed to parse posts response'));
                        }
                    } else {
                        reject(new Error(`Failed to get thread replies: HTTP ${response.statusCode}`));
                    }
                });
            });

            request.on('error', reject);
            request.setTimeout(5000, () => {
                request.destroy();
                reject(new Error('Thread replies request timeout after 5 seconds'));
            });

            request.end();
        });
    }

    // Check if a post is from the bot
    isBotReply(post) {
        if (!this.botUserId) {
            return false;
        }
        return post.user_id === this.botUserId;
    }

    // Get the latest post ID from the thread
    async getLatestPostId() {
        const posts = await this.getThreadReplies();
        const postIds = Object.keys(posts);

        if (postIds.length === 0) {
            return null;
        }

        // Sort by create_at timestamp to get the latest
        const sortedPosts = postIds
            .map(id => ({ ...posts[id], id }))
            .sort((a, b) => b.create_at - a.create_at);

        return sortedPosts[0].id;
    }

    // Find the first non-bot reply after the latest post
    async findUserReply(lastKnownPostId) {
        const posts = await this.getThreadReplies();
        const postIds = Object.keys(posts);

        if (postIds.length === 0) {
            return null;
        }

        // Filter out bot posts and find posts newer than lastKnownPostId
        const userReplies = postIds
            .map(id => ({ ...posts[id], id }))
            .filter(post => !this.isBotReply(post))
            .filter(post => !lastKnownPostId || post.create_at > posts[lastKnownPostId]?.create_at)
            .sort((a, b) => a.create_at - b.create_at);

        return userReplies.length > 0 ? userReplies[0] : null;
    }

    // Wait for a user reply with timeout
    async waitForUserReply() {
        const startTime = Date.now();
        let lastKnownPostId = await this.getLatestPostId();

        console.log(`⏳ Waiting for user reply (timeout: ${this.replyTimeoutMs}ms)`);

        while (Date.now() - startTime < this.replyTimeoutMs) {
            const userReply = await this.findUserReply(lastKnownPostId);

            if (userReply) {
                console.log(`✅ Found user reply: ${userReply.id}`);
                return userReply;
            }

            // Wait 2 seconds before checking again
            await this.sleep(2000);

            // Update last known post ID in case bot posts were added
            lastKnownPostId = await this.getLatestPostId();
        }

        console.log('⏰ Reply timeout reached, no user reply found');
        return null;
    }

    // Return JSON block response for Claude Code
    returnBlockResponse(userReply) {
        const response = {
            decision: 'block',
            reason: userReply.message || ''
        };

        console.log(JSON.stringify(response, null, 2));
        process.exit(0);
    }

    async run() {
        try {
            const input = await this.readInput();
            const message = this.extractMessage(input);

            // Send the final message to Mattermost
            await this.sendToMattermost(message);

            // Wait for user reply if timeout is set
            if (this.replyTimeoutMs > 0) {
                console.log('🔄 Reply waiting is enabled (timeout: ' + this.replyTimeoutMs + 'ms)');
                const userReply = await this.waitForUserReply();

                if (userReply) {
                    // Found a reply, return JSON block response
                    return this.returnBlockResponse(userReply);
                }
                // No reply found within timeout, continue with normal flow
                console.log('➡️ No user reply found, continuing normal flow');
            } else {
                console.log('➡️ Reply waiting is disabled (timeout: 0ms)');
            }

            process.exit(0);
        } catch (error) {
            console.error('Stop hook error:', error.message);
            process.exit(1);
        }
    }

    readInput() {
        return new Promise((resolve, reject) => {
            let data = '';
            const MAX_INPUT_SIZE = 1024 * 1024; // 1MB limit

            process.stdin.on('data', chunk => {
                if (data.length + chunk.length > MAX_INPUT_SIZE) {
                    reject(new Error('Input size exceeds maximum allowed'));
                    return;
                }
                data += chunk;
            });

            process.stdin.on('end', () => {
                try {
                    resolve(JSON.parse(data));
                } catch (error) {
                    reject(new Error(`Failed to parse JSON input: ${error.message}`));
                }
            });

            process.stdin.on('error', reject);
        });
    }

    extractMessage(input) {
        if (!input || typeof input.last_assistant_message !== 'string') {
            throw new Error('Missing or invalid last_assistant_message in input');
        }

        const message = input.last_assistant_message.trim();
        if (message.length === 0) {
            throw new Error('last_assistant_message is empty after trimming');
        }

        return message;
    }

    async sendToMattermost(message) {
        const mmAddress = process.env.MM_ADDRESS;
        const mmToken = process.env.MM_TOKEN;

        const payload = {
            channel_id: await this.getChannelIdFromThread(this.threadId),
            message: message,
            root_id: this.threadId
        };

        const url = `${mmAddress}/api/v4/posts`;
        const urlObj = new URL(url);
        const protocol = urlObj.protocol === 'https:' ? https : http;

        return new Promise((resolve, reject) => {
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
                        console.log('Message sent successfully to Mattermost');
                        resolve(data);
                    } else {
                        // Sanitize error message to avoid leaking sensitive info
                        reject(new Error(`HTTP ${response.statusCode}: Request failed`));
                    }
                });
            });

            request.on('error', reject);
            const timeoutMs = parseInt(process.env.MM_TIMEOUT_MS) || 10000;
            request.setTimeout(timeoutMs, () => {
                request.destroy();
                reject(new Error(`Mattermost API request timeout after ${timeoutMs}ms`));
            });

            request.write(JSON.stringify(payload));
            request.end();
        });
    }

    async getChannelIdFromThread(threadId) {
        const mmAddress = process.env.MM_ADDRESS;
        const mmToken = process.env.MM_TOKEN;

        console.log(`📝 Resolving channel ID for thread: ${threadId}`);

        // Get post details to extract channel_id
        const url = `${mmAddress}/api/v4/posts/${threadId}`;
        const urlObj = new URL(url);
        const protocol = urlObj.protocol === 'https:' ? https : http;

        return new Promise((resolve, reject) => {
            const request = protocol.request(urlObj, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${mmToken}`,
                    'Content-Type': 'application/json'
                }
            }, (response) => {
                let data = '';
                response.on('data', chunk => data += chunk);
                response.on('end', () => {
                    if (response.statusCode === 200) {
                        try {
                            const post = JSON.parse(data);
                            resolve(post.channel_id);
                        } catch (error) {
                            reject(new Error('Failed to parse post response'));
                        }
                    } else {
                        reject(new Error(`Failed to get post: HTTP ${response.statusCode}`));
                    }
                });
            });

            request.on('error', reject);
            request.setTimeout(5000, () => {
                request.destroy();
                reject(new Error('Thread resolution timeout after 5 seconds'));
            });

            request.end();
        });
    }
}

// Main execution
if (require.main === module) {
    const hook = new StopHook();
    hook.run().catch(error => {
        console.error('Unhandled error:', error.message);
        process.exit(1);
    });
}

module.exports = StopHook;