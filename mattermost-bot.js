#!/usr/bin/env node
// Mattermost Bot Service for Claude Code Integration
// Provides bidirectional communication between Mattermost and Claude Code

const WebSocket = require('ws');
const { spawn } = require('child_process');
const fs = require('fs');

class MattermostBot {
    constructor(config = {}) {
        // Validate required configuration parameters
        this.validateConfig(config);

        // Initialize with configuration values
        this.mmAddress = config.mmAddress;
        this.mmToken = config.mmToken;
        this.mmChannel = config.mmChannel;

        // Initialize session management
        this.sessions = new Map(); // threadId -> ClaudeCodeSession
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = config.maxReconnectAttempts || 5;
    }

    // Validate environment configuration
    validateConfig(config) {
        const requiredVars = ['mmAddress', 'mmToken'];
        const missingVars = requiredVars.filter(varName => !config[varName]);

        if (missingVars.length > 0) {
            throw new Error(`Missing required configuration: ${missingVars.join(', ')}`);
        }

        // Validate MM_ADDRESS format
        if (!this.isValidUrl(config.mmAddress)) {
            throw new Error('MM_ADDRESS must be a valid URL with http:// or https:// protocol');
        }

        // Validate MM_TOKEN format (should be non-empty string)
        if (typeof config.mmToken !== 'string' || config.mmToken.trim() === '') {
            throw new Error('MM_TOKEN must be a non-empty string');
        }

        // Validate MM_TOKEN doesn't contain sensitive patterns
        if (config.mmToken.length < 20) {
            throw new Error('MM_TOKEN appears to be too short - should be a valid Mattermost token');
        }
    }

    // Validate URL format
    isValidUrl(string) {
        try {
            const url = new URL(string);
            return url.protocol === 'http:' || url.protocol === 'https:';
        } catch (_) {
            return false;
        }
    }

    // Secure error handler
    handleError(error, context = 'Unknown') {
        const timestamp = new Date().toISOString();
        const errorId = Math.random().toString(36).substring(2, 15);

        // Log securely without exposing sensitive information
        console.error(`[${timestamp}] [${errorId}] Error in ${context}: ${error.message}`);

        // Optionally log to file in production
        if (process.env.NODE_ENV === 'production') {
            fs.appendFileSync('/var/log/mattermost-bot.log',
                `[${timestamp}] [${errorId}] [${context}] ${error.message}\n`);
        }

        return errorId;
    }

    async connect() {
        const mmAddress = this.mmAddress;
        const mmToken = this.mmToken;

        if (!mmAddress || !mmToken) {
            throw new Error('MM_ADDRESS and MM_TOKEN environment variables required');
        }

        // Extract base URL and create WebSocket URL
        const baseUrl = mmAddress.replace(/^http/, 'ws');
        const wsUrl = `${baseUrl}/api/v4/websocket`;

        console.log(`Connecting to Mattermost WebSocket: ${wsUrl}`);

        this.ws = new WebSocket(wsUrl, {
            headers: {
                'Authorization': `Bearer ${mmToken}`
            }
        });

        this.setupWebSocketHandlers();
    }

    setupWebSocketHandlers() {
        this.ws.on('open', () => {
            console.log('Connected to Mattermost WebSocket');
            this.reconnectAttempts = 0;
        });

        this.ws.on('message', (data) => {
            this.handleMessage(JSON.parse(data));
        });

        this.ws.on('close', () => {
            console.log('WebSocket connection closed');
            this.attemptReconnect();
        });

        this.ws.on('error', (error) => {
            console.error('WebSocket error:', error);
        });
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
            console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

            setTimeout(() => {
                this.connect().catch(console.error);
            }, delay);
        }
    }

    handleMessage(message) {
        if (message.event === 'posted') {
            this.handlePostMessage(message);
        } else if (message.event === 'hello') {
            console.log('Mattermost WebSocket handshake complete');
        }
    }

    handlePostMessage(message) {
        const post = JSON.parse(message.data.post);

        // Only process messages in the target channel
        if (post.channel_id !== this.getTargetChannelId()) {
            return;
        }

        // Handle thread replies (not the initial notification)
        if (post.root_id) {
            this.processUserInput(post);
        }
    }

    getTargetChannelId() {
        // This will be implemented when we resolve channel names
        return process.env.MM_CHANNEL_ID || '';
    }

    processUserInput(post) {
        console.log('Processing user input:', post.message);
        // Claude Code integration will be implemented in next task
    }

    // Session management methods will be implemented in later tasks
}

// Main execution with secure error handling
async function main() {
    try {
        // Load configuration from environment variables
        const config = {
            mmAddress: process.env.MM_ADDRESS,
            mmToken: process.env.MM_TOKEN,
            mmChannel: process.env.MM_CHANNEL,
            maxReconnectAttempts: parseInt(process.env.MAX_RECONNECT_ATTEMPTS) || 5
        };

        const bot = new MattermostBot(config);
        await bot.connect();

        console.log('Mattermost bot service running successfully');

        // Keep the process alive
        process.on('SIGINT', () => {
            console.log('Shutting down Mattermost bot service...');
            process.exit(0);
        });

        process.on('SIGTERM', () => {
            console.log('Shutting down Mattermost bot service...');
            process.exit(0);
        });

    } catch (error) {
        console.error('Fatal error starting Mattermost bot service:', error.message);
        process.exit(1);
    }
}

// Only run if this file is executed directly
if (require.main === module) {
    main().catch(error => {
        console.error('Unhandled error in Mattermost bot service:', error.message);
        process.exit(1);
    });
}

module.exports = MattermostBot;