#!/usr/bin/env node
// Claude Code Stop Hook for Mattermost Integration
// Sends last assistant message as reply to Mattermost thread

const https = require('https');
const http = require('http');

class StopHook {
    constructor() {
        this.validateEnvironment();
    }

    validateEnvironment() {
        const requiredVars = ['MM_THREAD_ID', 'MM_ADDRESS', 'MM_TOKEN'];
        const missingVars = requiredVars.filter(varName => !process.env[varName]);

        if (missingVars.length > 0) {
            console.error(`Missing required environment variables: ${missingVars.join(', ')}`);
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
    }

    async run() {
        try {
            const input = await this.readInput();
            const message = this.extractMessage(input);
            await this.sendToMattermost(message);
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
        const threadId = process.env.MM_THREAD_ID;

        const payload = {
            channel_id: await this.getChannelIdFromThread(threadId),
            message: message,
            root_id: threadId
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