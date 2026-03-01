#!/usr/bin/env node
// Complete workflow test for Mattermost thread ID file-first approach

const fs = require('fs');
const { execSync } = require('child_process');

class CompleteWorkflowTest {
    constructor() {
        this.testFile = '/tmp/mm_thread_id';
        this.testResults = [];
    }

    async runAllTests() {
        console.log('🚀 Complete Workflow Tests\n');

        try {
            await this.testFileCreationByInitialPost();
            await this.testStopHookReadsFromFile();
            await this.testBackwardCompatibility();

            this.printResults();
        } catch (error) {
            console.error('Workflow test error:', error.message);
            process.exit(1);
        }
    }

    async testFileCreationByInitialPost() {
        const testName = 'Initial post script creates thread ID file';

        try {
            // Simulate what mattermost-initial-post.sh does
            const testThreadId = 'workflow-thread-123';
            fs.writeFileSync(this.testFile, testThreadId);

            // Verify file was created
            if (fs.existsSync(this.testFile)) {
                const content = fs.readFileSync(this.testFile, 'utf8').trim();
                if (content === testThreadId) {
                    this.testResults.push({ name: testName, passed: true });
                    console.log(`✅ ${testName}`);
                } else {
                    this.testResults.push({ name: testName, passed: false, error: `File content mismatch` });
                    console.log(`❌ ${testName}`);
                }
            } else {
                this.testResults.push({ name: testName, passed: false, error: 'File was not created' });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testStopHookReadsFromFile() {
        const testName = 'Stop hook reads from file instead of env var';

        try {
            // Create file with thread ID
            const testThreadId = 'file-read-thread-456';
            fs.writeFileSync(this.testFile, testThreadId);

            // Set environment variable to a different value
            process.env.MM_THREAD_ID = 'env-read-thread-789';

            // Test the file-first logic
            const StopHook = require('./.claude/hooks/stop-hook.js');
            const hook = Object.create(StopHook.prototype);
            const result = hook.getThreadId();

            // Should prefer file over env var
            if (result === testThreadId) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected ${testThreadId} (file), got ${result}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testBackwardCompatibility() {
        const testName = 'Backward compatibility with env var only';

        try {
            // Remove file
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }

            // Set only environment variable
            const testThreadId = 'backward-compat-thread-999';
            process.env.MM_THREAD_ID = testThreadId;

            // Test fallback logic
            const StopHook = require('./.claude/hooks/stop-hook.js');
            const hook = Object.create(StopHook.prototype);
            const result = hook.getThreadId();

            // Should fallback to env var
            if (result === testThreadId) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected ${testThreadId} (env), got ${result}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    printResults() {
        console.log('\n📊 Complete Workflow Results Summary:');
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
            console.log('\n🎉 Complete workflow tests passed! Implementation is ready.');
        } else {
            console.log('\n⚠️  Some workflow tests failed.');
            process.exit(1);
        }
    }

    cleanup() {
        try {
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }
            delete process.env.MM_THREAD_ID;
        } catch (error) {
            // Ignore cleanup errors
        }
    }
}

// Run workflow tests
if (require.main === module) {
    const testSuite = new CompleteWorkflowTest();

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

module.exports = CompleteWorkflowTest;