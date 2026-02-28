#!/usr/bin/env node
// Test script for Mattermost Stop Hook

const { spawn } = require('child_process');
const fs = require('fs');

// Test input JSON matching Claude Code Stop hook format
const testInput = {
    session_id: "test-session-123",
    cwd: "/workspace",
    hook_event_name: "Stop",
    last_assistant_message: "Test message from Claude Code Stop hook"
};

console.log('Testing Stop hook with input:', JSON.stringify(testInput, null, 2));

// Check if hook file exists
const hookPath = '.claude/hooks/stop-hook.js';
if (!fs.existsSync(hookPath)) {
    console.error(`Error: Hook file ${hookPath} does not exist`);
    process.exit(1);
}

// Set required environment variables for testing
process.env.MM_THREAD_ID = process.env.MM_THREAD_ID || "test-thread-id";
process.env.MM_ADDRESS = process.env.MM_ADDRESS || "https://your-mattermost-server.com";
process.env.MM_TOKEN = process.env.MM_TOKEN || "test-token";

// Sanitize sensitive data for logging
const sanitizedEnv = {
    MM_THREAD_ID: process.env.MM_THREAD_ID,
    MM_ADDRESS: process.env.MM_ADDRESS,
    MM_TOKEN: "***" + process.env.MM_TOKEN.slice(-4) // Show only last 4 chars
};
console.log('Environment variables:', JSON.stringify(sanitizedEnv, null, 2));

const hookProcess = spawn(hookPath, [], {
    env: process.env,
    timeout: 15000 // 15 second timeout
});

// Handle process errors
hookProcess.on('error', (error) => {
    console.error('Failed to spawn hook process:', error.message);
    process.exit(1);
});

// Send test input to stdin
hookProcess.stdin.write(JSON.stringify(testInput));
hookProcess.stdin.end();

hookProcess.stdout.on('data', (data) => {
    console.log('STDOUT:', data.toString().trim());
});

hookProcess.stderr.on('data', (data) => {
    console.log('STDERR:', data.toString().trim());
});

hookProcess.on('close', (code) => {
    console.log(`Process exited with code ${code}`);

    // Simple test validation
    if (code === 0) {
        console.log('✅ Test PASSED - Hook executed successfully');
    } else {
        console.log('❌ Test FAILED - Hook execution failed');
    }

    process.exit(code === 0 ? 0 : 1);
});

hookProcess.on('timeout', () => {
    console.error('❌ Test FAILED - Process timeout exceeded');
    hookProcess.kill();
    process.exit(1);
});