// CCR Integration Test for Mistral Transformer
import MistralTransformer from './mistral.transformer.js';

async function testCCRIntegration() {
  console.log('Testing Mistral transformer CCR integration...\n');

  const transformer = new MistralTransformer({
    timeout: 30000,
    maxRetries: 3,
    retryDelay: 1000
  }, console);

  // Test 1: CCR provider configuration
  console.log('=== Test 1: CCR Provider Configuration ===');
  const ccrProvider = {
    name: 'mistral',
    models: ['devstral-latest', 'mistral-large-latest'],
    transformer: {
      use: ['mistral']
    }
  };

  try {
    const info = transformer.getInfo();
    console.log('✓ Transformer info retrieved');
    console.log('  Name:', info.name);
    console.log('  Version:', info.version);
    console.log('  Supported models:', info.supportedModels);
    console.log('  Features:', info.features);
  } catch (error) {
    console.error('✗ Failed to get transformer info:', error.message);
  }

  // Test 2: Health check integration
  console.log('\n=== Test 2: Health Check Integration ===');
  try {
    const health = await transformer.healthCheck();
    console.log('✓ Health check successful');
    console.log('  Healthy:', health.healthy);
    console.log('  Status:', health.status);
    console.log('  Metrics:', health.metrics);
  } catch (error) {
    console.error('✗ Health check failed:', error.message);
  }

  // Test 3: Request transformation with CCR format
  console.log('\n=== Test 3: CCR Request Transformation ===');
  const ccrRequest = {
    model: 'devstral-latest',
    messages: [
      { role: 'user', content: 'Hello from CCR!' }
    ],
    maxTokens: 100,
    temperature: 0.7
  };

  try {
    const mistralRequest = transformer.transformRequestIn(ccrRequest, ccrProvider, {});
    console.log('✓ CCR request transformation successful');
    console.log('  Model:', mistralRequest.model);
    console.log('  Messages count:', mistralRequest.messages.length);
    console.log('  Temperature:', mistralRequest.temperature);
    console.log('  Max tokens:', mistralRequest.max_tokens);
  } catch (error) {
    console.error('✗ CCR request transformation failed:', error.message);
  }

  // Test 4: Response transformation with CCR format
  console.log('\n=== Test 4: CCR Response Transformation ===');
  const mistralResponse = {
    id: 'chatcmpl-ccr-test',
    object: 'chat.completion',
    created: Date.now() / 1000,
    model: 'devstral-latest',
    choices: [
      {
        index: 0,
        message: {
          role: 'assistant',
          content: 'Hello! This is a CCR integration test response.'
        },
        finish_reason: 'stop'
      }
    ],
    usage: {
      prompt_tokens: 15,
      completion_tokens: 20,
      total_tokens: 35
    }
  };

  try {
    const ccrResponse = transformer.transformResponseIn(mistralResponse, {});
    console.log('✓ CCR response transformation successful');
    console.log('  Response ID:', ccrResponse.id);
    console.log('  Model:', ccrResponse.model);
    console.log('  Content:', ccrResponse.choices[0].message.content);
    console.log('  Usage:', ccrResponse.usage);
  } catch (error) {
    console.error('✗ CCR response transformation failed:', error.message);
  }

  // Test 5: Error handling in CCR context
  console.log('\n=== Test 5: CCR Error Handling ===');
  const errorResponse = {
    error: {
      message: 'Rate limit exceeded',
      type: 'rate_limit_error',
      code: 'rate_limit'
    }
  };

  try {
    const ccrErrorResponse = transformer.transformResponseIn(errorResponse, {});
    console.log('✓ CCR error transformation successful');
    console.log('  Error message:', ccrErrorResponse.error?.message);
    console.log('  Error code:', ccrErrorResponse.error?.code);
  } catch (error) {
    console.error('✗ CCR error transformation failed:', error.message);
  }

  // Test 6: Advanced features with CCR
  console.log('\n=== Test 6: CCR Advanced Features ===');
  const advancedRequest = {
    model: 'devstral-latest',
    messages: [{ role: 'user', content: 'Test advanced features' }],
    safePrompt: true,
    responseFormat: { type: 'json_object' }
  };

  try {
    const mistralAdvancedRequest = transformer.transformRequestIn(advancedRequest, ccrProvider, {});
    console.log('✓ CCR advanced features transformation successful');
    console.log('  Safe prompt:', mistralAdvancedRequest.safe_prompt);
    console.log('  Response format:', mistralAdvancedRequest.response_format);
  } catch (error) {
    console.error('✗ CCR advanced features transformation failed:', error.message);
  }

  console.log('\n=== CCR Integration Test Completed ===');
}

testCCRIntegration().catch(error => {
  console.error('CCR Integration test failed:', error);
  process.exit(1);
});