#!/usr/bin/env node
// Integration test for startup notification

const { MattermostBot } = require('./mattermost-bot.js');

async function testStartupNotificationIntegration() {
    console.log('=== Testing Mattermost Bot Startup Notification ===\n');

    // Test 1: Constructor validates configuration
    console.log('Test 1: Constructor validation');
    try {
        const bot1 = new MattermostBot({
            mmAddress: 'invalid-url',
            mmToken: 'short',
            mmChannel: 'test'
        });
        console.log('✗ FAIL: Should have thrown error for invalid config');
    } catch (error) {
        console.log('✓ PASS: Constructor validates configuration');
    }

    // Test 2: Constructor accepts valid configuration
    console.log('\nTest 2: Constructor accepts valid config');
    const bot2 = new MattermostBot({
        mmAddress: 'http://localhost:8065',
        mmToken: 'valid-token-very-long-string-for-validation-123456789012',
        mmChannel: 'test-channel'
    });
    console.log('✓ PASS: Constructor accepts valid configuration');

    // Test 3: botThreadId property exists
    console.log('\nTest 3: botThreadId property exists');
    if ('botThreadId' in bot2) {
        console.log('✓ PASS: botThreadId property exists');
    } else {
        console.log('✗ FAIL: botThreadId property missing');
    }

    // Test 4: sendStartupNotification method exists
    console.log('\nTest 4: sendStartupNotification method exists');
    if (typeof bot2.sendStartupNotification === 'function') {
        console.log('✓ PASS: sendStartupNotification method exists');
    } else {
        console.log('✗ FAIL: sendStartupNotification method missing');
    }

    // Test 5: Mock startup notification
    console.log('\nTest 5: Mock startup notification execution');

    // Mock getTargetChannelId
    bot2.getTargetChannelId = async () => 'mock-channel-id';

    // Mock HTTP request
    const originalRequest = require('http').request;
    const originalHttpsRequest = require('https').request;

    require('http').request = function(url, options, callback) {
        const mockResponse = {
            statusCode: 200,
            on: function(event, handler) {
                if (event === 'data') {
                    handler(Buffer.from(JSON.stringify({ id: 'test-startup-thread-id', message: 'test' })));
                } else if (event === 'end') {
                    handler();
                }
            }
        };

        setTimeout(() => callback(mockResponse), 10);

        return {
            on: () => {},
            setTimeout: () => {},
            write: () => {},
            end: () => {}
        };
    };

    require('https').request = require('http').request;

    try {
        const result = await bot2.sendStartupNotification();
        console.log('✓ PASS: sendStartupNotification executes successfully');
        console.log(`   Response ID: ${result.id}`);

        if (result.id === 'test-startup-thread-id') {
            console.log('✓ PASS: Response contains expected thread ID');
        } else {
            console.log('✗ FAIL: Response ID mismatch');
        }
    } catch (error) {
        console.log('✗ FAIL: sendStartupNotification failed');
        console.log(`   Error: ${error.message}`);
    } finally {
        // Restore original methods
        require('http').request = originalRequest;
        require('https').request = originalHttpsRequest;
    }

    console.log('\n=== Integration Tests Complete ===');
}

// Run tests
if (require.main === module) {
    testStartupNotificationIntegration().catch(error => {
        console.error('Test failed:', error);
        process.exit(1);
    });
}