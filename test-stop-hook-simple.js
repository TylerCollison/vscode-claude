#!/usr/bin/env node
// Simple test for stop-hook.js file-first approach

const fs = require('fs');

class StopHookSimpleTest {
    constructor() {
        this.testFile = '/tmp/mm_thread_id';
        this.testResults = [];
    }

    async runAllTests() {
        console.log('🧪 Simple Stop Hook Tests\n');

        try {
            await this.testGetThreadIdMethod();
            await this.testFallbackLogic();
            await this.testFileErrorHandling();

            this.printResults();
        } catch (error) {
            console.error('Simple test suite error:', error.message);
            process.exit(1);
        }
    }

    async testGetThreadIdMethod() {
        const testName = 'getThreadId method with file present';

        try {
            const testThreadId = 'simple-test-thread-123';
            fs.writeFileSync(this.testFile, testThreadId);

            // Import the StopHook class
            const StopHook = require('./.claude/hooks/stop-hook.js');

            // Create instance but avoid validation by calling getThreadId directly
            const hook = Object.create(StopHook.prototype);
            const result = hook.getThreadId();

            if (result === testThreadId) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected ${testThreadId}, got ${result}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testFallbackLogic() {
        const testName = 'Fallback to environment variable';

        try {
            fs.writeFileSync(this.testFile, ''); // Empty file
            process.env.MM_THREAD_ID = 'simple-env-thread-456';

            const StopHook = require('./.claude/hooks/stop-hook.js');
            const hook = Object.create(StopHook.prototype);
            const result = hook.getThreadId();

            if (result === 'simple-env-thread-456') {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected simple-env-thread-456, got ${result}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    async testFileErrorHandling() {
        const testName = 'Error handling for missing file';

        try {
            if (fs.existsSync(this.testFile)) {
                fs.unlinkSync(this.testFile);
            }
            delete process.env.MM_THREAD_ID;

            const StopHook = require('./.claude/hooks/stop-hook.js');
            const hook = Object.create(StopHook.prototype);
            const result = hook.getThreadId();

            if (result === null) {
                this.testResults.push({ name: testName, passed: true });
                console.log(`✅ ${testName}`);
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Expected null, got ${result}`
                });
                console.log(`❌ ${testName}`);
            }
        } catch (error) {
            this.testResults.push({ name: testName, passed: false, error: error.message });
            console.log(`❌ ${testName}`);
        }
    }

    printResults() {
        console.log('\n📊 Simple Test Results Summary:');
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
            console.log('\n🎉 All simple tests passed! File-first approach is working.');
        } else {
            console.log('\n⚠️  Some simple tests failed.');
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

// Run simple tests
if (require.main === module) {
    const testSuite = new StopHookSimpleTest();

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

module.exports = StopHookSimpleTest;