#!/usr/bin/env node
// Test script for the new reply waiting functionality in stop-hook.js

const fs = require('fs');

class ReplyWaitingTest {
    constructor() {
        this.stopHookPath = '/workspace/.claude/hooks/stop-hook.js';
        this.testFile = '/tmp/mm_thread_id';
        this.testResults = [];
    }

    async runTests() {
        console.log('🔍 Testing Reply Waiting Functionality\n');

        await this.testEnvironmentVariables();
        await this.testSleepMethod();
        await this.testIsBotReplyMethod();
        await this.testReturnBlockResponseMethod();
        await this.testFeatureDisabledByDefault();

        this.printResults();
    }

    async testEnvironmentVariables() {
        const testName = 'Environment variable setup';

        try {
            // Create test file
            fs.writeFileSync(this.testFile, 'test-thread-123');

            // Set environment variables
            process.env.MM_ADDRESS = 'https://mattermost.example.com';
            process.env.MM_TOKEN = 'test-token-456';
            process.env.REPLY_TIMEOUT_MS = '5000';
            process.env.BOT_USER_ID = 'bot-user-789';
            process.env.WAIT_FOR_REPLY = 'true';

            // Load stop-hook
            delete require.cache[require.resolve(this.stopHookPath)];
            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            // Test environment variables are set correctly
            const tests = [
                hook.replyTimeoutMs === 5000,
                hook.botUserId === 'bot-user-789',
                hook.waitForReplyEnabled === true
            ];

            if (tests.every(test => test)) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: 'Environment variables not set correctly' });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testSleepMethod() {
        const testName = 'Sleep method functionality';

        try {
            fs.writeFileSync(this.testFile, 'test-thread-123');
            process.env.MM_ADDRESS = 'https://mattermost.example.com';
            process.env.MM_TOKEN = 'test-token-456';

            delete require.cache[require.resolve(this.stopHookPath)];
            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            // Test that sleep returns a promise
            const sleepResult = hook.sleep(100);

            if (sleepResult && typeof sleepResult.then === 'function') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: 'Sleep method does not return a promise' });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testIsBotReplyMethod() {
        const testName = 'Bot reply filtering';

        try {
            fs.writeFileSync(this.testFile, 'test-thread-123');
            process.env.MM_ADDRESS = 'https://mattermost.example.com';
            process.env.MM_TOKEN = 'test-token-456';

            delete require.cache[require.resolve(this.stopHookPath)];
            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            // Test without bot user ID set
            const post1 = { user_id: 'user-123' };
            const result1 = hook.isBotReply(post1);

            // Set bot user ID and test again
            hook.botUserId = 'bot-user-789';
            const post2 = { user_id: 'bot-user-789' };
            const post3 = { user_id: 'user-456' };
            const result2 = hook.isBotReply(post2);
            const result3 = hook.isBotReply(post3);

            const tests = [
                result1 === false,
                result2 === true,
                result3 === false
            ];

            if (tests.every(test => test)) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: 'Bot reply filtering not working correctly' });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testReturnBlockResponseMethod() {
        const testName = 'Block response generation';

        try {
            fs.writeFileSync(this.testFile, 'test-thread-123');
            process.env.MM_ADDRESS = 'https://mattermost.example.com';
            process.env.MM_TOKEN = 'test-token-456';

            delete require.cache[require.resolve(this.stopHookPath)];
            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            const mockReply = {
                id: 'reply-post-123',
                message: 'This is a test reply',
                channel_id: 'channel-456',
                user_id: 'user-789',
                create_at: Date.now()
            };

            // Capture console.log output
            const originalLog = console.log;
            let capturedOutput = '';
            console.log = (msg) => {
                capturedOutput = msg;
                // Restore original log to avoid interference with test output
                console.log = originalLog;
            };

            // Temporarily override process.exit to prevent actual exit
            const originalExit = process.exit;
            let exitCalled = false;
            process.exit = (code) => {
                exitCalled = true;
                // Restore original exit
                process.exit = originalExit;
                return;
            };

            try {
                hook.returnBlockResponse(mockReply);

                // Check if exit was called
                if (exitCalled) {
                    const response = JSON.parse(capturedOutput);

                    const expectedStructure = {
                        type: 'block',
                        action: 'add',
                        block: {
                            type: 'waiting_reply_interceptor',
                            content: {
                                user_reply: mockReply.message,
                                reply_id: mockReply.id,
                                channel_id: mockReply.channel_id,
                                user_id: mockReply.user_id,
                                timestamp: mockReply.create_at
                            }
                        }
                    };

                    if (JSON.stringify(response) === JSON.stringify(expectedStructure)) {
                        this.testResults.push({ name: testName, passed: true });
                        console.log(`✅ ${testName}`);
                    } else {
                        this.testResults.push({ name: testName, passed: false, error: 'Block response structure incorrect' });
                        console.log(`❌ ${testName}`);
                    }
                } else {
                    this.testResults.push({ name: testName, passed: false, error: 'process.exit was not called' });
                    console.log(`❌ ${testName}`);
                }
            } finally {
                // Restore original process.exit
                process.exit = originalExit;
                console.log = originalLog;
            }

            // Restore console.log
            console.log = originalLog;

        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testFeatureDisabledByDefault() {
        const testName = 'Feature disabled by default';

        try {
            fs.writeFileSync(this.testFile, 'test-thread-123');
            process.env.MM_ADDRESS = 'https://mattermost.example.com';
            process.env.MM_TOKEN = 'test-token-456';
            delete process.env.WAIT_FOR_REPLY;

            delete require.cache[require.resolve(this.stopHookPath)];
            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            if (hook.waitForReplyEnabled === false) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: 'Feature should be disabled by default' });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    printResults() {
        console.log('\n📊 Reply Waiting Test Results Summary:');
        console.log('='.repeat(60));

        const passed = this.testResults.filter(r => r.passed).length;
        const total = this.testResults.length;

        console.log(`Passed: ${passed}/${total}`);

        const failedTests = this.testResults.filter(r => !r.passed);
        if (failedTests.length > 0) {
            console.log('\n❌ Failed Tests:');
            failedTests.forEach(test => {
                console.log(`   - ${test.name}: ${test.error}`);
            });
        }

        if (passed === total) {
            console.log('\n🎉 All reply waiting tests passed! Core functionality is working correctly.');
        } else {
            console.log('\n⚠️  Some tests failed. Please review the implementation.');
            process.exit(1);
        }
    }

    cleanup() {
        try {
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }
            delete process.env.WAIT_FOR_REPLY;
            delete process.env.REPLY_TIMEOUT_MS;
            delete process.env.BOT_USER_ID;
        } catch (error) {
            // Ignore cleanup errors
        }
    }
}

// Run tests
if (require.main === module) {
    const testSuite = new ReplyWaitingTest();

    process.on('exit', () => {
        testSuite.cleanup();
    });

    process.on('SIGINT', () => {
        testSuite.cleanup();
        process.exit(1);
    });

    testSuite.runTests().then(() => {
        testSuite.cleanup();
    });
}

module.exports = ReplyWaitingTest;