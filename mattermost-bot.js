#!/usr/bin/env node
// Mattermost Bot Service for Claude Code Integration
// Provides bidirectional communication between Mattermost and Claude Code

const WebSocket = require('ws');
const { spawn } = require('child_process');
const fs = require('fs');
// fetch is globally available in Node.js 22+

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
        this.sessionConfig = {
            sessionTimeout: parseInt(config.sessionTimeout) || 3600000, // 1 hour default
            maxContextLength: parseInt(config.maxContextLength) || 4000
        };
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = config.maxReconnectAttempts || 5;

        // Start session cleanup interval
        this.startSessionCleanupInterval();
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

    // Validate Mattermost post structure
    isValidPost(post) {
        if (typeof post !== 'object' || post === null) {
            return false;
        }

        // Required fields for basic post validation
        if (typeof post.id !== 'string' || post.id.trim() === '') {
            return false;
        }

        if (typeof post.channel_id !== 'string' || post.channel_id.trim() === '') {
            return false;
        }

        // Optional fields but with type validation
        if (post.message !== undefined && typeof post.message !== 'string') {
            return false;
        }

        if (post.root_id !== undefined && typeof post.root_id !== 'string') {
            return false;
        }

        // Additional validation: ensure no malicious content patterns
        const message = post.message || '';
        if (message.length > 10000) {
            console.error('Post message exceeds maximum length');
            return false;
        }

        // Check for potential injection patterns
        const dangerousPatterns = [
            /<script[^>]*>/i,
            /javascript:/i,
            /on\w+\s*=/i,
            /data:text\/html/i
        ];

        for (const pattern of dangerousPatterns) {
            if (pattern.test(message)) {
                console.error('Potential malicious content detected in post');
                return false;
            }
        }

        return true;
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

        this.ws.on('message', async (data) => {
            try {
                const message = JSON.parse(data);
                await this.handleMessage(message);
            } catch (error) {
                const errorId = this.handleError(error, 'JSON.parse');
                console.error(`[${errorId}] Failed to parse WebSocket message: ${error.message}`);
            }
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

    async handleMessage(message) {
        // Validate WebSocket message structure first
        if (!this.isValidWebSocketMessage(message)) {
            console.error('Invalid WebSocket message structure received');
            return;
        }

        if (message.event === 'posted') {
            await this.handlePostMessage(message);
        } else if (message.event === 'hello') {
            console.log('Mattermost WebSocket handshake complete');
        }
    }

    // Validate WebSocket message structure
    isValidWebSocketMessage(message) {
        if (typeof message !== 'object' || message === null) {
            return false;
        }

        if (typeof message.event !== 'string' || message.event.trim() === '') {
            return false;
        }

        // Additional validation based on event type
        if (message.event === 'posted') {
            if (typeof message.data !== 'object' || message.data === null) {
                return false;
            }
            if (typeof message.data.post !== 'string' || message.data.post.trim() === '') {
                return false;
            }
        }

        return true;
    }

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

        // Handle thread replies (not the initial notification)
        if (post.root_id) {
            this.processUserInput(post);
        }
    }

    async getTargetChannelId() {
        // First check for direct channel ID
        if (process.env.MM_CHANNEL_ID) {
            return process.env.MM_CHANNEL_ID;
        }

        // Resolve channel name to ID using Mattermost API
        if (this.mmChannel && this.mmChannel.trim() !== '') {
            try {
                const channelId = await this.resolveChannelByName(this.mmChannel);
                if (channelId) {
                    return channelId;
                }
            } catch (error) {
                this.handleError(error, 'channel resolution');
                console.error('Failed to resolve channel name, falling back to MM_CHANNEL_ID lookup');
            }
        }

        // Fallback to MM_CHANNEL_ID if available
        return process.env.MM_CHANNEL_ID || '';
    }

    async resolveChannelByName(channelName) {
        if (!this.mmAddress || !this.mmToken) {
            throw new Error('Missing Mattermost configuration for channel resolution');
        }

        return new Promise((resolve, reject) => {
            // Parse the URL and determine protocol
            const url = new URL(`${this.mmAddress}/api/v4/channels`);
            const protocol = url.protocol === 'https:' ? require('https') : require('http');

            const options = {
                hostname: url.hostname,
                port: url.port || (url.protocol === 'https:' ? 443 : 80),
                path: url.pathname + url.search,
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${this.mmToken}`,
                    'Content-Type': 'application/json'
                }
            };

            const req = protocol.request(options, (res) => {
                let data = '';

                res.on('data', (chunk) => {
                    data += chunk;
                });

                res.on('end', () => {
                    if (res.statusCode !== 200) {
                        reject(new Error(`Mattermost API error: ${res.statusCode} ${res.statusMessage}`));
                        return;
                    }

                    try {
                        const channels = JSON.parse(data);

                        // Find channel by name (case-insensitive)
                        const targetChannel = channels.find(channel =>
                            channel.name.toLowerCase() === channelName.toLowerCase() ||
                            channel.display_name.toLowerCase() === channelName.toLowerCase()
                        );

                        if (!targetChannel) {
                            reject(new Error(`Channel "${channelName}" not found in Mattermost workspace`));
                            return;
                        }

                        console.log(`Resolved channel "${channelName}" to ID: ${targetChannel.id}`);
                        resolve(targetChannel.id);

                    } catch (error) {
                        reject(new Error(`Failed to parse API response: ${error.message}`));
                    }
                });
            });

            req.on('error', (error) => {
                reject(new Error(`HTTP request failed: ${error.message}`));
            });

            req.setTimeout(10000, () => {
                req.destroy();
                reject(new Error('Channel resolution timeout after 10 seconds'));
            });

            req.end();
        });
    }

    processUserInput(post) {
        // Sanitize and validate user input before processing
        const sanitizedMessage = this.sanitizeUserInput(post.message || '');

        if (!this.isSafeUserInput(sanitizedMessage)) {
            console.error('Potential security risk detected in user input');
            return;
        }

        // Get or create session for this thread
        const threadId = post.root_id || post.id;
        const session = this.getOrCreateSession(threadId);

        // Add user message to conversation context
        session.addToContext(sanitizedMessage, true);

        console.log(`Processing user input for thread ${threadId}:`, sanitizedMessage);
        console.log(`Active sessions: ${this.getActiveSessionCount()}`);

        // Claude Code integration will be implemented in next task
    }

    // Sanitize user input to remove potentially dangerous content
    sanitizeUserInput(input) {
        if (typeof input !== 'string') {
            return '';
        }

        // Remove potentially dangerous HTML/JavaScript
        let sanitized = input
            .replace(/<script[^>]*>.*?<\/script>/gi, '')
            .replace(/<[^>]*>/g, '') // Remove all HTML tags
            .replace(/javascript:/gi, '')
            .replace(/data:text\/html/gi, '')
            .replace(/on\w+\s*=\s*["'][^"']*["']/gi, '');

        // Truncate to reasonable length
        sanitized = sanitized.substring(0, 5000);

        return sanitized.trim();
    }

    // Additional security checks for user input
    isSafeUserInput(input) {
        if (typeof input !== 'string') {
            return false;
        }

        // Check for suspicious patterns
        const suspiciousPatterns = [
            /\{\{.*\}\}/, // Template injection patterns
            /\$\{.*\}/,   // Variable substitution patterns
            /`.*`/,       // Command execution patterns
            /exec\s*\(/,  // JavaScript exec patterns
            /eval\s*\(/,  // JavaScript eval patterns
        ];

        for (const pattern of suspiciousPatterns) {
            if (pattern.test(input)) {
                console.error('Suspicious pattern detected in user input');
                return false;
            }
        }

        // Check for excessive repetition
        if (/(.)\1{50,}/.test(input)) {
            console.error('Excessive repetition detected in user input');
            return false;
        }

        return true;
    }

    // Start periodic session cleanup
    startSessionCleanupInterval() {
        setInterval(() => {
            this.cleanupExpiredSessions();
        }, 300000); // Check every 5 minutes
    }

    // Get or create session for thread
    getOrCreateSession(threadId) {
        let session = this.sessions.get(threadId);

        if (!session || !session.isValidSession()) {
            // Create new session
            session = new ClaudeCodeSession(threadId, this.sessionConfig);
            this.sessions.set(threadId, session);
            console.log(`Created new session for thread: ${threadId}`);
        } else {
            session.updateActivity();
        }

        return session;
    }

    // Clean up expired sessions
    cleanupExpiredSessions() {
        let expiredCount = 0;

        for (const [threadId, session] of this.sessions.entries()) {
            if (session.hasTimedOut()) {
                session.destroy();
                this.sessions.delete(threadId);
                expiredCount++;
            }
        }

        if (expiredCount > 0) {
            console.log(`Cleaned up ${expiredCount} expired sessions`);
        }
    }

    // Validate session exists and is active
    validateSession(threadId, securityToken) {
        const session = this.sessions.get(threadId);
        if (!session || !session.isValidSession()) {
            return false;
        }

        // Optional security token validation
        if (securityToken && session.securityToken !== securityToken) {
            console.error('Session security token mismatch');
            return false;
        }

        return true;
    }

    // Get active session count
    getActiveSessionCount() {
        return Array.from(this.sessions.values()).filter(session =>
            session.isValidSession()
        ).length;
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

class ClaudeCodeSession {
    constructor(threadId, config = {}) {
        this.threadId = threadId;
        this.sessionId = this.generateSessionId();
        this.createdAt = Date.now();
        this.lastActivity = Date.now();
        this.timeoutMs = config.sessionTimeout || 3600000; // 1 hour default
        this.maxContextLength = config.maxContextLength || 4000;
        this.isActive = true;
        this.conversationContext = [];
        this.securityToken = this.generateSecurityToken();

        console.log(`Session created for thread ${threadId}: ${this.sessionId}`);
    }

    // Generate unique session ID
    generateSessionId() {
        return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }

    // Generate security token for session validation
    generateSecurityToken() {
        return Buffer.from(`${this.sessionId}_${Date.now()}_${Math.random().toString(36)}`).toString('base64');
    }

    // Update last activity timestamp
    updateActivity() {
        this.lastActivity = Date.now();
        this.isActive = true;
    }

    // Check if session has timed out
    hasTimedOut() {
        return Date.now() - this.lastActivity > this.timeoutMs;
    }

    // Validate session is still active and valid
    isValidSession() {
        return this.isActive && !this.hasTimedOut();
    }

    // Add message to conversation context
    addToContext(message, isUserMessage = true) {
        // Limit context length to prevent excessive memory usage
        const contextEntry = {
            timestamp: Date.now(),
            isUserMessage,
            content: message.substring(0, 1000), // Limit message length
            sessionId: this.sessionId
        };

        this.conversationContext.push(contextEntry);

        // Trim context if exceeds maximum length
        const totalLength = this.conversationContext.reduce((sum, entry) =>
            sum + entry.content.length, 0);

        while (totalLength > this.maxContextLength && this.conversationContext.length > 1) {
            this.conversationContext.shift();
        }

        this.updateActivity();
    }

    // Get conversation context as formatted string
    getContext() {
        return this.conversationContext.map(entry =>
            `${entry.isUserMessage ? 'User' : 'Assistant'}: ${entry.content}`
        ).join('\n');
    }

    // Clear session data securely
    clearSession() {
        this.conversationContext = [];
        this.isActive = false;
        console.log(`Session ${this.sessionId} cleared`);
    }

    // Destroy session and clean up
    destroy() {
        this.clearSession();
        console.log(`Session ${this.sessionId} destroyed`);
    }
}

module.exports = { MattermostBot, ClaudeCodeSession };