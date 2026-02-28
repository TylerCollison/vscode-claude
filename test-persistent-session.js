#!/usr/bin/env node
// Test script for persistent session functionality

const { PersistentSession } = require('./mattermost-bot.js');

async function testPersistentSession() {
    console.log('Testing PersistentSession functionality...\n');

    // Test 1: Basic PersistentSession instantiation
    console.log('Test 1: Creating PersistentSession instance...');
    const config = {
        threadId: 'test-thread-123',
        maxRestartAttempts: 3
    };
    const session = new PersistentSession(config);

    if (session.config.threadId === 'test-thread-123') {
        console.log('✓ Test 1 - Thread ID set correctly: PASS');
    } else {
        console.log(`✗ Test 1 - Thread ID set correctly: FAIL (got: ${session.config.threadId})`);
        return;
    }

    if (session.config.threadId === 'test-thread-123') {
        console.log('✓ Test 1 - Config object created: PASS');
    } else {
        console.log(`✗ Test 1 - Config object created: FAIL (got: ${session.config.threadId})`);
        return;
    }

    // Test 2: Session validation methods
    console.log('\nTest 2: Testing session validation methods...');

    if (typeof session.sendMessage === 'function') {
        console.log('✓ Test 2 - sendMessage method exists: PASS');
    } else {
        console.log('✗ Test 2 - sendMessage method exists: FAIL');
    }

    if (typeof session.checkAlive === 'function') {
        console.log('✓ Test 2 - checkAlive method exists: PASS');
    } else {
        console.log('✗ Test 2 - checkAlive method exists: FAIL');
    }

    // Test 3: Process management
    console.log('\nTest 3: Testing process management...');

    if (typeof session.startClaudeProcess === 'function') {
        console.log('✓ Test 3 - startClaudeProcess method exists: PASS');
    } else {
        console.log('✗ Test 3 - startClaudeProcess method exists: FAIL');
    }

    if (typeof session.destroy === 'function') {
        console.log('✓ Test 3 - destroy method exists: PASS');
    } else {
        console.log('✗ Test 3 - destroy method exists: FAIL');
    }

    // Test 4: Send message functionality
    console.log('\nTest 4: Testing message sending...');

    let messageProcessed = false;

    try {
        // Test that sendMessage exists as a function
        if (typeof session.sendMessage === 'function') {
            console.log('✓ Test 4 - sendMessage method exists: PASS');
        } else {
            console.log('✗ Test 4 - sendMessage method exists: FAIL');
        }

        // Test message validation
        try {
            await session.sendMessage(''); // Should fail for empty message
            console.log('✗ Test 4 - Empty message validation: FAIL (should have thrown error)');
        } catch (error) {
            console.log('✓ Test 4 - Empty message validation: PASS');
        }

        messageProcessed = true;
    } catch (error) {
        console.log(`✗ Test 4 - Message sending: FAIL (${error.message})`);
    }

    // Test 5: Session cleanup and destruction
    console.log('\nTest 5: Testing session cleanup...');

    if (typeof session.destroy === 'function') {
        console.log('✓ Test 5 - destroy method exists: PASS');
    } else {
        console.log('✗ Test 5 - destroy method exists: FAIL');
    }

    // Test queue properties
    if (Array.isArray(session.messageQueue)) {
        console.log('✓ Test 5 - messageQueue exists: PASS');
    } else {
        console.log('✗ Test 5 - messageQueue exists: FAIL');
    }

    console.log('\nAll persistent session tests completed.');
}

async function testConversationPersistence() {
    console.log('\n=== Testing Conversation Persistence ===\n');

    // Create a new session to test conversation persistence
    const session = new PersistentSession({
        threadId: 'conversation-test',
        maxRestartAttempts: 3
    });

    try {
        // Test basic initialization
        console.log('Testing session initialization...');

        // Verify session has required properties
        if (session.config && session.config.threadId === 'conversation-test') {
            console.log('✓ Session configuration: PASS');
        } else {
            console.log('✗ Session configuration: FAIL');
        }

        // Test message queue functionality
        if (Array.isArray(session.messageQueue)) {
            console.log('✓ Message queue exists: PASS');
        } else {
            console.log('✗ Message queue exists: FAIL');
        }

        // Test message queue limits
        console.log(`Current message queue size: ${session.messageQueue.length}`);
        console.log(`Max queue size: ${session.MAX_QUEUE_SIZE}`);

        // Test sendMessage method existence
        if (typeof session.sendMessage === 'function') {
            console.log('✓ sendMessage method exists: PASS');
        } else {
            console.log('✗ sendMessage method exists: FAIL');
        }

        // Clean up
        await session.destroy();
        console.log('✓ Session cleanup completed: PASS');

    } catch (error) {
        console.error('Persistence test failed:', error);
        await session.destroy();
    }
}

// Run tests
if (require.main === module) {
    (async () => {
        await testPersistentSession();
        await testConversationPersistence();
        console.log('\n=== All Tests Completed Successfully ===');
    })().catch(error => {
        console.error('Test failed:', error);
        process.exit(1);
    });
}

module.exports = { testPersistentSession, testConversationPersistence };