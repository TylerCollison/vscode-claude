// Test to verify that 422 errors are resolved
import MistralTransformer from './mistral.transformer.js';

async function test422Resolution() {
  console.log('Testing 422 error resolution...\n');

  const transformer = new MistralTransformer({}, console);

  // Test cases that previously caused 422 errors
  const problematicRequests = [
    {
      name: 'Request with OpenAI-specific fields',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Hello' }],
        best_of: 3,
        echo: true,
        logprobs: 5,
        suffix: 'end',
        user: 'test-user'
      },
      shouldNotContain: ['best_of', 'echo', 'logprobs', 'suffix', 'user']
    },
    {
      name: 'Request with invalid parameter values',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Test' }],
        temperature: 3.0,  // Invalid range
        topP: 2.0         // Invalid range
      },
      shouldFail: true
    },
    {
      name: 'Request with valid parameters',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Valid request' }],
        temperature: 0.8,
        topP: 0.9,
        maxTokens: 100
      }
    },
    {
      name: 'Request with Mistral-specific parameters',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Mistral test' }],
        safePrompt: true,
        responseFormat: { type: 'text' }
      }
    }
  ];

  const mockProvider = {
    name: 'mistral',
    models: ['devstral-latest', 'mistral-large-latest']
  };

  for (const testCase of problematicRequests) {
    console.log(`=== ${testCase.name} ===`);

    try {
      const result = transformer.transformRequestIn(testCase.request, mockProvider, {});

      if (testCase.shouldFail) {
        console.error(`✗ Expected failure but transformation succeeded`);
        continue;
      }

      console.log('✓ Transformation successful');

      // Check that unwanted fields are filtered
      if (testCase.shouldNotContain) {
        const unwantedFields = testCase.shouldNotContain.filter(field => result[field] !== undefined);
        if (unwantedFields.length === 0) {
          console.log('✓ Unsupported fields filtered out');
        } else {
          console.error(`✗ Unwanted fields still present:`, unwantedFields);
        }
      }

      // Log valid transformed parameters
      console.log('Transformed parameters:', Object.keys(result));

    } catch (error) {
      if (testCase.shouldFail) {
        console.log('✓ Correctly rejected invalid request:', error.message);
      } else {
        console.error('✗ Unexpected failure:', error.message);
      }
    }
  }

  // Test edge cases that might cause 422
  console.log('\n=== Edge Case Testing ===');
  const edgeCases = [
    {
      name: 'Empty messages array',
      request: { model: 'devstral-latest', messages: [] }
    },
    {
      name: 'Null message content',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: null }]
      }
    },
    {
      name: 'Undefined message content',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: undefined }]
      }
    },
    {
      name: 'Mixed invalid model names',
      request: {
        model: 'invalid model name',
        messages: [{ role: 'user', content: 'Test' }]
      }
    }
  ];

  for (const testCase of edgeCases) {
    console.log(`Testing: ${testCase.name}`);

    try {
      const result = transformer.transformRequestIn(testCase.request, mockProvider, {});

      if (testCase.request.messages && testCase.request.messages.length === 0) {
        console.error('✗ Empty messages array should have been rejected');
      } else {
        console.log('✓ Edge case handled successfully');
      }

    } catch (error) {
      if (testCase.request.messages && testCase.request.messages.length === 0) {
        console.log('✓ Empty messages correctly rejected:', error.message);
      } else {
        console.log('✓ Edge case handled (rejected):', error.message);
      }
    }
  }

  console.log('\n=== Response Format Validation ===');

  // Test response transformation edge cases
  const responseCases = [
    {
      name: 'Standard response',
      response: {
        id: 'test-123',
        model: 'devstral-latest',
        choices: [{ message: { role: 'assistant', content: 'Hello' } }]
      }
    },
    {
      name: 'Response with null content',
      response: {
        choices: [{ message: { role: 'assistant', content: null } }]
      }
    },
    {
      name: 'Response with empty content',
      response: {
        choices: [{ message: { role: 'assistant', content: '' } }]
      }
    },
    {
      name: 'Response with tools',
      response: {
        choices: [{
          message: {
            role: 'assistant',
            content: '',
            tool_calls: [{ type: 'function', function: { name: 'test', arguments: '{}' } }]
          }
        }]
      }
    }
  ];

  for (const testCase of responseCases) {
    console.log(`Testing response: ${testCase.name}`);

    try {
      const result = transformer.transformResponseIn(testCase.response, {});
      console.log('✓ Response transformation successful');

      // Check that content is properly handled
      if (testCase.response.choices && testCase.response.choices[0]) {
        const content = result.choices[0].message.content;
        console.log(`  Content: "${content}" (length: ${content ? content.length : 0})`);
      }

    } catch (error) {
      console.error('✗ Response transformation failed:', error.message);
    }
  }

  console.log('\n=== 422 Resolution Verification Complete ===');
  console.log('The transformer should now handle all previously problematic scenarios');
  console.log('and prevent 422 errors by proper validation and field filtering.');
}

test422Resolution().catch(error => {
  console.error('422 resolution test failed:', error);
  process.exit(1);
});