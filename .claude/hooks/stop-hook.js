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
            process.stdin.on('data', chunk => data += chunk);
            process.stdin.on('end', () => {
                try {
                    resolve(JSON.parse(data));
                } catch (error) {
                    reject(new Error('Failed to parse JSON input'));
                }
            });
            process.stdin.on('error', reject);
        });
    }

    extractMessage(input) {
        if (!input || typeof input.last_assistant_message !== 'string') {
            throw new Error('Missing or invalid last_assistant_message in input');
        }
        return input.last_assistant_message.trim();
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
                        resolve(data);
                    } else {
                        reject(new Error(`HTTP ${response.statusCode}: ${data}`));
                    }
                });
            });

            request.on('error', reject);
            request.setTimeout(10000, () => {
                request.destroy();
                reject(new Error('Mattermost API request timeout after 10 seconds'));
            });

            request.write(JSON.stringify(payload));
            request.end();
        });
    }

    async getChannelIdFromThread(threadId) {
        // For now, assume threadId is the channel ID
        // In a real implementation, we might need to resolve the channel from the thread
        return threadId;
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