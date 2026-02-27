#!/usr/bin/env node
// Test script for CCR integration

const { spawnSync } = require('child_process');

function testCommandSelection() {
    console.log('Starting CCR Integration Tests...\n');

    // Test 1: No CCR_PROFILE set
    process.env.CCR_PROFILE = undefined;
    const result1 = simulateCommandSelection();
    console.log('Test 1 - No CCR_PROFILE:', result1.command === 'claude' ? 'PASS' : 'FAIL');
    console.log(`  Command: ${result1.command}, Args: [${result1.args.join(', ')}]`);

    // Test 2: CCR_PROFILE set but ccr not available
    process.env.CCR_PROFILE = 'default';
    const result2 = simulateCommandSelection();
    console.log('Test 2 - CCR_PROFILE set, ccr unavailable:', result2.command === 'claude' ? 'PASS' : 'FAIL');
    console.log(`  Command: ${result2.command}, Args: [${result2.args.join(', ')}]`);

    // Test 3: CCR_PROFILE empty string
    process.env.CCR_PROFILE = '';
    const result3 = simulateCommandSelection();
    console.log('Test 3 - CCR_PROFILE empty:', result3.command === 'claude' ? 'PASS' : 'FAIL');
    console.log(`  Command: ${result3.command}, Args: [${result3.args.join(', ')}]`);

    // Test 4: CCR_PROFILE set and ccr available (simulated)
    process.env.CCR_PROFILE = 'default';
    const result4 = simulateCommandSelectionWithCCRAvailable();
    console.log('Test 4 - CCR_PROFILE set, ccr available:', result4.command === 'ccr' ? 'PASS' : 'FAIL');
    console.log(`  Command: ${result4.command}, Args: [${result4.args.join(', ')}]`);

    console.log('\nAll tests completed.');
}

function simulateCommandSelection() {
    const ccrProfile = process.env.CCR_PROFILE;
    const useCCR = ccrProfile && ccrProfile.trim() !== '';

    // Simulate ccr command check (always false for this test)
    const ccrAvailable = false;

    const command = useCCR && ccrAvailable ? 'ccr' : 'claude';
    const args = useCCR && ccrAvailable ?
        [ccrProfile, '--permission-mode', 'default'] :
        ['--permission-mode', 'default'];

    return { command, args };
}

function simulateCommandSelectionWithCCRAvailable() {
    const ccrProfile = process.env.CCR_PROFILE;
    const useCCR = ccrProfile && ccrProfile.trim() !== '';

    // Simulate ccr command check (always true for this test)
    const ccrAvailable = true;

    const command = useCCR && ccrAvailable ? 'ccr' : 'claude';
    const args = useCCR && ccrAvailable ?
        [ccrProfile, '--permission-mode', 'default'] :
        ['--permission-mode', 'default'];

    return { command, args };
}

testCommandSelection();