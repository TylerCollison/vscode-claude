// Advanced test for Mistral transformer features
import MistralTransformer from './mistral.transformer.js';

async function testAdvancedFeatures() {
  console.log('Testing advanced Mistral transformer features...');

  const transformer = new MistralTransformer({}, console);

  // Test tool calling transformation
  console.log('\n=== Testing Tool Calling ===');
  const toolRequest = {
    model: 'devstral-latest',
    messages: [
      { role: 'user', content: 'What\'s the weather like in Paris?' }
    ],
    tools: [
      {
        type: 'function',
        function: {
          name: 'get_weather',
          description: 'Get the current weather in a location',
          parameters: {
            type: 'object',
            properties: {
              location: {
                type: 'string',
                description: 'The city and country'
              }
            },
            required: ['location']
          }
        }
      }
    ]
  };

  const mistralToolRequest = transformer.transformRequestIn(toolRequest, {
    name: 'mistral',
    models: ['devstral-latest']
  }, {});

  console.log('Tool request transformed successfully');
  console.log('Tools:', JSON.stringify(mistralToolRequest.tools, null, 2));

  // Test tool response transformation
  const toolResponse = {
    id: 'chatcmpl-tool-123',
    object: 'chat.completion',
    created: Date.now() / 1000,
    model: 'devstral-latest',
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

  const unifiedToolResponse = transformer.transformResponseIn(toolResponse, {});
  console.log('Tool response transformed successfully');

  // Test tool result message transformation
  const toolResultRequest = {
    model: 'devstral-latest',
    messages: [
      { role: 'user', content: 'What\'s the weather like in Paris?' },
      {
        role: 'assistant',
        content: '',
        tool_calls: [
          {
            id: 'call_123',
            function: {
              name: 'get_weather',
              arguments: { location: 'Paris, France' }
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

  const mistralToolResultRequest = transformer.transformRequestIn(toolResultRequest, {
    name: 'mistral',
    models: ['devstral-latest']
  }, {});

  console.log('Tool result message transformation:');
  console.log('Messages:', JSON.stringify(mistralToolResultRequest.messages, null, 2));

  // Test streaming support
  console.log('\n=== Testing Streaming Support ===');
  const streamingRequest = {
    model: 'devstral-latest',
    messages: [{ role: 'user', content: 'Tell me a story' }],
    stream: true
  };

  const mistralStreamingRequest = transformer.transformRequestIn(streamingRequest, {
    name: 'mistral',
    models: ['devstral-latest']
  }, {});

  console.log('Streaming request transformed successfully');
  console.log('Stream flag:', mistralStreamingRequest.stream);

  // Test message role mapping
  console.log('\n=== Testing Role Mapping ===');
  const multiRoleRequest = {
    model: 'mistral-large-latest',
    messages: [
      { role: 'system', content: 'You are a helpful assistant.' },
      { role: 'user', content: 'Hello!' },
      { role: 'assistant', content: 'Hi there!' },
      { role: 'tool', content: 'Tool result', tool_call_id: 'call_456' }
    ]
  };

  const mistralRoleRequest = transformer.transformRequestIn(multiRoleRequest, {
    name: 'mistral',
    models: ['mistral-large-latest']
  }, {});

  console.log('Role mapping successful');
  console.log('Roles:', mistralRoleRequest.messages.map(m => m.role));

  console.log('\nAll advanced tests passed!');
}

testAdvancedFeatures().catch(console.error);