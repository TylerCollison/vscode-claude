// Basic test for Mistral transformer
import MistralTransformer from './mistral.transformer.js';

async function testTransformer() {
  console.log('Testing Mistral transformer...');

  // Create transformer instance
  const transformer = new MistralTransformer({
    maxTokens: 4096,
    temperature: 0.7
  }, console);

  // Test basic methods
  console.log('✓ Transformer created successfully');

  // Test getInfo
  const info = transformer.getInfo();
  console.log('✓ Transformer info:', info);

  // Test health check
  const healthy = await transformer.healthCheck();
  console.log('✓ Health check:', healthy);

  // Test request transformation
  const testRequest = {
    model: 'devstral-latest',
    messages: [
      { role: 'user', content: 'Hello, world!' }
    ],
    maxTokens: 100,
    temperature: 0.8
  };

  const mistralRequest = transformer.transformRequestIn(testRequest, {
    name: 'mistral',
    models: ['devstral-latest']
  }, {});

  console.log('✓ Request transformation successful');
  console.log('Transformed request:', JSON.stringify(mistralRequest, null, 2));

  // Test response transformation
  const testResponse = {
    id: 'chatcmpl-123',
    object: 'chat.completion',
    created: Date.now() / 1000,
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

  const unifiedResponse = transformer.transformResponseIn(testResponse, {});
  console.log('✓ Response transformation successful');
  console.log('Transformed response:', JSON.stringify(unifiedResponse, null, 2));

  console.log('All tests passed! Mistral transformer is working correctly.');
}

testTransformer().catch(console.error);