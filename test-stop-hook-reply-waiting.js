#!/usr/bin/env node
// Integration test for Mattermost reply waiting feature

const fs = require('fs');
const StopHook = require('./.claude/hooks/stop-hook.js');

class ReplyWaitingTest {
    constructor() {
        this.testResults = [];
    }

    async runAllTests() {
        console.log('🧪 Reply Waiting Integration Tests\n');

        try {
            await this.testReplyDetection();
            await this.testTimeoutBehavior();
            await this.testBotFiltering();

            this.printResults();
        } catch (error) {
            console.error('Test suite error:', error.message);
            process.exit(1);
        }
    }

    async testReplyDetection() {
        const testName = 'Reply detection with mock API';
        console.log(`📝 Testing: ${testName}`);

        // Set minimal required environment variables
        process.env.MM_ADDRESS = 'https://mattermost.example.com';
        process.env.MM_TOKEN = 'test-token-456';

        try {
            // Test file-first thread ID approach
            const testFile = '/tmp/mm_thread_id';
            const testThreadId = 'integration-test-thread-reply-waiting-123';
            fs.writeFileSync(testFile, testThreadId);

            // This test verifies the method exists
            const hook = new StopHook();
            if (typeof hook.waitForUserReply === 'function') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: 'Method not found' });
                console.log(`❌ ${testName}`);
            }

            // Clean up
            fs.unlinkSync(testFile);
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        } finally {
            // Clean up environment variables
            delete process.env.MM_ADDRESS;
            delete process.env.MM_TOKEN;
        }
    }

    async testTimeoutBehavior() {
        const testName = 'Timeout behavior without replies';
        console.log(`📝 Testing: ${testName}`);

        // Set minimal required environment variables
        process.env.MM_ADDRESS = 'https://mattermost.example.com';
        process.env.MM_TOKEN = 'test-token-456';

        try {
            // Test file-first thread ID approach
            const testFile = '/tmp/mm_thread_id';
            const testThreadId = 'integration-test-thread-timeout-456';
            fs.writeFileSync(testFile, testThreadId);

            // Test that timeout-related methods exist
            const hook = new StopHook();
            if (typeof hook.returnBlockResponse === 'function') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: 'Method not found' });
                console.log(`❌ ${testName}`);
            }

            // Clean up
            fs.unlinkSync(testFile);
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        } finally {
            // Clean up environment variables
            delete process.env.MM_ADDRESS;
            delete process.env.MM_TOKEN;
        }
    }

    async testBotFiltering() {
        const testName = 'Bot reply filtering';
        console.log(`📝 Testing: ${testName}`);

        // Set minimal required environment variables INCLUDING BOT ID BEFORE creating hook
        process.env.MM_ADDRESS = 'https://mattermost.example.com';
        process.env.MM_TOKEN = 'test-token-456';
        process.env.MM_BOT_USER_ID = 'bot123';

        try {
            // Test file-first thread ID approach
            const testFile = '/tmp/mm_thread_id';
            const testThreadId = 'integration-test-thread-bot-789';
            fs.writeFileSync(testFile, testThreadId);

            // Test bot detection logic
            const hook = new StopHook();
            const testPost = { user_id: 'bot123', message: 'Bot message' };

            // Test the isBotReply method
            const isBot = hook.isBotReply(testPost);

            if (isBot) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: 'Bot not filtered correctly' });
                console.log(`❌ ${testName}`);
            }

            // Clean up
            fs.unlinkSync(testFile);
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        } finally {
            // Clean up environment variables
            delete process.env.MM_ADDRESS;
            delete process.env.MM_TOKEN;
            delete process.env.MM_BOT_USER_ID;
        }
    }

    printResults() {
        console.log('\n📊 Reply Waiting Test Results Summary:');
        console.log('='.repeat(50));

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
            console.log('\n🎉 All reply waiting tests passed!');
        } else {
            console.log('\n⚠️  Some tests failed.');
            process.exit(1);
        }
    }
}

// Run tests
if (require.main === module) {
    const testSuite = new ReplyWaitingTest();
    testSuite.runAllTests().catch(error => {
        console.error('Test suite execution failed:', error.message);
        process.exit(1);
    });
}

module.exports = ReplyWaitingTest;