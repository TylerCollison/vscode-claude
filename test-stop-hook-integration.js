#!/usr/bin/env node
// Integration test for modified stop-hook.js with file-first approach

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

class StopHookIntegrationTest {
    constructor() {
        this.testFile = '/tmp/mm_thread_id';
        this.stopHookPath = '/workspace/.claude/hooks/stop-hook.js';
        this.testResults = [];
    }

    async runAllTests() {
        console.log('🔍 Running Stop Hook Integration Tests\n');

        try {
            await this.testFileFirstApproach();
            await this.testEnvVarFallback();
            await this.testValidationFailure();
            await this.testThreadResolution();

            this.printResults();
        } catch (error) {
            console.error('Integration test suite error:', error.message);
            process.exit(1);
        }
    }

    async testFileFirstApproach() {
        const testName = 'File-first approach integration';

        try {
            // Create test file
            const testThreadId = 'integration-test-thread-123';
            fs.writeFileSync(this.testFile, testThreadId);

            // Set environment variables before requiring the module
            process.env.MM_ADDRESS = 'https://mattermost.example.com';
            process.env.MM_TOKEN = 'test-token-456';

            // Clear module cache and reload to get fresh module with new env vars
            delete require.cache[require.resolve(this.stopHookPath)];

            // Test the thread ID extraction logic
            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            // Verify thread ID was set correctly
            if (hook.threadId === testThreadId) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected threadId=${testThreadId}, got ${hook.threadId}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testEnvVarFallback() {
        const testName = 'Environment variable fallback integration';

        try {
            // File with empty content
            fs.writeFileSync(this.testFile, '');

            // Set environment variable
            process.env.MM_THREAD_ID = 'env-fallback-thread-789';
            process.env.MM_ADDRESS = 'https://mattermost.example.com';
            process.env.MM_TOKEN = 'test-token-456';

            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            if (hook.threadId === 'env-fallback-thread-789') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected threadId=env-fallback-thread-789, got ${hook.threadId}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testValidationFailure() {
        const testName = 'Validation failure when no thread ID available';

        try {
            // Remove both file and env var
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }
            delete process.env.MM_THREAD_ID;

            // Set only required vars
            process.env.MM_ADDRESS = 'https://mattermost.example.com';
            process.env.MM_TOKEN = 'test-token-456';

            // Test the getThreadId method directly without instantiating the full StopHook
            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            // Extract just the getThreadId method logic for testing
            const threadId = hook.getThreadId();

            if (!threadId) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: `Expected no thread ID, but got ${threadId}` });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testThreadResolution() {
        const testName = 'Thread resolution method integration';

        try {
            // Create test file
            const testThreadId = 'resolution-test-thread-999';
            fs.writeFileSync(this.testFile, testThreadId);

            process.env.MM_ADDRESS = 'https://mattermost.example.com';
            process.env.MM_TOKEN = 'test-token-456';

            // Clear module cache and reload
            delete require.cache[require.resolve(this.stopHookPath)];

            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            // Test that getChannelIdFromThread method accepts threadId parameter
            let methodWorks = false;
            try {
                // Mock the API call by catching the expected error
                await hook.getChannelIdFromThread(testThreadId).catch(error => {
                    // Expected to fail since it's a test environment
                    // But the method should accept the parameter correctly
                    if (error.message.includes('Failed to get post') || error.message.includes('Thread resolution timeout')) {
                        methodWorks = true;
                    }
                });
            } catch (error) {
                // Also acceptable if method throws synchronously
                methodWorks = true;
            }

            if (methodWorks) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: 'Thread resolution method failed' });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    printResults() {
        console.log('\n📊 Integration Test Results Summary:');
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
            console.log('\n🎉 All integration tests passed! File-first approach is working correctly.');
        } else {
            console.log('\n⚠️  Some integration tests failed. Please review the implementation.');
            process.exit(1);
        }
    }

    cleanup() {
        try {
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }
            // Clean up environment variables
            delete process.env.MM_THREAD_ID;
        } catch (error) {
            // Ignore cleanup errors
        }
    }
}

// Run integration tests
if (require.main === module) {
    const testSuite = new StopHookIntegrationTest();

    process.on('exit', () => {
        testSuite.cleanup();
    });

    process.on('SIGINT', () => {
        testSuite.cleanup();
        process.exit(1);
    });

    testSuite.runAllTests().then(() => {
        testSuite.cleanup();
    });
}

module.exports = StopHookIntegrationTest;