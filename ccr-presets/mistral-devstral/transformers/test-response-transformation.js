// Comprehensive test for Mistral response transformation
import MistralTransformer from './mistral.transformer.js';

async function testResponseTransformation() {
  console.log('Testing enhanced Mistral response transformation...\n');

  const transformer = new MistralTransformer({}, console);

  // Test 1: Standard successful response
  console.log('=== Test 1: Standard Successful Response ===');
  const standardResponse = {
    id: 'chatcmpl-123',
    object: 'chat.completion',
    created: 1700000000,
    model: 'devstral-latest',
    choices: [
      {
        index: 0,
        message: {
          role: 'assistant',
          content: 'Hello! How can I help you today?'
        },
        finish_reason: 'stop'
      }
    ],
    usage: {
      prompt_tokens: 10,
      completion_tokens: 15,
      total_tokens: 25
    }
  };

  try {
    const unifiedResponse = transformer.transformResponseIn(standardResponse, {});
    console.log('✓ Standard response transformation successful');
    console.log('Response ID:', unifiedResponse.id);
    console.log('Model:', unifiedResponse.model);
    console.log('Choices count:', unifiedResponse.choices.length);
  } catch (error) {
    console.error('✗ Standard response test failed:', error.message);
  }

  // Test 2: Response with tool calls
  console.log('\n=== Test 2: Response with Tool Calls ===');
  const toolResponse = {
    id: 'chatcmpl-tool-123',
    object: 'chat.completion',
    created: 1700000000,
    model: 'mistral-large-latest',
    choices: [
      {
        index: 0,
        message: {
          role: 'assistant',
          content: '',
          tool_calls: [
            {
              id: 'call_123',
              type: 'function',
              function: {
                name: 'get_weather',
                arguments: '{"location":"Paris, France"}'
              }
            }
          ]
        },
        finish_reason: 'tool_calls'
      }
    ],
    usage: {
      prompt_tokens: 25,
      completion_tokens: 30,
      total_tokens: 55
    }
  };

  try {
    const unifiedResponse = transformer.transformResponseIn(toolResponse, {});
    console.log('✓ Tool response transformation successful');
    console.log('Has tool calls:', unifiedResponse.choices[0].message.tool_calls?.length > 0);
    console.log('Finish reason:', unifiedResponse.choices[0].finish_reason);
  } catch (error) {
    console.error('✗ Tool response test failed:', error.message);
  }

  // Test 3: Error response
  console.log('\n=== Test 3: Error Response ===');
  const errorResponse = {
    error: {
      message: 'Invalid API key',
      type: 'authentication_error',
      param: null,
      code: 'invalid_api_key'
    }
  };

  try {
    const unifiedResponse = transformer.transformResponseIn(errorResponse, {});
    console.log('✓ Error response transformation successful');
    console.log('Error code:', unifiedResponse.error?.code);
    console.log('Error message:', unifiedResponse.error?.message);
    console.log('Object type:', unifiedResponse.object);
  } catch (error) {
    console.error('✗ Error response test failed:', error.message);
  }

  // Test 4: Empty choices array
  console.log('\n=== Test 4: Empty Choices Array ===');
  const emptyChoicesResponse = {
    id: 'chatcmpl-empty',
    object: 'chat.completion',
    model: 'devstral-latest',
    choices: []
  };

  try {
    const unifiedResponse = transformer.transformResponseIn(emptyChoicesResponse, {});
    console.log('✓ Empty choices handled successfully');
    console.log('Choices count:', unifiedResponse.choices.length);
  } catch (error) {
    console.error('✗ Empty choices test failed:', error.message);
  }

  // Test 5: Missing required fields
  console.log('\n=== Test 5: Response with Missing Fields ===');
  const minimalResponse = {
    choices: [
      {
        message: {
          role: 'assistant',
          content: 'Minimal response'
        }
      }
    ]
  };

  try {
    const unifiedResponse = transformer.transformResponseIn(minimalResponse, {});
    console.log('✓ Minimal response transformation successful');
    console.log('Generated ID:', unifiedResponse.id);
    console.log('Default model:', unifiedResponse.model);
    console.log('Default usage:', unifiedResponse.usage);
  } catch (error) {
    console.error('✗ Minimal response test failed:', error.message);
  }

  // Test 6: Invalid response formats
  console.log('\n=== Test 6: Invalid Response Formats ===');
  const invalidResponses = [
    {
      name: 'Null response',
      response: null,
      expectedError: 'must be an object'
    },
    {
      name: 'String response',
      response: 'not an object',
      expectedError: 'must be an object'
    },
    {
      name: 'Missing choices',
      response: { id: 'test', model: 'devstral-latest' },
      expectedError: 'missing or invalid choices array'
    },
    {
      name: 'Invalid choice structure',
      response: { choices: ['not an object'] },
      expectedError: 'must be an object'
    }
  ];

  for (const test of invalidResponses) {
    try {
      transformer.transformResponseIn(test.response, {});
      console.error(`✗ "${test.name}" should have failed but didn't`);
    } catch (error) {
      if (error.message.includes(test.expectedError)) {
        console.log(`✓ "${test.name}" correctly rejected: ${error.message}`);
      } else {
        console.error(`✗ "${test.name}" failed with unexpected error: ${error.message}`);
      }
    }
  }

  // Test 7: Edge cases
  console.log('\n=== Test 7: Edge Cases ===');
  const edgeCases = [
    {
      name: 'Null content in message',
      response: {
        choices: [
          {
            message: {
              role: 'assistant',
              content: null
            }
          }
        ]
      }
    },
    {
      name: 'Undefined content with tool calls',
      response: {
        choices: [
          {
            message: {
              role: 'assistant',
              content: undefined,
              tool_calls: [
                {
                  id: 'call_123',
                  type: 'function',
                  function: {
                    name: 'test_function',
                    arguments: '{}'
                  }
                }
              ]
            }
          }
        ]
      }
    },
    {
      name: 'Invalid usage values',
      response: {
        choices: [
          {
            message: {
              role: 'assistant',
              content: 'Test'
            }
          }
        ],
        usage: {
          prompt_tokens: 'invalid',
          completion_tokens: -5,
          total_tokens: null
        }
      }
    }
  ];

  for (const test of edgeCases) {
    try {
      const unifiedResponse = transformer.transformResponseIn(test.response, {});
      console.log(`✓ "${test.name}" handled successfully`);
      console.log('  Content:', unifiedResponse.choices[0].message.content);
      if (test.response.usage) {
        console.log('  Usage:', unifiedResponse.usage);
      }
    } catch (error) {
      console.error(`✗ "${test.name}" failed: ${error.message}`);
    }
  }

  // Test 8: HTTP error responses
  console.log('\n=== Test 8: HTTP Error Responses ===');
  const httpErrorResponses = [
    {
      name: '400 Bad Request',
      response: {
        status_code: 400,
        error: 'Invalid request parameters'
      }
    },
    {
      name: '401 Unauthorized',
      response: {
        status: 401,
        message: 'Authentication required'
      }
    },
    {
      name: '429 Rate Limit',
      response: {
        status_code: 429,
        error: {
          message: 'Rate limit exceeded',
          type: 'rate_limit_error'
        }
      }
    },
    {
      name: '500 Internal Error',
      response: {
        status: 500,
        error: 'Internal server error'
      }
    }
  ];

  for (const test of httpErrorResponses) {
    try {
      const unifiedResponse = transformer.transformResponseIn(test.response, {});
      console.log(`✓ "${test.name}" transformed successfully`);
      console.log('  Error object:', unifiedResponse.error);
      console.log('  Response type:', unifiedResponse.object);
    } catch (error) {
      console.error(`✗ "${test.name}" failed: ${error.message}`);
    }
  }

  console.log('\n=== All response transformation tests completed ===');
}

// Run the test
testResponseTransformation().catch(error => {
  console.error('Test suite failed:', error);
  process.exit(1);
});