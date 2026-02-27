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
        try {
            console.log('Mattermost bot service starting...');
            console.log(`Connecting to Mattermost server: ${this.mmAddress}`);

            // WebSocket connection logic will be implemented in next task
            // This is placeholder for the actual implementation

            console.log('Mattermost bot service initialization complete');
        } catch (error) {
            const errorId = this.handleError(error, 'connect');
            throw new Error(`Connection failed (Error ID: ${errorId})`);
        }
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