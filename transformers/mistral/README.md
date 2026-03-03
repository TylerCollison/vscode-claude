# Mistral Transformer

Advanced Mistral AI API transformer for Claude Code Router with comprehensive advanced features support.

> **Version:** 1.2.0
> **Package:** `mistral-transformer`
> **Compatibility:** Node.js >= 16.0.0

## Overview

The Mistral Transformer provides seamless integration between Claude Code Router and Mistral AI APIs, offering comprehensive support for advanced features including streaming, tool calling, advanced error handling, performance monitoring, and structured logging.

## Features

### Core Features
- Full Mistral API compatibility
- Tool calling support with advanced validation
- Comprehensive streaming response handling
- Advanced parameter support including Mistral-specific features
- Support for all Mistral models (`devstral-latest`, `mistral-large-latest`, `mistral-medium-latest`)

### Advanced Features
- Enhanced error handling with recovery mechanisms
- Performance monitoring and metrics tracking
- Structured logging system with metadata sanitization
- Circuit breaker and retry policies for fault tolerance
- Safe prompt filtering support
- Random seed for deterministic results
- Configuration validation and health checks
- State export and configuration updates

### Supported Parameters

The transformer supports all Mistral advanced parameters:
- `temperature`, `top_p`, `max_tokens` - Core sampling parameters
- `safe_prompt`, `random_seed`, `response_format` - Advanced parameters
- `frequency_penalty`, `presence_penalty` - Penalty controls
- `tool_choice` - Tool selection options

## Installation

### Using npm
```bash
npm install mistral-transformer
```

### Using yarn
```bash
yarn add mistral-transformer
```

### Manual Installation
```javascript
import MistralTransformer from './mistral.transformer.js';
```

## Quick Start

```javascript
import MistralTransformer from 'mistral-transformer';

// Basic initialization
const transformer = new MistralTransformer();

// Transform request to Mistral format
const mistralRequest = transformer.transformRequestIn({
  model: 'devstral-latest',
  messages: [{ role: 'user', content: 'Hello, world!' }],
  maxTokens: 100
}, { name: 'mistral' }, {});

// Transform response back to unified format
const unifiedResponse = transformer.transformResponseIn(
  mistralApiResponse,
  {}
);
```

## Configuration

### Initialization Options

The transformer accepts advanced configuration options:

```javascript
const transformer = new MistralTransformer({
  // Core parameters
  maxTokens: 4096,
  temperature: 0.7,
  topP: 1.0,

  // Advanced Mistral parameters
  safePrompt: false,           // Enable safe prompt filtering
  randomSeed: null,            // Random seed for deterministic results
  responseFormat: 'text',      // Response format control ('text' or 'json_object')
  frequencyPenalty: 0.0,      // Frequency penalty
  presencePenalty: 0.0,        // Presence penalty

  // Advanced system configuration
  timeout: 30000,              // Request timeout in milliseconds
  maxRetries: 3,               // Maximum retry attempts
  retryDelay: 1000,            // Retry delay in milliseconds
  circuitBreakerThreshold: 5,  // Circuit breaker activation threshold
}, console); // Custom logger (optional)
```

### Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `maxTokens` | number | `4096` | Maximum tokens for completion |
| `temperature` | number | `0.7` | Sampling temperature (0-2) |
| `topP` | number | `1.0` | Nucleus sampling (0-1) |
| `safePrompt` | boolean | `false` | Enable safe prompt filtering |
| `randomSeed` | number | `null` | Random seed for deterministic results |
| `responseFormat` | string | `'text'` | Response format (`text` or `json_object`) |
| `frequencyPenalty` | number | `0.0` | Frequency penalty (-2.0 to 2.0) |
| `presencePenalty` | number | `0.0` | Presence penalty (-2.0 to 2.0) |
| `timeout` | number | `30000` | Request timeout in milliseconds |
| `maxRetries` | number | `3` | Maximum retry attempts |
| `retryDelay` | number | `1000` | Retry delay in milliseconds |
| `circuitBreakerThreshold` | number | `5` | Circuit breaker activation threshold |

## Streaming Support

The Mistral transformer provides comprehensive Server-Sent Events (SSE) support for real-time streaming responses.

### Streaming Example

```javascript
// Enable streaming in request
const streamingRequest = {
  model: 'devstral-latest',
  messages: [{ role: 'user', content: 'Tell me a story about AI' }],
  stream: true
};

const mistralRequest = transformer.transformRequestIn(streamingRequest, { name: 'mistral' }, {});

// Handle streaming responses
const streamingResponse = {
  choices: [{
    delta: { content: 'Once upon a time' },
    finish_reason: null
  }]
};

const streamingChunks = transformer.transformResponseIn(streamingResponse, { stream: true });
// Returns array of streaming chunks

// Handle raw SSE data
const rawSSEData = `data: {"id":"chatcmpl-123","delta":{"content":"Hello"}}\ndata: [DONE]`;
const parsedChunks = transformer.transformResponseIn(rawSSEData, { stream: true });
```

### Streaming Features

- **Raw SSE parsing**: Automatically detects and parses raw Server-Sent Events streams
- **Incremental content**: Handles incremental content chunks with proper delta tracking
- **Tool calls in streaming**: Supports tool calls within streaming responses
- **[DONE] event handling**: Properly detects and handles streaming termination
- **Error handling**: Graceful error handling within streaming contexts


## Advanced Usage

### Configuration Validation and Health Monitoring

```javascript
import MistralTransformer from 'mistral-transformer';

// Initialize with advanced configuration
const transformer = new MistralTransformer({
  safePrompt: true,           // Enable safe prompt filtering
  randomSeed: 12345,          // Set random seed for deterministic results
  responseFormat: 'text',      // Response format control
  timeout: 30000,             // Request timeout in ms
  maxRetries: 3,              // Maximum retry attempts
  retryDelay: 1000,           // Retry delay in ms
  circuitBreakerThreshold: 5  // Circuit breaker threshold
}, console);

// Get transformer information
const info = transformer.getInfo();
console.log('Transformer Info:', info);

// Get performance metrics
const metrics = transformer.getPerformanceMetrics();
console.log('Performance Metrics:', metrics);

// Validate transformer configuration
const validation = await transformer.validate();
console.log('Validation Results:', validation);

// Health check
const health = await transformer.healthCheck();
console.log('Health Status:', health);

// Export complete transformer state
const state = transformer.exportState();
console.log('Transformer State:', state);
```

### Advanced Parameters and Configuration Updates

```javascript
// Request with advanced Mistral parameters
const advancedRequest = {
  model: 'devstral-latest',
  messages: [{ role: 'user', content: 'Generate JSON for a user profile' }],
  safe_prompt: true,           // Safe prompt filtering
  random_seed: 12345,          // Random seed
  response_format: 'json_object', // Response format
  tool_choice: 'auto',          // Tool selection
  frequency_penalty: 0.5,      // Frequency penalty
  presence_penalty: 0.3        // Presence penalty
};

const mistralRequest = transformer.transformRequestIn(advancedRequest, { name: 'mistral' }, {});

// Update configuration dynamically
transformer.updateConfiguration({
  maxRetries: 5,
  timeout: 60000,
  safePrompt: false
});

// Reset metrics if needed
transformer.resetMetrics();
```

### Error Handling and Recovery

```javascript
try {
  const response = transformer.transformResponseIn(mistralResponse, {});

} catch (error) {
  // Categorized error handling
  switch (error.type) {
    case 'VALIDATION_ERROR':
      console.error('Validation failed:', error.message);
      break;
    case 'NETWORK_ERROR':
      if (error.recoverable && error.retryCount < error.maxRetries) {
        console.warn(`Network error, retrying (${error.retryCount}/${error.maxRetries})`);
        // Implement retry logic
      }
      break;
    case 'RATE_LIMIT_ERROR':
      console.warn(`Rate limit hit, retrying after ${error.retryAfter}ms`);
      break;
    default:
      console.error('Internal error:', error.message);
  }
}

// Retry mechanism with exponential backoff
async function executeWithRetry(transformer, request, maxAttempts = 3) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await transformer.transformRequestIn(request, {});
    } catch (error) {
      if (!error.recoverable || attempt === maxAttempts) {
        throw error;
      }

      const delay = error.retryAfter || Math.pow(2, attempt) * 1000;
      console.warn(`Attempt ${attempt} failed, retrying in ${delay}ms`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

### Performance Monitoring

```javascript
// Monitor transformer performance
setInterval(() => {
  const metrics = transformer.getPerformanceMetrics();

  if (metrics.failureRate > 10) {
    console.warn('High failure rate detected:', metrics.failureRate + '%');
  }

  console.log(`Success Rate: ${metrics.successRate.toFixed(2)}%`);
  console.log(`Average Response Time: ${metrics.averageResponseTime.toFixed(2)}ms`);
}, 60000); // Every minute

// Health check
const health = await transformer.healthCheck();
console.log('Transformer Health:', health);

// Reset metrics
if (health.metrics.totalRequests > 1000) {
  transformer.resetMetrics();
  console.log('Performance metrics reset');
}
```

### Example Usage

```javascript
import MistralTransformer from './mistral.transformer.js';

const transformer = new MistralTransformer();

// Handle raw SSE stream
const rawSSE = `data: {\"id\":\"chatcmpl-123\",\"delta\":{\"content\":\"Hello\"}}
data: [DONE]`;
const chunks = transformer.transformResponseIn(rawSSE, { stream: true });

// Handle structured streaming response
const streamingResponse = {
  choices: [{
    delta: { content: "Streaming response" },
    finish_reason: "stop"
  }]
};
const chunks = transformer.transformResponseIn(streamingResponse, { stream: true });
```

## Advanced Configuration Options

### Available Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `safePrompt` | boolean | `false` | Enable safe prompt filtering |
| `randomSeed` | number | `null` | Random seed for deterministic results |
| `responseFormat` | string | `'text'` | Response format (`text`, `json_object`) |
| `timeout` | number | `30000` | Request timeout in milliseconds |
| `maxRetries` | number | `3` | Maximum retry attempts |
| `retryDelay` | number | `1000` | Retry delay in milliseconds |
| `circuitBreakerThreshold` | number | `5` | Circuit breaker activation threshold |

### Advanced Parameters Support

The transformer supports all Mistral advanced parameters:
- `safe_prompt` - Enable/disable safe prompt filtering
- `random_seed` - Set random seed for reproducibility
- `response_format` - Control response format (`text` or `json_object`)
- `tool_choice` - Tool selection (`auto`, `none`, or specific function)
- `frequency_penalty` - Frequency penalty for token repetition
- `presence_penalty` - Presence penalty for topic repetition

### Streaming Response Format

Each streaming chunk includes:
- `object`: `"stream.chunk"`
- `id`: Unique chunk identifier
- `index`: Choice index for multi-choice responses
- `delta`: Content delta with `content`, `role`, or `tool_calls`
- `finish_reason`: Finish reason when streaming completes
- `provider`: Provider metadata including streaming type

### Error Handling in Streaming

Streaming errors are properly transformed:
- Errors within SSE streams are detected and transformed
- Streaming context is preserved during error handling
- Proper error objects are returned within the streaming format

## Advanced Error Handling

### Error Categorization

The transformer categorizes errors into four types:

1. **Validation Errors** (Non-recoverable)
   - Invalid parameter values
   - Missing required fields
   - Type validation failures

2. **Network Errors** (Recoverable)
   - Connection timeouts
   - Network connectivity issues
   - DNS resolution failures

3. **Rate Limit Errors** (Recoverable with backoff)
   - API rate limiting
   - Quota exceeded
   - Too many requests

4. **Internal Errors** (Non-recoverable)
   - Internal transformer failures
   - Unexpected data formats
   - System-level issues

### Retry Mechanism

```javascript
async function executeWithRetry(transformer, request, maxAttempts = 3) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await transformer.transformRequestIn(request, {});
    } catch (error) {
      if (!error.recoverable || attempt === maxAttempts) {
        throw error;
      }

      const delay = error.retryAfter || Math.pow(2, attempt) * 1000;
      console.warn(`Attempt ${attempt} failed, retrying in ${delay}ms`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

### Circuit Breaker Pattern

The transformer includes a built-in circuit breaker that automatically stops requests after consecutive failures:

```javascript
const transformer = new MistralTransformer({
  circuitBreakerThreshold: 5  // Activate after 5 consecutive failures
});

// Check circuit breaker status
const circuitBreaker = transformer._createCircuitBreaker();
console.log('Circuit Breaker Status:', circuitBreaker.getStatus());
```

## Performance Monitoring

### Key Metrics

| Metric | Description | Calculation |
|--------|-------------|-------------|
| `totalRequests` | Total requests processed | Count of all requests |
| `successfulRequests` | Successful transformations | Count of successful requests |
| `failedRequests` | Failed transformations | Count of failed requests |
| `averageResponseTime` | Average processing time | Moving average of processing times |
| `successRate` | Success percentage | `(successfulRequests / totalRequests) * 100` |
| `failureRate` | Failure percentage | `(failedRequests / totalRequests) * 100` |

### Health Monitoring

```javascript
// Check transformer health
const health = await transformer.healthCheck();
console.log('Health Status:', health);

// Export complete transformer state
const state = transformer.exportState();
console.log('Transformer State:', state);
```

## Structured Logging

### Log Levels

- **DEBUG**: Detailed operational information
- **INFO**: General operational messages
- **WARN**: Warning messages for potential issues
- **ERROR**: Error messages for failures

### Log Format

All logs include structured metadata:
```json
{
  "transformer": "mistral",
  "version": "1.2.0",
  "message": "Request transformation completed successfully",
  "processingTime": 15,
  "performance": {
    "successRate": 98.5
  }
}
```

### Custom Logger Integration

```javascript
// Custom structured logger
const customLogger = {
  debug: (level, metadata, message, ...args) => {
    console.log(`[${level}] ${metadata.transformer} ${message}`, ...args, metadata);
  }
  // ... implement info, warn, error similarly
};

const transformer = new MistralTransformer({}, customLogger);
```

## API Reference

### Constructor

```javascript
new MistralTransformer(options = {}, logger = console)
```

**Parameters:**
- `options`: Configuration options (see Configuration Parameters)
- `logger`: Logger instance (console by default)

### Methods

#### transformRequestIn(request, provider, context)
Transforms unified Claude Code Router request to Mistral API format.

**Parameters:**
- `request`: Unified request object
- `provider`: Provider configuration object
- `context`: Transformation context

**Returns:** Mistral API-compatible request object

#### transformResponseIn(response, context)
Transforms Mistral API response back to unified Claude Code Router format.

**Parameters:**
- `response`: Mistral API response object
- `context`: Transformation context

**Returns:** Unified response object or array of streaming chunks

#### getInfo()
Returns transformer metadata including supported models, features, and configuration.

**Returns:** Info object with metadata

#### getPerformanceMetrics()
Returns performance statistics including success rates and processing times.

**Returns:** Performance metrics object

#### healthCheck()
Performs health check and returns transformer status.

**Returns:** Health status object

#### validate()
Validates transformer configuration and returns validation results.

**Returns:** Validation result object

#### exportState()
Exports complete transformer state including configuration and metrics.

**Returns:** State object

#### updateConfiguration(newConfig)
Updates transformer configuration dynamically.

**Parameters:**
- `newConfig`: New configuration options

#### resetMetrics()
Resets performance metrics counters.

### Error Handling

All errors include structured information:

```javascript
{
  name: 'Error',
  message: 'Error message',
  type: 'ERROR_TYPE',           // VALIDATION_ERROR, NETWORK_ERROR, etc.
  recoverable: boolean,         // Whether error can be retried
  retryCount: number,           // Current retry attempt
  maxRetries: number,           // Maximum retry attempts
  statusCode: number,           // HTTP-like status code
  requestId: string,            // Request identifier
  context: object              // Additional context
}
```

## Troubleshooting

### Common Issues

#### Validation Errors
If you encounter validation errors, check:
- Required fields are present in requests
- Parameter values are within valid ranges
- Model names are supported by Mistral API

#### Performance Issues
- Monitor success rates with `getPerformanceMetrics()`
- Implement circuit breaker for fault tolerance
- Use exponential backoff for retries

#### Streaming Issues
- Ensure streaming context is properly set
- Handle streaming termination events
- Implement proper error handling for streaming chunks

### Best Practices

#### Configuration Management
- Validate configuration before deployment
- Use circuit breaker for production environments
- Monitor performance metrics regularly

#### Error Handling
- Implement retry logic for recoverable errors
- Use structured error handling patterns
- Monitor error rates and types

#### Performance Optimization
- Optimize request/response payload sizes
- Use streaming for long conversations
- Implement caching where appropriate

## Support

For issues and questions:
- Check the API documentation
- Review validation error messages
- Monitor performance metrics
- Enable debug logging for troubleshooting