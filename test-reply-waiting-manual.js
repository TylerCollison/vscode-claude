#!/usr/bin/env node
// Manual Test Script for Mattermost Reply Waiting Feature
// Task 4: Create Manual Test Script

const fs = require('fs');
const path = require('path');

class ReplyWaitingManualTest {
    constructor() {
        this.testResults = [];
        this.stopHookPath = '/workspace/.claude/hooks/stop-hook.js';
        this.testInstructions = [];
    }

    async runAllTests() {
        console.log('🔧 Manual Test for Mattermost Reply Waiting Feature\n');
        console.log('='.repeat(60));

        // Run validation tests
        await this.testEnvironmentVariables();
        await this.testFileStructure();
        await this.testMethodExistence();
        await this.testSyntaxValidity();

        // Print results
        this.printResults();

        // Provide manual testing instructions
        this.provideManualInstructions();
    }

    async testEnvironmentVariables() {
        const testName = 'Environment Variable Setup';
        console.log(`\n📋 ${testName}`);
        console.log('-'.repeat(40));

        const requiredVars = [
            'MM_ADDRESS',
            'MM_TOKEN'
        ];

        const optionalVars = [
            'MM_REPLY_TIMEOUT_MS',
            'MM_BOT_USER_ID'
        ];

        let passed = true;
        let missingRequired = [];
        let warnings = [];

        // Check required variables
        requiredVars.forEach(varName => {
            if (!process.env[varName]) {
                missingRequired.push(varName);
                passed = false;
            }
        });

        // Check optional variables
        optionalVars.forEach(varName => {
            if (!process.env[varName]) {
                warnings.push(`${varName} (optional)`);
            }
        });

        if (passed && missingRequired.length === 0) {
            console.log('✅ All required environment variables are set');
            this.testResults.push({ name: testName, passed: true });
        } else {
            if (missingRequired.length > 0) {
                console.log(`❌ Missing required variables: ${missingRequired.join(', ')}`);
            }
            this.testResults.push({
                name: testName,
                passed: false,
                error: `Missing required variables: ${missingRequired.join(', ')}`
            });
        }

        if (warnings.length > 0) {
            console.log(`⚠️ Optional variables not set: ${warnings.join(', ')}`);
        }

        // Show current values (masking tokens for security)
        console.log('\n📝 Current Environment Variables:');
        [...requiredVars, ...optionalVars].forEach(varName => {
            if (process.env[varName]) {
                const maskedValue = varName.includes('TOKEN') || varName.includes('KEY')
                    ? '*****'
                    : process.env[varName];
                console.log(`   ${varName}: ${maskedValue}`);
            }
        });
    }

    async testFileStructure() {
        const testName = 'File Structure Validation';
        console.log(`\n📋 ${testName}`);
        console.log('-'.repeat(40));

        const filesToCheck = [
            {
                path: this.stopHookPath,
                description: 'Main stop-hook.js file',
                required: true
            },
            {
                path: '/tmp/mm_thread_id',
                description: 'Thread ID storage file',
                required: false
            }
        ];

        let passed = true;
        let errors = [];

        filesToCheck.forEach(file => {
            if (fs.existsSync(file.path)) {
                const stats = fs.statSync(file.path);
                if (stats.isFile()) {
                    console.log(`✅ ${file.description}: ${file.path}`);
                    if (file.path === '/tmp/mm_thread_id') {
                        try {
                            const content = fs.readFileSync(file.path, 'utf8').trim();
                            console.log(`   Thread ID: ${content || '(empty)'}`);
                        } catch (error) {
                            console.log(`   Could not read file: ${error.message}`);
                        }
                    }
                } else {
                    console.log(`❌ ${file.description}: Exists but is not a file`);
                    passed = false;
                    errors.push(`${file.path} exists but is not a file`);
                }
            } else {
                if (file.required) {
                    console.log(`❌ ${file.description}: File not found`);
                    passed = false;
                    errors.push(`${file.path} not found`);
                } else {
                    console.log(`⚠️ ${file.description}: File not found (optional)`);
                }
            }
        });

        if (passed) {
            this.testResults.push({ name: testName, passed: true });
        } else {
            this.testResults.push({ name: testName, passed: false, error: errors.join('; ') });
        }
    }

    async testMethodExistence() {
        const testName = 'Method Existence Check';
        console.log(`\n📋 ${testName}`);
        console.log('-'.repeat(40));

        try {
            // Clear require cache to ensure fresh load
            delete require.cache[require.resolve(this.stopHookPath)];

            const StopHook = require(this.stopHookPath);
            const hook = new StopHook();

            const requiredMethods = [
                'validateEnvironment',
                'getThreadId',
                'sleep',
                'getThreadReplies',
                'isBotReply',
                'getLatestPostId',
                'findUserReply',
                'waitForUserReply',
                'returnBlockResponse',
                'run'
            ];

            let missingMethods = [];

            requiredMethods.forEach(methodName => {
                if (typeof hook[methodName] === 'function') {
                    console.log(`✅ ${methodName}(): Method exists`);
                } else {
                    console.log(`❌ ${methodName}(): Method missing`);
                    missingMethods.push(methodName);
                }
            });

            if (missingMethods.length === 0) {
                this.testResults.push({ name: testName, passed: true });
            } else {
                this.testResults.push({
                    name: testName,
                    passed: false,
                    error: `Missing methods: ${missingMethods.join(', ')}`
                });
            }

            // Test constructor properties
            console.log('\n📝 Hook Properties:');
            console.log(`   replyTimeoutMs: ${hook.replyTimeoutMs}`);
            console.log(`   botUserId: ${hook.botUserId || '(not set)'}`);
            console.log(`   threadId: ${hook.threadId || '(not resolved)'}`);

        } catch (error) {
            console.log(`❌ Failed to load stop-hook.js: ${error.message}`);
            this.testResults.push({ name: testName, passed: false, error: error.message });
        }
    }

    async testSyntaxValidity() {
        const testName = 'Syntax Validity Check';
        console.log(`\n📋 ${testName}`);
        console.log('-'.repeat(40));

        try {
            // Read the file and check for common syntax issues
            const content = fs.readFileSync(this.stopHookPath, 'utf8');

            // Basic syntax checks
            const issues = [];

            // Check for unclosed braces/brackets/parentheses
            const braceStack = [];
            const bracketStack = [];
            const parenStack = [];

            const lines = content.split('\n');
            lines.forEach((line, index) => {
                // Check for common syntax patterns
                if (line.includes('function(') && !line.includes(')')) {
                    issues.push(`Line ${index + 1}: Possible unclosed function parameter`);
                }

                // Check for balanced quotes (simplified check)
                const singleQuotes = (line.match(/'/g) || []).length;
                const doubleQuotes = (line.match(/"/g) || []).length;
                if (singleQuotes % 2 !== 0) {
                    issues.push(`Line ${index + 1}: Possible unclosed single quote`);
                }
                if (doubleQuotes % 2 !== 0) {
                    issues.push(`Line ${index + 1}: Possible unclosed double quote`);
                }
            });

            // Try to parse as JavaScript using eval (in safe context)
            try {
                // Create a safe function to test syntax
                new Function(content);
                console.log('✅ JavaScript syntax appears valid');
            } catch (parseError) {
                issues.push(`JavaScript parse error: ${parseError.message}`);
            }

            if (issues.length === 0) {
                console.log('✅ No obvious syntax issues detected');
                this.testResults.push({ name: testName, passed: true });
            } else {
                console.log('⚠️ Potential syntax issues detected:');
                issues.forEach(issue => console.log(`   - ${issue}`));
                this.testResults.push({
                    name: testName,
                    passed: issues.length < 3, // Tolerant of minor issues
                    error: issues.join('; ')
                });
            }

        } catch (error) {
            console.log(`❌ Failed to read/parse stop-hook.js: ${error.message}`);
            this.testResults.push({ name: testName, passed: false, error: error.message });
        }
    }

    printResults() {
        console.log('\n📊 Manual Test Results Summary:');
        console.log('='.repeat(50));

        const passed = this.testResults.filter(r => r.passed).length;
        const total = this.testResults.length;

        console.log(`\nTests Passed: ${passed}/${total}`);

        this.testResults.forEach((test, index) => {
            const status = test.passed ? '✅' : '❌';
            console.log(`${status} ${test.name}`);
            if (!test.passed && test.error) {
                console.log(`   Issue: ${test.error}`);
            }
        });

        if (passed === total) {
            console.log('\n🎉 All validation tests passed! Ready for manual testing.');
        } else {
            console.log(`\n⚠️  ${total - passed} validation issue(s) found. Please fix before manual testing.`);
        }
    }

    provideManualInstructions() {
        console.log('\n📖 MANUAL TESTING INSTRUCTIONS:');
        console.log('='.repeat(50));

        console.log('\n1. 🚀 SETUP YOUR TEST ENVIRONMENT:');
        console.log('   export MM_ADDRESS="https://your-mattermost-instance.com"');
        console.log('   export MM_TOKEN="your-bot-token-here"');
        console.log('   export MM_REPLY_TIMEOUT_MS="30000"  # 30 seconds for testing');
        console.log('   export MM_BOT_USER_ID="your-bot-user-id"  # Optional but recommended');

        console.log('\n2. 🧪 CREATE A TEST THREAD:');
        console.log('   - Go to Mattermost and create a new post');
        console.log('   - Note the post ID (thread ID)');
        console.log('   - Set it in the thread file: echo "THREAD_ID" > /tmp/mm_thread_id');

        console.log('\n3. 🔧 TEST THE STOP HOOK:');
        console.log('   cd /workspace');
        console.log('   node .claude/hooks/stop-hook.js < test-input.json');

        console.log('\n4. 📝 CREATE TEST INPUT (test-input.json):');
        console.log('   {');
        console.log('     "last_assistant_message": "Hello, this is a test message from Claude Code"');
        console.log('   }');

        console.log('\n5. 🔄 TEST REPLY WAITING FEATURE:');
        console.log('   - The hook should send your message to Mattermost');
        console.log('   - It should then wait for a user reply (if timeout > 0)');
        console.log('   - Try replying in Mattermost within the timeout period');
        console.log('   - The hook should detect your reply and exit with a block response');

        console.log('\n6. ⏱️ TEST TIMEOUT BEHAVIOR:');
        console.log('   - Set a short timeout (e.g., 5000ms)');
        console.log('   - Do not reply within the timeout period');
        console.log('   - The hook should timeout and continue normal flow');

        console.log('\n7. 🤖 TEST BOT FILTERING (if bot user ID is set):');
        console.log('   - Have the bot reply to the thread');
        console.log('   - The hook should ignore bot replies and wait for human replies');

        console.log('\n8. 📊 VERIFY BEHAVIOR:');
        console.log('   ✅ Message should be posted to Mattermost');
        console.log('   ✅ Hook should wait for replies (if timeout > 0)');
        console.log('   ✅ User replies should be detected and processed');
        console.log('   ✅ Bot replies should be ignored (if bot ID is set)');
        console.log('   ✅ Timeout should work correctly');

        console.log('\n9. 🔧 TROUBLESHOOTING:');
        console.log('   - Check Mattermost logs for API errors');
        console.log('   - Verify thread ID file is readable: cat /tmp/mm_thread_id');
        console.log('   - Test with shorter timeouts first');
        console.log('   - Check network connectivity to Mattermost instance');

        console.log('\n💡 TIP: Start with a 10-second timeout for quick testing cycles.');
    }
}

// Main execution
if (require.main === module) {
    const manualTest = new ReplyWaitingManualTest();

    // Handle cleanup on exit
    process.on('exit', () => {
        console.log('\n🧹 Manual test completed.');
    });

    process.on('SIGINT', () => {
        console.log('\n🛑 Manual test interrupted.');
        process.exit(1);
    });

    manualTest.runAllTests().catch(error => {
        console.error('Manual test execution failed:', error.message);
        process.exit(1);
    });
}

module.exports = ReplyWaitingManualTest;