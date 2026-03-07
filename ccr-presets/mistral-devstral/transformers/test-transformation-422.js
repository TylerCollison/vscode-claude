// Test for Mistral transformer 422 error prevention
import MistralTransformer from './mistral.transformer.js';

async function test422ErrorPrevention() {
  console.log('Testing Mistral transformer 422 error prevention...\n');

  const transformer = new MistralTransformer({
    maxTokens: 4096,
    temperature: 0.7
  }, console);

  // Test 1: Basic valid request
  console.log('=== Test 1: Basic Valid Request ===');
  try {
    const validRequest = {
      model: 'devstral-latest',
      messages: [
        { role: 'user', content: 'Hello, world!' }
      ],
      maxTokens: 100,
      temperature: 0.8
    };

    const mistralRequest = transformer.transformRequestIn(validRequest, {
      name: 'mistral',
      models: ['devstral-latest']
    }, {});

    console.log('✓ Basic transformation successful');
    console.log('Request keys:', Object.keys(mistralRequest));
  } catch (error) {
    console.error('✗ Basic test failed:', error.message);
  }

  // Test 2: Request with unsupported fields
  console.log('\n=== Test 2: Request with Unsupported Fields ===');
  try {
    const unsupportedRequest = {
      model: 'devstral-latest',
      messages: [
        { role: 'user', content: 'Hello!' }
      ],
      // These fields might cause 422 errors
      best_of: 3,
      echo: true,
      logprobs: 5,
      suffix: 'end',
      user: 'test-user'
    };

    const mistralRequest = transformer.transformRequestIn(unsupportedRequest, {
      name: 'mistral',
      models: ['devstral-latest']
    }, {});

    console.log('✓ Transformation filtered unsupported fields');
    console.log('Request keys (should not contain unsupported fields):', Object.keys(mistralRequest));
    console.log('Unsupported fields removed:', Object.keys(unsupportedRequest).filter(k => !mistralRequest.hasOwnProperty(k)));
  } catch (error) {
    console.error('✗ Unsupported fields test failed:', error.message);
  }

  // Test 3: Request with tools
  console.log('\n=== Test 3: Request with Tools ===');
  try {
    const toolRequest = {
      model: 'devstral-latest',
      messages: [
        { role: 'user', content: 'Get weather for Paris' }
      ],
      tools: [
        {
          type: 'function',
          function: {
            name: 'get_weather',
            description: 'Get current weather',
            parameters: {
              type: 'object',
              properties: {
                location: { type: 'string' }
              },
              required: ['location']
            }
          }
        }
      ]
    };

    const mistralRequest = transformer.transformRequestIn(toolRequest, {
      name: 'mistral',
      models: ['devstral-latest']
    }, {});

    console.log('✓ Tool transformation successful');
    console.log('Tools present:', mistralRequest.tools ? mistralRequest.tools.length : 0);
  } catch (error) {
    console.error('✗ Tool test failed:', error.message);
  }

  // Test 4: Request validation errors
  console.log('\n=== Test 4: Request Validation Errors ===');

  const invalidRequests = [
    {
      name: 'Empty messages array',
      request: {
        model: 'devstral-latest',
        messages: []
      },
      expectedError: 'non-empty array'
    },
    {
      name: 'Invalid model name',
      request: {
        model: 'invalid model name with spaces',
        messages: [{ role: 'user', content: 'Hello' }]
      },
      expectedError: 'Invalid model name format'
    },
    {
      name: 'Invalid temperature value',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Hello' }],
        temperature: 3.0 // Out of range
      },
      expectedError: 'must be between'
    }
  ];

  for (const test of invalidRequests) {
    try {
      transformer.transformRequestIn(test.request, {
        name: 'mistral',
        models: ['devstral-latest']
      }, {});
      console.error(`✗ "${test.name}" should have failed but didn't`);
    } catch (error) {
      if (error.message.includes(test.expectedError)) {
        console.log(`✓ "${test.name}" correctly rejected: ${error.message}`);
      } else {
        console.error(`✗ "${test.name}" failed with unexpected error: ${error.message}`);
      }
    }
  }

  // Test 5: Edge cases
  console.log('\n=== Test 5: Edge Cases ===');

  const edgeCases = [
    {
      name: 'Null content',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: null }]
      }
    },
    {
      name: 'Undefined content',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: undefined }]
      }
    },
    {
      name: 'Empty string content',
      request: {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: '' }]
      }
    }
  ];

  for (const test of edgeCases) {
    try {
      const result = transformer.transformRequestIn(test.request, {
        name: 'mistral',
        models: ['devstral-latest']
      }, {});
      console.log(`✓ "${test.name}" handled successfully`);
    } catch (error) {
      console.error(`✗ "${test.name}" failed: ${error.message}`);
    }
  }

  // Test 6: Tool calling message transformation
  console.log('\n=== Test 6: Tool Calling Message Transformation ===');
  try {
    const toolCallMessageRequest = {
      model: 'devstral-latest',
      messages: [
        { role: 'user', content: 'What\'s the weather?' },
        {
          role: 'assistant',
          content: null,
          tool_calls: [
            {
              id: 'call_123',
              function: {
                name: 'get_weather',
                arguments: JSON.stringify({ location: 'Paris' })
              }
            }
          ]
        },
        {
          role: 'tool',
          tool_call_id: 'call_123',
          content: 'Sunny, 22°C'
        }
      ]
    };

    const mistralRequest = transformer.transformRequestIn(toolCallMessageRequest, {
      name: 'mistral',
      models: ['devstral-latest']
    }, {});

    console.log('✓ Tool calling message transformation successful');
    console.log('Message roles:', mistralRequest.messages.map(m => m.role));
    console.log('Has tool calls:', mistralRequest.messages.some(m => m.tool_calls));
    console.log('Has tool call IDs:', mistralRequest.messages.some(m => m.tool_call_id));
  } catch (error) {
    console.error('✗ Tool calling message test failed:', error.message);
  }

  console.log('\n=== All 422 error prevention tests completed ===');
}

test422ErrorPrevention().catch(console.error);