#!/usr/bin/env node
// Mattermost Bot Service for Claude Code Integration
// Provides bidirectional communication between Mattermost and Claude Code

const WebSocket = require('ws');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const https = require('https');
const http = require('http');
// fetch is globally available in Node.js 22+

class MattermostBot {
    constructor(config = {}) {
        // Validate required configuration parameters
        this.validateConfig(config);

        // Initialize with configuration values
        this.mmAddress = config.mmAddress;
        this.mmToken = config.mmToken;
        this.mmChannel = config.mmChannel;
        this.mmTeam = config.mmTeam || 'home';

        // Initialize session management
        this.sessions = new Map(); // threadId -> ClaudeCodeSession
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = config.maxReconnectAttempts || 5;
        this.targetChannelId = null;
        this.botThreadId = null;
    }

    // Validate environment configuration
    validateConfig(config) {
        const requiredVars = ['mmAddress', 'mmToken', 'mmChannel'];
        const missingVars = requiredVars.filter(varName => !config[varName]);

        if (missingVars.length > 0) {
            throw new Error(`Missing required configuration: ${missingVars.join(', ')}`);
        }

        // Validate mmTeam if provided
        if (config.mmTeam && typeof config.mmTeam !== 'string') {
            throw new Error('mmTeam must be a string if provided');
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
            const logPath = process.env.MM_BOT_LOG_PATH || '/tmp/mattermost-bot.log';
            try {
                fs.appendFileSync(logPath,
                    `[${timestamp}] [${errorId}] [${context}] ${error.message}\n`);
            } catch (logError) {
                // Fallback to console logging
                console.error(`Failed to write to log file ${logPath}:`, logError.message);
                console.error(`Original error [${errorId}] in ${context}:`, error.message);
            }
        }

        return errorId;
    }

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

    async resolveChannelId() {
        const mmAddress = this.mmAddress;
        const mmToken = this.mmToken;
        const channelName = this.mmChannel;

        if (!channelName) {
            throw new Error('mmChannel configuration is required');
        }

        // First, get the team ID using the team name
        const teamName = this.mmTeam;
        const teamId = await this.resolveTeamId(teamName);

        // Then get the channel using the team ID
        const url = `${mmAddress}/api/v4/teams/${teamId}/channels/name/${channelName}`;

        return new Promise((resolve, reject) => {
            const request = (mmAddress.startsWith('https') ? https : http).request(url, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${mmToken}`
                }
            }, (response) => {
                let data = '';
                response.on('data', chunk => data += chunk);
                response.on('end', () => {
                    if (response.statusCode === 200) {
                        const channel = JSON.parse(data);
                        this.targetChannelId = channel.id;
                        console.log(`Resolved channel ${channelName} to ID: ${channel.id}`);
                        resolve(channel.id);
                    } else {
                        reject(new Error(`Failed to resolve channel: HTTP ${response.statusCode}`));
                    }
                });
            });

            request.on('error', reject);
            request.end();
        });
    }

    async resolveTeamId(teamName) {
        const mmAddress = this.mmAddress;
        const mmToken = this.mmToken;

        // Get user's teams to find the correct team ID
        const url = `${mmAddress}/api/v4/users/me/teams`;

        return new Promise((resolve, reject) => {
            const request = (mmAddress.startsWith('https') ? https : http).request(url, {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${mmToken}`
                }
            }, (response) => {
                let data = '';
                response.on('data', chunk => data += chunk);
                response.on('end', () => {
                    if (response.statusCode === 200) {
                        try {
                            const teams = JSON.parse(data);
                            const targetTeam = teams.find(team =>
                                team.name.toLowerCase() === teamName.toLowerCase() ||
                                team.display_name.toLowerCase() === teamName.toLowerCase()
                            );

                            if (!targetTeam) {
                                reject(new Error(`Team "${teamName}" not found or bot is not a member`));
                                return;
                            }

                            console.log(`Resolved team ${teamName} to ID: ${targetTeam.id}`);
                            resolve(targetTeam.id);
                        } catch (error) {
                            reject(new Error(`Failed to parse teams response: ${error.message}`));
                        }
                    } else {
                        reject(new Error(`Failed to get teams: HTTP ${response.statusCode}`));
                    }
                });
            });

            request.on('error', reject);
            request.end();
        });
    }

    async connect() {
        const mmAddress = this.mmAddress;
        const mmToken = this.mmToken;

        if (!mmAddress || !mmToken) {
            throw new Error('mmAddress and mmToken configuration are required');
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

        // Only process replies to our bot thread
        // Add graceful handling for missing thread ID
        if (!this.botThreadId) {
            console.log('Bot thread ID not set, ignoring message');
            return;
        }

        if (!post.root_id || post.root_id !== this.botThreadId) {
            console.log(`Ignoring message not in bot thread: ${post.root_id}`);
            return;
        }

        // Ignore messages from the bot user itself to prevent feedback loops
        if (post.user_id === '9as575ix8fgsidymtg41eewikc') { // Bot user ID
            console.log(`Ignoring message from bot user: ${post.user_id}`);
            return;
        }

        // Add debug logging for successful thread filtering
        console.log(`Processing message in bot thread: ${post.root_id}`);

        // Handle thread replies
        this.processUserInput(post);
    }

    async getTargetChannelId() {
        if (this.targetChannelId) {
            return this.targetChannelId;
        }

        // First check for direct channel ID
        if (process.env.MM_CHANNEL_ID) {
            this.targetChannelId = process.env.MM_CHANNEL_ID;
            return this.targetChannelId;
        }

        // Resolve channel name to ID using Mattermost API
        if (this.mmChannel && this.mmChannel.trim() !== '') {
            try {
                const channelId = await this.resolveChannelByName(this.mmChannel);
                if (channelId) {
                    this.targetChannelId = channelId;
                    return this.targetChannelId;
                }
            } catch (error) {
                this.handleError(error, 'channel resolution');
                console.error('Failed to resolve channel name, falling back to MM_CHANNEL_ID lookup');
            }
        }

        // Fallback to MM_CHANNEL_ID if available
        this.targetChannelId = process.env.MM_CHANNEL_ID || '';
        return this.targetChannelId;
    }

    async resolveChannelByName(channelName) {
        const mmAddress = this.mmAddress;
        const mmToken = this.mmToken;

        if (!mmAddress || !mmToken) {
            throw new Error('Missing Mattermost configuration for channel resolution');
        }

        return new Promise((resolve, reject) => {
            // Parse the URL and determine protocol
            const url = new URL(`${mmAddress}/api/v4/channels`);
            const protocol = url.protocol === 'https:' ? require('https') : require('http');

            const options = {
                hostname: url.hostname,
                port: url.port || (url.protocol === 'https:' ? 443 : 80),
                path: url.pathname + url.search,
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${mmToken}`,
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

    async sendReply(originalPost, message) {
        const mmAddress = this.mmAddress;
        const mmToken = this.mmToken;

        // Validate required parameters
        if (!mmAddress || !mmToken) {
            throw new Error('mmAddress and mmToken configuration are required');
        }

        const payload = {
            channel_id: originalPost.channel_id,
            message: message,
            root_id: originalPost.root_id
        };

        const url = `${mmAddress}/api/v4/posts`;

        return new Promise((resolve, reject) => {
            const urlObj = new URL(url);
            const protocol = urlObj.protocol === 'https:' ? https : http;

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
                            // If parsing fails but status is good, still resolve
                            resolve(data);
                        }
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
        }, 60000); // Check every minute
    }


    // Clean up expired sessions
    cleanupExpiredSessions() {
        let expiredCount = 0;

        for (const [threadId, session] of this.sessions.entries()) {
            if (session.isExpired()) {
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
        if (!session || session.isExpired()) {
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
            !session.isExpired()
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
            mmTeam: process.env.MM_TEAM,
            maxReconnectAttempts: parseInt(process.env.MAX_RECONNECT_ATTEMPTS) || 5
        };

        const bot = new MattermostBot(config);
        await bot.initialize();

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

class PersistentSession {
    constructor(config = {}) {
        // Validate config
        if (typeof config !== 'object' || config === null) {
            throw new Error('Config must be a valid object');
        }

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
        try {
            await this.startClaudeProcess();
        } catch (error) {
            console.error('Failed to initialize PersistentSession:', error);
            throw error;
        }
    }

    async startClaudeProcess() {
        return new Promise((resolve, reject) => {
            // Security Fix 2: Configurable permission mode
            const permissionMode = process.env.CLAUDE_PERMISSION_MODE || 'default';

            // Determine which command to use
            const ccrProfile = process.env.CCR_PROFILE;
            let useCCR = ccrProfile && ccrProfile.trim() !== '';

            // Security Fix: Validate CCR_PROFILE to prevent command injection
            if (useCCR) {
                const ccrProfilePattern = /^[a-zA-Z0-9_-]+$/;
                if (!ccrProfilePattern.test(ccrProfile)) {
                    console.warn(`Invalid CCR_PROFILE format "${ccrProfile}", falling back to claude command`);
                    useCCR = false;
                }
            }

            // Check CCR availability
            let ccrAvailable = false;
            if (useCCR) {
                try {
                    const { spawnSync } = require('child_process');
                    ccrAvailable = spawnSync('which', ['ccr']).status === 0;
                } catch (error) {
                    console.warn('Failed to check ccr command availability:', error.message);
                }
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
            const MAX_BUFFER_SIZE = 1024 * 1024; // 1MB limit

            this.process.stdout.on('data', (data) => {
                const newData = data.toString();
                // Check if buffer exceeds size limit
                if (this.stdoutBuffer.length + newData.length > MAX_BUFFER_SIZE) {
                    // Keep only recent data (last 50% of buffer)
                    this.stdoutBuffer = this.stdoutBuffer.substring(this.stdoutBuffer.length - Math.floor(MAX_BUFFER_SIZE / 2));
                }
                this.stdoutBuffer += newData;
            });

            this.process.stderr.on('data', (data) => {
                const stderrData = data.toString();
                // Check if buffer exceeds size limit
                if (this.stderrBuffer.length + stderrData.length > MAX_BUFFER_SIZE) {
                    // Keep only recent data (last 50% of buffer)
                    this.stderrBuffer = this.stderrBuffer.substring(this.stderrBuffer.length - Math.floor(MAX_BUFFER_SIZE / 2));
                }
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

                    // Security Fix: Exponential backoff with limits
                    const baseDelay = 2000;
                    const maxDelay = 30000;
                    const delay = Math.min(baseDelay * Math.pow(2, this.restartAttempts - 1), maxDelay);

                    console.log(`Attempting restart ${this.restartAttempts}/${this.maxRestartAttempts} in ${delay}ms`);
                    setTimeout(() => this.startClaudeProcess(), delay);
                }
            });

            this.process.on('error', (error) => {
                console.error('Failed to start Claude process:', error.message);
                reject(error);
            });

            // Wait for process to be ready with proper readiness checking
            const checkProcessReady = () => {
                if (this.process && this.process.stdout) {
                    this.isAlive = true;
                    console.log('Claude Code process ready');
                    resolve();
                } else if (this.process) {
                    // Process exists but stdout not ready yet, retry
                    setTimeout(checkProcessReady, 100);
                } else {
                    // Process failed to start
                    reject(new Error('Claude Code process failed to initialize'));
                }
            };

            setTimeout(() => {
                checkProcessReady();
            }, 500);
        });
    }

    async sendMessage(message) {
        return new Promise((resolve, reject) => {
            if (!this.checkAlive()) {
                const error = new Error('Claude Code process is not alive');
                console.error('Cannot send message:', error.message);
                reject(error);
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

            console.log(`Queued message ${messageId} (queue size: ${this.messageQueue.length})`);

            // Process queue if not already processing
            if (!this.processing) {
                this.processQueue();
            }
        });
    }

    async processQueue() {
        if (this.processing || this.messageQueue.length === 0) {
            return;
        }

        this.processing = true;
        const message = this.messageQueue.shift();

        console.log(`Processing message ${message.id} (${message.content.length} chars)`);

        try {
            // Clear buffers for new response
            this.stdoutBuffer = '';
            this.stderrBuffer = '';

            // Send message to Claude Code
            this.process.stdin.write(message.content + '\n');
            console.log(`Sent message ${message.id} to Claude Code`);

            // Wait for response with timeout
            const response = await this.waitForResponse(30000); // 30 second timeout
            console.log(`Received response for message ${message.id}: ${response.length} chars`);
            message.resolve(response);

        } catch (error) {
            console.error(`Error processing message ${message.id}:`, error.message);
            message.reject(error);
        } finally {
            this.processing = false;

            // Process next message in queue
            if (this.messageQueue.length > 0) {
                setTimeout(() => this.processQueue(), 100);
            }
        }
    }

    waitForResponse(timeoutMs) {
        return new Promise((resolve, reject) => {
            const startTime = Date.now();
            const timeout = setTimeout(() => {
                const elapsed = Date.now() - startTime;
                console.error(`Response timeout exceeded after ${elapsed}ms`);
                reject(new Error('Response timeout exceeded'));
            }, timeoutMs);

            const checkResponse = () => {
                // Look for complete response (Claude Code typically ends with specific markers)
                if (this.stdoutBuffer.includes('\n') && this.stdoutBuffer.trim().length > 0) {
                    clearTimeout(timeout);
                    const response = this.stdoutBuffer.trim();
                    this.stdoutBuffer = '';
                    const elapsed = Date.now() - startTime;
                    console.log(`Response received after ${elapsed}ms`);
                    resolve(response);
                    return;
                }

                // Check if process died
                if (!this.checkAlive()) {
                    clearTimeout(timeout);
                    const elapsed = Date.now() - startTime;
                    console.error(`Process terminated while waiting for response (${elapsed}ms)`);
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

    checkAlive() {
        return this.isAlive && this.process && !this.process.killed;
    }

    async restart() {
        await this.destroy();
        this.restartAttempts = 0;
        await this.startClaudeProcess();
    }

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
}

// Send startup notification to Mattermost
MattermostBot.prototype.sendStartupNotification = async function() {
    const mmAddress = this.mmAddress;
    const mmToken = this.mmToken;
    const channelId = await this.getTargetChannelId();

    // Add validation for environment variables
    if (!process.env.PROMPT || !process.env.IDE_ADDRESS) {
        console.warn('Missing PROMPT or IDE_ADDRESS environment variables');
    }

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
};

class ClaudeCodeSession {
    constructor(threadId) {
        this.threadId = threadId;
        this.session = new PersistentSession();
        this.createdAt = Date.now();
        this.lastActivity = this.createdAt;
        this.maxIdleTime = 15 * 60 * 1000; // 15 minutes
        this.isInitialized = false;
    }

    async sendToClaude(message) {
        this.lastActivity = Date.now();

        try {
            // Initialize session if not already initialized
            if (!this.isInitialized) {
                console.log(`Initializing ClaudeCodeSession for thread ${this.threadId}`);
                await this.session.initialize();
                this.isInitialized = true;
                console.log(`ClaudeCodeSession initialized for thread ${this.threadId}`);
            }

            console.log(`Sending message to Claude for thread ${this.threadId}: ${message.substring(0, 100)}...`);
            const response = await this.session.sendMessage(message);
            console.log(`Received response from Claude for thread ${this.threadId}: ${response.length} chars`);
            return response;

        } catch (error) {
            console.error(`Error in ClaudeCodeSession for thread ${this.threadId}:`, error.message);
            // Reset initialization flag on error
            if (error.message.includes('process terminated') || error.message.includes('not alive')) {
                this.isInitialized = false;
            }
            throw error;
        }
    }

    isExpired() {
        return Date.now() - this.lastActivity > this.maxIdleTime;
    }

    destroy() {
        console.log(`Destroying ClaudeCodeSession for thread ${this.threadId}`);
        if (this.session) {
            this.session.destroy();
            this.session = null;
        }
        this.isInitialized = false;
        console.log(`ClaudeCodeSession destroyed for thread ${this.threadId}`);
    }
}

module.exports = { MattermostBot, PersistentSession, ClaudeCodeSession };