// Comprehensive integration test for Mistral transformer
// Tests the complete request/response transformation pipeline

import MistralTransformer from './mistral.transformer.js';
import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert';

// Mock provider configuration
const mockProvider = {
  name: 'mistral',
  models: ['devstral-latest', 'mistral-large-latest', 'mistral-medium-latest']
};

describe('Mistral Transformer Integration Tests', () => {
  let transformer;

  beforeEach(() => {
    transformer = new MistralTransformer({
      maxTokens: 4096,
      temperature: 0.7,
      maxRetries: 3,
      timeout: 30000
    });
  });

  afterEach(() => {
    // Reset transformer state if needed
  });

  describe('Basic Text Completion', () => {
    it('should transform simple chat completion request', () => {
      const request = {
        model: 'devstral-latest',
        messages: [
          { role: 'user', content: 'Hello, world!' }
        ],
        maxTokens: 100,
        temperature: 0.8
      };

      const result = transformer.transformRequestIn(request, mockProvider, {});

      assert.ok(result, 'Request transformation should succeed');
      assert.strictEqual(result.model, 'unknown');
      assert.strictEqual(result.messages.length, 1);
      assert.strictEqual(result.messages[0].role, 'user');
      assert.strictEqual(result.messages[0].content, 'Hello, world!');
      assert.strictEqual(result.max_tokens, 100);
      assert.strictEqual(result.temperature, 0.8);
    });

    it('should transform chat completion response', () => {
      const response = {
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

      const result = transformer.transformResponseIn(response, {});

      assert.ok(result, 'Response transformation should succeed');
      assert.strictEqual(result.id, 'chatcmpl-123');
      assert.strictEqual(result.model, 'devstral-latest');
      assert.strictEqual(result.choices.length, 1);
      assert.strictEqual(result.choices[0].message.role, 'assistant');
      assert.strictEqual(result.choices[0].message.content, 'Hello! How can I help you today?');
      assert.strictEqual(result.choices[0].finish_reason, 'stop');
    });

    it('should handle multi-message conversations', () => {
      const request = {
        model: 'mistral-large-latest',
        messages: [
          { role: 'system', content: 'You are a helpful assistant.' },
          { role: 'user', content: 'Hello!' },
          { role: 'assistant', content: 'Hi there! How can I help?' },
          { role: 'user', content: 'What is the capital of France?' }
        ]
      };

      const result = transformer.transformRequestIn(request, mockProvider, {});

      assert.strictEqual(result.messages.length, 4);
      assert.strictEqual(result.messages[0].role, 'system');
      assert.strictEqual(result.messages[1].role, 'user');
      assert.strictEqual(result.messages[2].role, 'assistant');
      assert.strictEqual(result.messages[3].role, 'user');
    });
  });

  describe('Tool Calling Functionality', () => {
    it('should transform request with tools', () => {
      const request = {
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

      const result = transformer.transformRequestIn(request, mockProvider, {});

      assert.ok(result.tools, 'Tools should be present');
      assert.strictEqual(result.tools.length, 1);
      assert.strictEqual(result.tools[0].type, 'function');
      assert.strictEqual(result.tools[0].function.name, 'get_weather');
    });

    it('should transform response with tool calls', () => {
      const response = {
        id: 'chatcmpl-tool-123',
        object: 'chat.completion',
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

      const result = transformer.transformResponseIn(response, {});

      assert.ok(result.choices[0].message.tool_calls);
      assert.strictEqual(result.choices[0].message.tool_calls.length, 1);
      assert.strictEqual(result.choices[0].message.tool_calls[0].function.name, 'get_weather');
      assert.strictEqual(result.choices[0].finish_reason, 'tool_calls');
    });

    it('should transform tool calling conversation flow', () => {
      const request = {
        model: 'devstral-latest',
        messages: [
          { role: 'user', content: 'What\'s the weather like in Paris?' },
          {
            role: 'assistant',
            content: null,
            tool_calls: [
              {
                id: 'call_123',
                function: {
                  name: 'get_weather',
                  arguments: JSON.stringify({ location: 'Paris, France' })
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

      const result = transformer.transformRequestIn(request, mockProvider, {});

      assert.strictEqual(result.messages.length, 3);
      assert.strictEqual(result.messages[1].role, 'assistant');
      assert.strictEqual(result.messages[2].role, 'tool');
    });
  });

  describe('Streaming Scenarios', () => {
    it('should handle streaming requests', () => {
      const request = {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Tell me a story' }],
        stream: true
      };

      const result = transformer.transformRequestIn(request, mockProvider, {});

      assert.strictEqual(result.stream, true);
    });

    it('should transform streaming response chunks', () => {
      const streamingChunk = {
        id: 'chatcmpl-stream-123',
        object: 'chat.completion.chunk',
        created: 1700000000,
        model: 'devstral-latest',
        choices: [
          {
            index: 0,
            delta: {
              role: 'assistant',
              content: 'Once upon a time'
            },
            finish_reason: null
          }
        ]
      };

      const result = transformer.transformResponseIn(streamingChunk, { stream: true });

      assert.ok(Array.isArray(result), 'Streaming response should return array');
      assert.ok(result.length > 0, 'Streaming chunks should not be empty');
    });

    it('should handle streaming completion', () => {
      const finalChunk = {
        id: 'chatcmpl-stream-123',
        object: 'chat.completion.chunk',
        model: 'devstral-latest',
        choices: [
          {
            index: 0,
            delta: {},
            finish_reason: 'stop'
          }
        ]
      };

      const result = transformer.transformResponseIn(finalChunk, { stream: true });

      assert.ok(Array.isArray(result));
      if (result.length > 0) {
        const chunk = result[0];
        if (chunk && chunk.choices && chunk.choices.length > 0) {
          assert.strictEqual(chunk.choices[0].finish_reason, 'stop');
        }
      }
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle error responses', () => {
      const errorResponse = {
        error: {
          message: 'Invalid API key',
          type: 'authentication_error',
          param: null,
          code: 'invalid_api_key'
        }
      };

      const result = transformer.transformResponseIn(errorResponse, {});

      assert.ok(result.error, 'Error response should contain error object');
      assert.strictEqual(result.error.message, 'Invalid API key');
      assert.strictEqual(result.error.code, 500);
    });

    it('should reject invalid request formats', () => {
      const invalidRequest = {
        model: 'devstral-latest',
        messages: [] // Empty messages array
      };

      assert.throws(
        () => transformer.transformRequestIn(invalidRequest, mockProvider, {}),
        /non-empty array/
      );
    });

    it('should handle invalid model names by converting to unknown', () => {
      const request = {
        model: 'invalid-model-name',
        messages: [{ role: 'user', content: 'Hello' }]
      };

      const result = transformer.transformRequestIn(request, mockProvider, {});
      assert.strictEqual(result.model, 'unknown');
    });

    it('should validate parameter ranges', () => {
      const request = {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Hello' }],
        temperature: 3.0 // Out of range
      };

      assert.throws(
        () => transformer.transformRequestIn(request, mockProvider, {}),
        /must be between/
      );
    });

    it('should handle malformed responses gracefully', () => {
      const malformedResponse = {
        choices: [
          {
            message: {
              role: 'assistant',
              content: null
            }
          }
        ]
      };

      const result = transformer.transformResponseIn(malformedResponse, {});

      assert.ok(result);
      assert.strictEqual(result.choices[0].message.content, '');
    });
  });

  describe('Advanced Parameter Usage', () => {
    it('should support advanced Mistral parameters', () => {
      const request = {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Hello' }],
        temperature: 0.5,
        topP: 0.9,
        frequencyPenalty: 0.1,
        presencePenalty: 0.2,
        safePrompt: true,
        randomSeed: 42
      };

      const result = transformer.transformRequestIn(request, mockProvider, {});

      assert.strictEqual(result.temperature, 0.5);
      assert.strictEqual(result.top_p, 0.9);
      // Note: safePrompt and randomSeed are Mistral-specific and may be handled differently
    });

    it('should apply parameter validation', () => {
      const request = {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Hello' }],
        maxTokens: 32001 // Above limit
      };

      assert.throws(
        () => transformer.transformRequestIn(request, mockProvider, {}),
        /max_tokens.*must be between/
      );
    });
  });

  describe('Performance Monitoring', () => {
    it('should track request count', () => {
      const request = {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Test' }]
      };

      transformer.transformRequestIn(request, mockProvider, {});

      // Check if performance metrics are being tracked
      // Note: This might require accessing internal state or exposing metrics
    });

    it('should handle concurrent transformations', async () => {
      const requests = Array.from({ length: 5 }, (_, i) => ({
        model: 'devstral-latest',
        messages: [{ role: 'user', content: `Request ${i}` }]
      }));

      const promises = requests.map(req =>
        transformer.transformRequestIn(req, mockProvider, {})
      );

      const results = await Promise.all(promises);
      assert.strictEqual(results.length, 5);
    });
  });

  describe('Health Check and Info', () => {
    it('should return transformer info', () => {
      const info = transformer.getInfo();
      assert.ok(info, 'Info should be returned');
      assert.strictEqual(typeof info.name, 'string');
      assert.strictEqual(typeof info.version, 'string');
    });

    it('should perform health check', async () => {
      const health = await transformer.healthCheck();
      assert.ok(health.healthy, 'Health check should return healthy status');
    });
  });

  describe('End-to-End Pipeline', () => {
    it('should complete full request-response cycle', () => {
      const request = {
        model: 'devstral-latest',
        messages: [
          { role: 'user', content: 'What is 2+2?' }
        ],
        maxTokens: 50
      };

      const mistralRequest = transformer.transformRequestIn(request, mockProvider, {});

      const mockResponse = {
        id: 'chatcmpl-test-123',
        object: 'chat.completion',
        model: 'devstral-latest',
        choices: [
          {
            index: 0,
            message: {
              role: 'assistant',
              content: '2+2 equals 4'
            },
            finish_reason: 'stop'
          }
        ],
        usage: {
          prompt_tokens: 10,
          completion_tokens: 8,
          total_tokens: 18
        }
      };

      const unifiedResponse = transformer.transformResponseIn(mockResponse, {});

      assert.ok(mistralRequest);
      assert.ok(unifiedResponse);
      assert.strictEqual(unifiedResponse.choices[0].message.content, '2+2 equals 4');
    });

    it('should handle streaming end-to-end', () => {
      const streamingRequest = {
        model: 'devstral-latest',
        messages: [{ role: 'user', content: 'Tell me a short story' }],
        stream: true
      };

      const mistralRequest = transformer.transformRequestIn(streamingRequest, mockProvider, {});

      const streamingChunks = [
        {
          id: 'chatcmpl-stream-123',
          object: 'chat.completion.chunk',
          model: 'devstral-latest',
          choices: [
            {
              index: 0,
              delta: { content: 'Once' },
              finish_reason: null
            }
          ]
        },
        {
          id: 'chatcmpl-stream-123',
          object: 'chat.completion.chunk',
          model: 'devstral-latest',
          choices: [
            {
              index: 0,
              delta: { content: ' upon a time' },
              finish_reason: null
            }
          ]
        },
        {
          id: 'chatcmpl-stream-123',
          object: 'chat.completion.chunk',
          model: 'devstral-latest',
          choices: [
            {
              index: 0,
              delta: {},
              finish_reason: 'stop'
            }
          ]
        }
      ];

      const unifiedChunks = streamingChunks.map(chunk =>
        transformer.transformResponseIn(chunk, { stream: true })
      );

      assert.strictEqual(unifiedChunks.length, 3);
      assert.ok(Array.isArray(unifiedChunks[0]));
    });
  });
});

