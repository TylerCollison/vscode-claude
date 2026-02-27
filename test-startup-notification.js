#!/usr/bin/env node
// Test script for startup notification functionality

const { MattermostBot } = require('./mattermost-bot.js');

async function testSendStartupNotification() {
    console.log('Testing startup notification functionality...\n');

    // Create mock configuration
    const config = {
        mmAddress: 'http://localhost:8065',
        mmToken: 'mock-token-very-long-string-for-validation-123456789012',
        mmChannel: 'test-channel',
        mmTeam: 'home'
    };

    const bot = new MattermostBot(config);

    // Test 1: Check if method exists
    if (typeof bot.sendStartupNotification === 'function') {
        console.log('✓ Test 1 - sendStartupNotification method exists: PASS');
    } else {
        console.log('✗ Test 1 - sendStartupNotification method exists: FAIL');
        return;
    }

    // Test 2: Check if botThreadId property exists
    if ('botThreadId' in bot) {
        console.log('✓ Test 2 - botThreadId property exists: PASS');
    } else {
        console.log('✗ Test 2 - botThreadId property exists: FAIL');
    }

    // Test 3: Mock the initialize method to test the integration
    bot.resolveChannelId = async () => {
        console.log('✓ Mock resolveChannelId called');
    };

    bot.connect = async () => {
        console.log('✓ Mock connect called');
    };

    bot.startSessionCleanupInterval = () => {
        console.log('✓ Mock startSessionCleanupInterval called');
    };

    bot.getTargetChannelId = async () => 'mock-channel-id';

    // Test 4: Mock HTTP request to avoid real API calls
    const originalHttpRequest = require('http').request;
    const originalHttpsRequest = require('https').request;

    let mockRequestCalled = false;

    // Mock HTTP/HTTPS request
    const mockRequest = function(url, options, callback) {
        mockRequestCalled = true;

        // Create mock response
        const mockResponse = {
            statusCode: 200,
            on: function(event, handler) {
                if (event === 'data') {
                    handler(Buffer.from(JSON.stringify({ id: 'test-thread-id', message: 'test' })));
                } else if (event === 'end') {
                    handler();
                }
            }
        };

        setTimeout(() => {
            callback(mockResponse);
        }, 10);

        return {
            on: () => {},
            setTimeout: () => {},
            write: () => {},
            end: () => {}
        };
    };

    require('http').request = mockRequest;
    require('https').request = mockRequest;

    try {
        await bot.initialize();
        console.log('✓ Test 3 - initialize executes without error: PASS');

        if (mockRequestCalled) {
            console.log('✓ Test 4 - HTTP request was made: PASS');
        } else {
            console.log('✗ Test 4 - HTTP request was made: FAIL');
        }

        if (bot.botThreadId === 'test-thread-id') {
            console.log('✓ Test 5 - botThreadId was set correctly: PASS');
        } else {
            console.log(`✗ Test 5 - botThreadId was set correctly: FAIL (got: ${bot.botThreadId})`);
        }
    } catch (error) {
        console.log('✗ Test 3 - initialize executes without error: FAIL');
        console.log(`  Error: ${error.message}`);
    } finally {
        // Restore original HTTP request methods
        require('http').request = originalHttpRequest;
        require('https').request = originalHttpsRequest;
    }

    console.log('\nStartup notification tests completed.');
}

// Run tests
if (require.main === module) {
    testSendStartupNotification().catch(error => {
        console.error('Test failed:', error);
        process.exit(1);
    });
}

module.exports = { testSendStartupNotification };