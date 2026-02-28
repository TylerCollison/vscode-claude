#!/usr/bin/env node
// Test script for Mattermost Stop Hook

const { spawn } = require('child_process');

// Test input JSON matching Claude Code Stop hook format
const testInput = {
    session_id: "test-session-123",
    cwd: "/workspace",
    hook_event_name: "Stop",
    last_assistant_message: "Test message from Claude Code Stop hook"
};

console.log('Testing Stop hook with input:', JSON.stringify(testInput, null, 2));

// Set required environment variables for testing
process.env.MM_THREAD_ID = process.env.MM_THREAD_ID || "test-thread-id";
process.env.MM_ADDRESS = process.env.MM_ADDRESS || "https://your-mattermost-server.com";
process.env.MM_TOKEN = process.env.MM_TOKEN || "test-token";

const hookProcess = spawn('.claude/hooks/stop-hook.js', [], {
    env: process.env
});

// Send test input to stdin
hookProcess.stdin.write(JSON.stringify(testInput));
hookProcess.stdin.end();

hookProcess.stdout.on('data', (data) => {
    console.log('STDOUT:', data.toString());
});

hookProcess.stderr.on('data', (data) => {
    console.log('STDERR:', data.toString());
});

hookProcess.on('close', (code) => {
    console.log(`Process exited with code ${code}`);
});