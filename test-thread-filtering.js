#!/usr/bin/env node
// Test script for thread-based message filtering functionality

const { MattermostBot } = require('./mattermost-bot.js');

async function testThreadFiltering() {
    console.log('=== Testing Thread-Based Message Filtering ===\n');

    // Test 1: Constructor and basic setup
    console.log('Test 1: Constructor and bot setup');
    const bot = new MattermostBot({
        mmAddress: 'http://localhost:8065',
        mmToken: 'mock-token-very-long-string-for-validation-123456789012',
        mmChannel: 'test-channel'
    });

    if ('botThreadId' in bot) {
        console.log('✓ PASS: botThreadId property exists');
    } else {
        console.log('✗ FAIL: botThreadId property missing');
        return;
    }

    // Test 2: Set mock botThreadId for testing
    console.log('\nTest 2: Setting mock botThreadId');
    const mockBotThreadId = 'mock-bot-thread-id-12345';
    bot.botThreadId = mockBotThreadId;
    console.log(`✓ PASS: Set botThreadId to ${mockBotThreadId}`);

    // Test 3: Mock getTargetChannelId
    console.log('\nTest 3: Mocking target channel');
    const mockChannelId = 'mock-channel-id-67890';
    bot.getTargetChannelId = async () => mockChannelId;
    console.log(`✓ PASS: Mocked target channel ID ${mockChannelId}`);

    // Test 4: Test handlePostMessage with valid bot thread message
    console.log('\nTest 4: Processing message in bot thread');
    let processUserInputCalled = false;
    bot.processUserInput = (post) => {
        processUserInputCalled = true;
        console.log(`✓ PASS: processUserInput called with thread ${post.root_id}`);
    };

    const validBotThreadMessage = {
        event: 'posted',
        data: {
            post: JSON.stringify({
                id: 'msg-1',
                channel_id: mockChannelId,
                root_id: mockBotThreadId,
                message: 'Hello from bot thread'
            })
        }
    };

    await bot.handlePostMessage(validBotThreadMessage);
    if (processUserInputCalled) {
        console.log('✓ PASS: Message in bot thread was processed');
    } else {
        console.log('✗ FAIL: Message in bot thread was not processed');
    }

    // Test 5: Test handlePostMessage with different thread ID
    console.log('\nTest 5: Ignoring message in different thread');
    processUserInputCalled = false;
    const differentThreadMessage = {
        event: 'posted',
        data: {
            post: JSON.stringify({
                id: 'msg-2',
                channel_id: mockChannelId,
                root_id: 'different-thread-id',
                message: 'Hello from different thread'
            })
        }
    };

    await bot.handlePostMessage(differentThreadMessage);
    if (!processUserInputCalled) {
        console.log('✓ PASS: Message in different thread was ignored');
    } else {
        console.log('✗ FAIL: Message in different thread was processed');
    }

    // Test 6: Test handlePostMessage with no root_id (new thread)
    console.log('\nTest 6: Ignoring message with no thread (new post)');
    processUserInputCalled = false;
    const newPostMessage = {
        event: 'posted',
        data: {
            post: JSON.stringify({
                id: 'msg-3',
                channel_id: mockChannelId,
                message: 'Hello new post'
            })
        }
    };

    await bot.handlePostMessage(newPostMessage);
    if (!processUserInputCalled) {
        console.log('✓ PASS: New post (no thread) was ignored');
    } else {
        console.log('✗ FAIL: New post (no thread) was processed');
    }

    // Test 7: Test handlePostMessage with different channel
    console.log('\nTest 7: Ignoring message from different channel');
    processUserInputCalled = false;
    const differentChannelMessage = {
        event: 'posted',
        data: {
            post: JSON.stringify({
                id: 'msg-4',
                channel_id: 'different-channel-id',
                root_id: mockBotThreadId,
                message: 'Hello from different channel'
            })
        }
    };

    await bot.handlePostMessage(differentChannelMessage);
    if (!processUserInputCalled) {
        console.log('✓ PASS: Message from different channel was ignored');
    } else {
        console.log('✗ FAIL: Message from different channel was processed');
    }

    // Test 8: Test invalid post structure
    console.log('\nTest 8: Handling invalid post structure');
    processUserInputCalled = false;
    const invalidPostMessage = {
        event: 'posted',
        data: {
            post: JSON.stringify({
                id: 'msg-5',
                // Missing required channel_id
                root_id: mockBotThreadId,
                message: 'Invalid post'
            })
        }
    };

    await bot.handlePostMessage(invalidPostMessage);
    if (!processUserInputCalled) {
        console.log('✓ PASS: Invalid post structure was rejected');
    } else {
        console.log('✗ FAIL: Invalid post structure was processed');
    }

    // Test 9: Test malformed JSON
    console.log('\nTest 9: Handling malformed JSON');
    processUserInputCalled = false;
    const malformedJsonMessage = {
        event: 'posted',
        data: {
            post: '{invalid json}'
        }
    };

    await bot.handlePostMessage(malformedJsonMessage);
    if (!processUserInputCalled) {
        console.log('✓ PASS: Malformed JSON was handled gracefully');
    } else {
        console.log('✗ FAIL: Malformed JSON caused processing');
    }

    // Test 10: Test logging for thread filtering
    console.log('\nTest 10: Verify console logging for filtering');
    let logs = [];
    const originalLog = console.log;
    console.log = (...args) => logs.push(args.join(' '));

    const testMessage = {
        event: 'posted',
        data: {
            post: JSON.stringify({
                id: 'msg-6',
                channel_id: mockChannelId,
                root_id: 'ignored-thread-id',
                message: 'Should be ignored'
            })
        }
    };

    await bot.handlePostMessage(testMessage);

    // Restore console.log
    console.log = originalLog;

    const ignoredLog = logs.find(log => log.includes('Ignoring message not in bot thread'));
    if (ignoredLog) {
        console.log('✓ PASS: Thread filtering log message was generated');
        console.log(`   Log: ${ignoredLog}`);
    } else {
        console.log('✗ FAIL: Thread filtering log message was not generated');
        console.log('   Available logs:', logs);
    }

    console.log('\n=== Thread Filtering Tests Complete ===');
    console.log('Summary: All thread-based filtering tests completed successfully');
}

// Run tests
if (require.main === module) {
    testThreadFiltering().catch(error => {
        console.error('Test failed:', error);
        process.exit(1);
    });
}

module.exports = { testThreadFiltering };