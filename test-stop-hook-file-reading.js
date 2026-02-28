#!/usr/bin/env node
// Test script for Stop Hook file-first thread ID approach

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

class StopHookFileReadingTest {
    constructor() {
        this.testFile = '/tmp/mm_thread_id';
        this.testResults = [];
    }

    async runAllTests() {
        console.log('🧪 Running Stop Hook File Reading Tests\n');

        try {
            await this.testFileCreation();
            await this.testFileReading();
            await this.testFileEmpty();
            await this.testFileMissing();
            await this.testEnvVarFallback();
            await this.testNoThreadIdAvailable();
            await this.testErrorLogging();

            this.printResults();
        } catch (error) {
            console.error('Test suite error:', error.message);
            process.exit(1);
        }
    }

    async testFileCreation() {
        const testName = 'File creation with valid thread ID';

        try {
            // Clean up any existing test file
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }

            // Create test file
            const testThreadId = 'test-thread-123';
            fs.writeFileSync(this.testFile, testThreadId);

            // Verify file exists and content is correct
            const content = fs.readFileSync(this.testFile, 'utf8').trim();

            if (content === testThreadId) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({ name: testName, passed: false, error: `Expected ${testThreadId}, got ${content}` });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testFileReading() {
        const testName = 'File reading with valid thread ID';

        try {
            const testThreadId = 'thread-456-def';
            fs.writeFileSync(this.testFile, testThreadId);

            // Simulate the file reading logic that will be implemented in stop-hook.js
            let threadId = null;
            let source = null;

            if (fs.existsSync(this.testFile)) {
                const content = fs.readFileSync(this.testFile, 'utf8').trim();
                if (content) {
                    threadId = content;
                    source = 'file';
                }
            }

            if (!threadId && process.env.MM_THREAD_ID) {
                threadId = process.env.MM_THREAD_ID;
                source = 'env';
            }

            if (threadId === testThreadId && source === 'file') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected threadId=${testThreadId}, source=file, got threadId=${threadId}, source=${source}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testFileEmpty() {
        const testName = 'File exists but is empty (should fallback to env)';

        try {
            fs.writeFileSync(this.testFile, '');
            process.env.MM_THREAD_ID = 'env-thread-789';

            let threadId = null;
            let source = null;

            if (fs.existsSync(this.testFile)) {
                const content = fs.readFileSync(this.testFile, 'utf8').trim();
                if (content) {
                    threadId = content;
                    source = 'file';
                }
            }

            if (!threadId && process.env.MM_THREAD_ID) {
                threadId = process.env.MM_THREAD_ID;
                source = 'env';
            }

            if (threadId === 'env-thread-789' && source === 'env') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected threadId=env-thread-789, source=env, got threadId=${threadId}, source=${source}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testFileMissing() {
        const testName = 'File does not exist (should fallback to env)';

        try {
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }
            process.env.MM_THREAD_ID = 'missing-file-env-123';

            let threadId = null;
            let source = null;

            if (fs.existsSync(this.testFile)) {
                const content = fs.readFileSync(this.testFile, 'utf8').trim();
                if (content) {
                    threadId = content;
                    source = 'file';
                }
            }

            if (!threadId && process.env.MM_THREAD_ID) {
                threadId = process.env.MM_THREAD_ID;
                source = 'env';
            }

            if (threadId === 'missing-file-env-123' && source === 'env') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected threadId=missing-file-env-123, source=env, got threadId=${threadId}, source=${source}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testEnvVarFallback() {
        const testName = 'Environment variable fallback';

        try {
            // File with empty content and env var set
            fs.writeFileSync(this.testFile, '\n\n   \n'); // whitespace only
            process.env.MM_THREAD_ID = 'env-fallback-456';

            let threadId = null;
            let source = null;

            if (fs.existsSync(this.testFile)) {
                const content = fs.readFileSync(this.testFile, 'utf8').trim();
                if (content) {
                    threadId = content;
                    source = 'file';
                }
            }

            if (!threadId && process.env.MM_THREAD_ID) {
                threadId = process.env.MM_THREAD_ID;
                source = 'env';
            }

            if (threadId === 'env-fallback-456' && source === 'env') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected threadId=env-fallback-456, source=env, got threadId=${threadId}, source=${source}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testNoThreadIdAvailable() {
        const testName = 'No thread ID available (should throw error)';

        try {
            // Remove both file and env var
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }
            delete process.env.MM_THREAD_ID;

            let threadId = null;
            let errorThrown = false;

            try {
                if (fs.existsSync(this.testFile)) {
                    const content = fs.readFileSync(this.testFile, 'utf8').trim();
                    if (content) {
                        threadId = content;
                    }
                }

                if (!threadId && process.env.MM_THREAD_ID) {
                    threadId = process.env.MM_THREAD_ID;
                }

                if (!threadId) {
                    throw new Error('No thread ID available from file or environment');
                }
            } catch (error) {
                errorThrown = true;
            }

            if (errorThrown && !threadId) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected error to be thrown, got threadId=${threadId}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testErrorLogging() {
        const testName = 'Error logging for debugging';

        try {
            fs.writeFileSync(this.testFile, 'debug-thread-999');
            delete process.env.MM_THREAD_ID;

            let threadId = null;
            let source = null;

            if (fs.existsSync(this.testFile)) {
                console.log('📝 Log: Reading thread ID from file');
                const content = fs.readFileSync(this.testFile, 'utf8').trim();
                if (content) {
                    threadId = content;
                    source = 'file';
                    console.log(`📝 Log: Using thread ID from file: ${threadId}`);
                }
            }

            if (!threadId && process.env.MM_THREAD_ID) {
                console.log('📝 Log: Falling back to environment variable');
                threadId = process.env.MM_THREAD_ID;
                source = 'env';
                console.log(`📝 Log: Using thread ID from env: ${threadId}`);
            }

            if (threadId === 'debug-thread-999' && source === 'file') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected threadId=debug-thread-999, source=file, got threadId=${threadId}, source=${source}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    printResults() {
        console.log('\n📊 Test Results Summary:');
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
            console.log('\n🎉 All tests passed! Ready to implement file-first approach.');
        } else {
            console.log('\n⚠️  Some tests failed. Please review before implementation.');
            process.exit(1);
        }
    }

    cleanup() {
        try {
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }
        } catch (error) {
            // Ignore cleanup errors
        }
    }
}

// Run tests
if (require.main === module) {
    const testSuite = new StopHookFileReadingTest();

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

module.exports = StopHookFileReadingTest;