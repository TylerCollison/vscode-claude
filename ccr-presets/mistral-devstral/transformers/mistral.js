// Mistral Transformer for Claude Code Router
// Transforms unified Claude Code Router requests to Mistral API format

module.exports = class MistralTransformer {
  constructor(options = {}, logger = console) {
    this.name = 'mistral';
    this.options = options;
    this.logger = this._setupLogger(logger);

    // Configure transformer options with advanced defaults
    this.maxTokens = options.maxTokens || 4096;
    this.temperature = options.temperature || 0.7;
    this.topP = options.topP || 1.0;

    // Advanced Mistral-specific parameters
    this.safePrompt = options.safePrompt !== undefined ? Boolean(options.safePrompt) : false;
    this.randomSeed = options.randomSeed !== undefined ? Number(options.randomSeed) : null;
    this.frequencyPenalty = options.frequencyPenalty !== undefined ? Number(options.frequencyPenalty) : 0.0;
    this.presencePenalty = options.presencePenalty !== undefined ? Number(options.presencePenalty) : 0.0;
    this.responseFormat = options.responseFormat || 'text';

    // Advanced configuration options
    this.timeout = options.timeout || 30000;
    this.maxRetries = options.maxRetries || 3;
    this.retryDelay = options.retryDelay || 1000;
    this.circuitBreakerThreshold = options.circuitBreakerThreshold || 5;

    // Performance monitoring
    this.performanceMetrics = {
      totalRequests: 0,
      successfulRequests: 0,
      failedRequests: 0,
      averageResponseTime: 0
    };

    this.logger.debug('MistralTransformer initialized with advanced features', { options });
  }

  /**
   * Setup logger with structured logging support
   * @private
   */
  _setupLogger(logger) {
    const structuredLogger = {
      transformer: 'mistral',
      version: '1.2.0'
    };

    if (typeof logger === 'function') {
      return {
        debug: (message, ...args) => logger('DEBUG', structuredLogger, message, ...args),
        info: (message, ...args) => logger('INFO', structuredLogger, message, ...args),
        warn: (message, ...args) => logger('WARN', structuredLogger, message, ...args),
        error: (message, ...args) => logger('ERROR', structuredLogger, message, ...args)
      };
    }

    // Enhanced console logger with structured format
    if (logger === console) {
      return {
        debug: (message, metadata) => console.debug(`[MISTRAL-TRANSFORMER] DEBUG: ${message}`, this._formatMetadata(metadata)),
        info: (message, metadata) => console.info(`[MISTRAL-TRANSFORMER] INFO: ${message}`, this._formatMetadata(metadata)),
        warn: (message, metadata) => console.warn(`[MISTRAL-TRANSFORMER] WARN: ${message}`, this._formatMetadata(metadata)),
        error: (message, metadata) => console.error(`[MISTRAL-TRANSFORMER] ERROR: ${message}`, this._formatMetadata(metadata))
      };
    }

    // Ensure logger has all necessary methods
    return {
      debug: logger.debug || console.debug,
      info: logger.info || console.info,
      warn: logger.warn || console.warn,
      error: logger.error || console.error
    };
  }

  /**
   * Format metadata for structured logging
   * @private
   */
  _formatMetadata(metadata) {
    if (!metadata || typeof metadata !== 'object') {
      return {};
    }

    // Remove circular references and limit data size
    const sanitized = {};

    Object.keys(metadata).slice(0, 10).forEach(key => { // Limit to 10 keys
      const value = metadata[key];

      if (typeof value === 'string' && value.length > 100) {
        sanitized[key] = value.substring(0, 100) + '...';
      } else if (typeof value === 'object' && value !== null) {
        sanitized[key] = '[Object]';
      } else {
        sanitized[key] = value;
      }
    });

    return sanitized;
  }

  /**
   * Get transformer configuration
   * @returns {Object} Configuration object
   */
  getConfiguration() {
    return {
      version: '1.2.0',
      advancedFeatures: {
        safePrompt: this.safePrompt,
        randomSeed: this.randomSeed,
        responseFormat: this.responseFormat,
        timeout: this.timeout,
        maxRetries: this.maxRetries,
        retryDelay: this.retryDelay,
        circuitBreakerThreshold: this.circuitBreakerThreshold
      },
      performance: this.getPerformanceMetrics(),
      supportedParameters: [
        'temperature', 'top_p', 'max_tokens', 'frequency_penalty', 'presence_penalty',
        'safe_prompt', 'random_seed', 'response_format', 'tool_choice'
      ]
    };
  }

  /**
   * Update transformer configuration
   * @param {Object} newConfig - New configuration options
   */
  updateConfiguration(newConfig) {
    if (newConfig.maxTokens !== undefined) {
      this.maxTokens = Number(newConfig.maxTokens);
    }
    if (newConfig.temperature !== undefined) {
      this.temperature = Number(newConfig.temperature);
    }
    if (newConfig.topP !== undefined) {
      this.topP = Number(newConfig.topP);
    }
    if (newConfig.safePrompt !== undefined) {
      this.safePrompt = Boolean(newConfig.safePrompt);
    }
    if (newConfig.randomSeed !== undefined) {
      this.randomSeed = Number(newConfig.randomSeed);
    }
    if (newConfig.responseFormat !== undefined) {
      this.responseFormat = newConfig.responseFormat;
    }
    if (newConfig.timeout !== undefined) {
      this.timeout = Number(newConfig.timeout);
    }
    if (newConfig.maxRetries !== undefined) {
      this.maxRetries = Number(newConfig.maxRetries);
    }
    if (newConfig.retryDelay !== undefined) {
      this.retryDelay = Number(newConfig.retryDelay);
    }

    this.logger.info('Transformer configuration updated', { newConfig });
  }

  /**
   * Create a circuit breaker for API calls
   * @private
   */
  _createCircuitBreaker() {
    let failureCount = 0;
    let lastFailureTime = 0;
    let circuitOpen = false;

    return {
      shouldAllowRequest: () => {
        if (!circuitOpen) return true;

        const timeSinceLastFailure = Date.now() - lastFailureTime;
        if (timeSinceLastFailure > this.retryDelay * 2) {
          circuitOpen = false;
          failureCount = 0;
          return true;
        }

        return false;
      },

      recordFailure: () => {
        failureCount++;
        lastFailureTime = Date.now();

        if (failureCount >= this.circuitBreakerThreshold) {
          circuitOpen = true;
          this.logger.warn('Circuit breaker activated due to consecutive failures', {
            failureCount,
            threshold: this.circuitBreakerThreshold
          });
        }
      },

      recordSuccess: () => {
        failureCount = 0;
        circuitOpen = false;
      },

      getStatus: () => ({
        circuitOpen,
        failureCount,
        lastFailureTime,
        threshold: this.circuitBreakerThreshold
      })
    };
  }

  /**
   * Transform unified Claude Code Router request to Mistral API format
   * @param {Object} request - Unified request object
   * @param {string} provider - Provider configuration
   * @param {Object} context - Context information
   * @returns {Object} Transformed Mistral API request
   */
  transformRequestIn(request, provider, context) {
    const startTime = Date.now();

    try {
      this.performanceMetrics.totalRequests++;

      this.logger.debug('Transforming request to Mistral format', {
        request: JSON.stringify(request, null, 2),
        provider,
        context
      });

      // Advanced request validation with detailed error messages
      this._validateRequestWithContext(request, context);

      // Create base Mistral request with validated fields only
      const mistralRequest = {
        model: request.model,
        messages: this._transformMessages(request.messages),
        temperature: this._validateParameter(request.temperature, this.temperature, 'temperature', 0, 2),
        top_p: this._validateParameter(request.topP, this.topP, 'top_p', 0, 1),
        max_tokens: this._validateParameter(request.maxTokens, this.maxTokens, 'max_tokens', 1, 32000),
        stream: Boolean(request.stream)
      };

      // Add optional Mistral-supported parameters with validation
      this._addOptionalParameters(mistralRequest, request);

      // Handle tool calls if present
      if (request.tools && request.tools.length > 0) {
        mistralRequest.tools = this._transformTools(request.tools);
      }

      // Remove any undefined values to prevent 422 errors
      this._cleanRequest(mistralRequest);

      // Performance monitoring
      const processingTime = Date.now() - startTime;
      this._updatePerformanceMetrics(true, processingTime);

      this.logger.info('Request transformation completed successfully', {
        processingTime,
        mistralRequest: { ...mistralRequest, messages: `[${mistralRequest.messages?.length || 0} messages]` }
      });

      return mistralRequest;
    } catch (error) {
      // Enhanced error handling with categorization
      const processingTime = Date.now() - startTime;
      this._updatePerformanceMetrics(false, processingTime);

      const categorizedError = this._categorizeError(error, request, context);

      this.logger.error('Request transformation failed', {
        error: categorizedError.message,
        errorType: categorizedError.type,
        requestId: request.id,
        processingTime,
        stack: categorizedError.stack,
        recoverable: categorizedError.recoverable
      });

      throw categorizedError;
    }
  }

  /**
   * Transform Mistral API response to unified Claude Code Router format
   * @param {Object} response - Mistral API response or SSE chunk
   * @param {Object} context - Context information
   * @returns {Object|Array} Transformed unified response or array of SSE chunks
   */
  transformResponseIn(response, context) {
    const startTime = Date.now();

    try {
      this.logger.debug('Transforming Mistral response to unified format', {
        response: JSON.stringify(response, null, 2),
        context
      });

      // Handle streaming SSE chunks
      if (this._isSSEChunk(response) || (context && context.stream)) {
        const chunks = this._transformSSEChunk(response, context);
        this._logResponseTransformation('streaming', startTime, chunks.length);
        return chunks;
      }

      // Handle error responses first
      if (this._isErrorResponse(response)) {
        // Check if we're in streaming context
        if (context.stream || this._isSSEChunk(response)) {
          const streamingError = this._transformStreamingErrorResponse(response, context);
          this._logResponseTransformation('streaming_error', startTime, 1);
          return [streamingError]; // Return as array for consistency
        }
        const errorResponse = this._transformErrorResponse(response, context);
        this._logResponseTransformation('error', startTime, 1);
        return errorResponse;
      }

      // Advanced response structure validation
      this._validateResponseStructureWithContext(response, context);

      const unifiedResponse = {
        id: this._getResponseId(response),
        object: 'chat.completion',
        created: this._getCreatedTimestamp(response),
        model: response.model,
        usage: this._transformUsage(response.usage),
        choices: this._transformChoices(response.choices)
      };

      // Add provider-specific metadata with advanced features
      unifiedResponse.provider = {
        name: 'mistral',
        type: 'api',
        responseType: this._getResponseType(response),
        advancedFeatures: this._getResponseAdvancedFeatures(response)
      };

      // Handle streaming responses if needed
      if (response.stream || context.stream) {
        unifiedResponse.stream = true;
      }

      // Add performance metadata
      unifiedResponse.performance = {
        processingTime: Date.now() - startTime,
        transformerVersion: '1.2.0'
      };

      this.logger.info('Response transformation completed successfully', {
        processingTime: Date.now() - startTime,
        responseType: unifiedResponse.provider.responseType,
        choices: unifiedResponse.choices.length
      });

      return unifiedResponse;
    } catch (error) {
      const processingTime = Date.now() - startTime;
      const categorizedError = this._categorizeError(error, { id: context?.requestId }, context);

      this.logger.error('Response transformation failed', {
        error: categorizedError.message,
        errorType: categorizedError.type,
        processingTime,
        stack: categorizedError.stack
      });

      throw categorizedError;
    }
  }

  /**
   * Log response transformation with performance metrics
   * @private
   */
  _logResponseTransformation(type, startTime, count = 1) {
    const processingTime = Date.now() - startTime;

    this.logger.info(`Response transformation (${type}) completed`, {
      processingTime,
      count,
      performance: this.getPerformanceMetrics()
    });
  }

  /**
   * Enhanced response validation with context
   * @private
   */
  _validateResponseStructureWithContext(response, context) {
    try {
      this._validateResponseStructure(response, context);

      // Additional context-aware validation
      if (context) {
        // Validate streaming context consistency
        if (context.stream && !this._isSSEChunk(response)) {
          this.logger.warn('Streaming context but response is not SSE format');
        }

        // Validate model consistency
        if (context.expectedModel && response.model !== context.expectedModel) {
          this.logger.warn('Response model differs from expected model', {
            expected: context.expectedModel,
            actual: response.model
          });
        }
      }
    } catch (error) {
      throw this._createValidationError(error.message, response, context);
    }
  }

  /**
   * Extract advanced features from response
   * @private
   */
  _getResponseAdvancedFeatures(response) {
    const features = {};

    // Check for safe prompt filtering
    if (response.safe_prompt !== undefined) {
      features.safePromptUsed = Boolean(response.safe_prompt);
    }

    // Check for random seed
    if (response.random_seed !== undefined) {
      features.randomSeedUsed = response.random_seed;
    }

    // Check for response format
    if (response.response_format) {
      features.responseFormat = response.response_format;
    }

    // Check for tool usage
    if (response.choices) {
      const hasToolCalls = response.choices.some(choice =>
        choice.message?.tool_calls || choice.delta?.tool_calls
      );
      if (hasToolCalls) {
        features.toolUsage = true;
      }
    }

    return features;
  }

  /**
   * Validate request structure and required fields
   * @private
   */
  _validateRequest(request) {
    if (!request || typeof request !== 'object') {
      throw new Error('Invalid request: must be an object');
    }

    // Validate messages array
    if (!Array.isArray(request.messages) || request.messages.length === 0) {
      throw new Error('Invalid messages: must be a non-empty array');
    }

    // Validate each message structure
    request.messages.forEach((message, index) => {
      if (!message || typeof message !== 'object') {
        throw new Error(`Invalid message at index ${index}: must be an object`);
      }

      if (!message.role || typeof message.role !== 'string') {
        throw new Error(`Invalid message role at index ${index}: must be a string`);
      }

      if (message.content === undefined) {
        throw new Error(`Invalid message content at index ${index}: must be defined`);
      }

      // Allow string, null, array, or object content (Claude Code Router format)
      const validContentTypes = ['string', 'object', 'null'];
      const contentType = typeof message.content;
      if (!validContentTypes.includes(contentType) && message.content !== null) {
        throw new Error(`Invalid message content at index ${index}: must be string, null, array, or object`);
      }
    });
  }

  /**
   * Validate and normalize parameter values
   * @private
   */
  _validateParameter(value, defaultValue, paramName, minValue = 0, maxValue = Infinity) {
    const finalValue = value !== undefined ? value : defaultValue;

    if (finalValue === undefined) {
      return undefined;
    }

    // Convert to number if needed
    const numericValue = Number(finalValue);

    if (isNaN(numericValue)) {
      throw new Error(`Invalid ${paramName}: must be a number`);
    }

    if (numericValue < minValue || numericValue > maxValue) {
      throw new Error(`Invalid ${paramName}: must be between ${minValue} and ${maxValue}`);
    }

    return numericValue;
  }

  /**
   * Add optional Mistral-supported parameters with validation
   * @private
   */
  _addOptionalParameters(mistralRequest, request) {
    // Add stop sequences if present
    if (request.stop) {
      if (Array.isArray(request.stop) && request.stop.length > 0) {
        mistralRequest.stop = request.stop.slice(0, 4); // Limit to 4 stop sequences
      } else if (typeof request.stop === 'string' && request.stop.trim()) {
        mistralRequest.stop = [request.stop.trim()];
      }
    }

    // Add Mistral-supported optional parameters with comprehensive validation
    const optionalParams = [
      'frequency_penalty',
      'presence_penalty',
      'random_seed',
      'safe_prompt'
    ];

    optionalParams.forEach(param => {
      if (request[param] !== undefined) {
        mistralRequest[param] = this._validateParameter(
          request[param],
          undefined,
          param,
          param.includes('penalty') ? -2.0 : 0,
          param.includes('penalty') ? 2.0 : Infinity
        );
      }
    });

    // Add advanced Mistral-specific parameters with enhanced validation
    this._addAdvancedParameters(mistralRequest, request);
  }

  /**
   * Add advanced Mistral-specific parameters with enhanced validation
   * @private
   */
  _addAdvancedParameters(mistralRequest, request) {
    // Response format parameter
    if (request.response_format !== undefined) {
      mistralRequest.response_format = this._validateResponseFormat(request.response_format);
    }

    // Safe prompt filtering
    if (request.safe_prompt !== undefined) {
      mistralRequest.safe_prompt = Boolean(request.safe_prompt);
    } else if (this.safePrompt !== undefined) {
      mistralRequest.safe_prompt = this.safePrompt;
    }

    // Random seed for deterministic results
    if (request.random_seed !== undefined) {
      const seed = Number(request.random_seed);
      if (Number.isInteger(seed) && seed >= 0) {
        mistralRequest.random_seed = seed;
      }
    } else if (this.randomSeed !== null) {
      mistralRequest.random_seed = this.randomSeed;
    }

    // Advanced tool calling parameters
    if (request.tool_choice !== undefined) {
      mistralRequest.tool_choice = this._validateToolChoice(request.tool_choice);
    }

    // Temperature with advanced validation
    if (request.temperature !== undefined) {
      mistralRequest.temperature = this._validateAdvancedParameter(
        request.temperature,
        'temperature',
        0.0,
        2.0,
        2
      );
    }

    // Top-p with advanced validation
    if (request.top_p !== undefined) {
      mistralRequest.top_p = this._validateAdvancedParameter(
        request.top_p,
        'top_p',
        0.0,
        1.0,
        3
      );
    }

    // Penalty parameters with advanced validation
    if (request.frequency_penalty !== undefined) {
      mistralRequest.frequency_penalty = this._validateAdvancedParameter(
        request.frequency_penalty,
        'frequency_penalty',
        -2.0,
        2.0,
        2
      );
    }

    if (request.presence_penalty !== undefined) {
      mistralRequest.presence_penalty = this._validateAdvancedParameter(
        request.presence_penalty,
        'presence_penalty',
        -2.0,
        2.0,
        2
      );
    }

    // Max tokens with advanced validation
    if (request.max_tokens !== undefined) {
      mistralRequest.max_tokens = this._validateMaxTokens(request.max_tokens);
    }
  }

  /**
   * Validate response format parameter
   * @private
   */
  _validateResponseFormat(format) {
    const validFormats = ['text', 'json_object'];

    if (typeof format === 'string' && validFormats.includes(format)) {
      return format;
    }

    if (typeof format === 'object' && format.type && validFormats.includes(format.type)) {
      return format;
    }

    this.logger.warn('Invalid response format, defaulting to text', { format });
    return 'text';
  }

  /**
   * Validate tool choice parameter
   * @private
   */
  _validateToolChoice(toolChoice) {
    if (toolChoice === 'auto' || toolChoice === 'none') {
      return toolChoice;
    }

    if (typeof toolChoice === 'object' && toolChoice.type === 'function' && toolChoice.function?.name) {
      return toolChoice;
    }

    this.logger.warn('Invalid tool choice, defaulting to auto', { toolChoice });
    return 'auto';
  }

  /**
   * Advanced parameter validation with precision control
   * @private
   */
  _validateAdvancedParameter(value, paramName, minValue, maxValue, decimalPlaces = 2) {
    const finalValue = Number(value);

    if (isNaN(finalValue)) {
      throw new Error(`Invalid ${paramName}: must be a number`);
    }

    if (finalValue < minValue || finalValue > maxValue) {
      throw new Error(`Invalid ${paramName}: must be between ${minValue} and ${maxValue}`);
    }

    // Round to specified decimal places
    const multiplier = Math.pow(10, decimalPlaces);
    return Math.round(finalValue * multiplier) / multiplier;
  }

  /**
   * Validate max tokens with model-specific limits
   * @private
   */
  _validateMaxTokens(value) {
    const tokens = Number(value);

    if (isNaN(tokens) || tokens < 1) {
      throw new Error('Invalid max_tokens: must be a positive number');
    }

    // Model-specific token limits (can be extended based on actual model capabilities)
    const maxAllowed = 32000; // Conservative limit

    if (tokens > maxAllowed) {
      this.logger.warn(`max_tokens exceeds recommended limit, truncating to ${maxAllowed}`, { tokens });
      return maxAllowed;
    }

    return Math.floor(tokens);
  }

  /**
   * Clean request by removing undefined values
   * @private
   */
  _cleanRequest(mistralRequest) {
    Object.keys(mistralRequest).forEach(key => {
      if (mistralRequest[key] === undefined) {
        delete mistralRequest[key];
      }
    });
  }

  /**
   * Transform unified messages to Mistral message format
   * @private
   */
  _transformMessages(messages) {
    if (!Array.isArray(messages)) {
      return [];
    }

    return messages.map((message, index) => {
      try {
        const mistralMessage = {
          role: this._mapRole(message.role),
          content: this._extractTextContent(message.content)
        };

        // Handle tool calls in messages
        if (message.tool_calls && Array.isArray(message.tool_calls)) {
          mistralMessage.tool_calls = message.tool_calls.map((toolCall, toolIndex) => {
            if (!toolCall.function || !toolCall.function.name) {
              throw new Error(`Invalid tool call at message ${index}, tool ${toolIndex}: missing function name`);
            }

            return {
              id: toolCall.id || `call_${Date.now()}_${index}_${toolIndex}`,
              type: 'function',
              function: {
                name: toolCall.function.name,
                arguments: typeof toolCall.function.arguments === 'string'
                  ? toolCall.function.arguments
                  : JSON.stringify(toolCall.function.arguments || {})
              }
            };
          });
        }

        // Handle tool results
        if (message.tool_call_id) {
          mistralMessage.tool_call_id = String(message.tool_call_id);
        }

        // Clean undefined values
        Object.keys(mistralMessage).forEach(key => {
          if (mistralMessage[key] === undefined) {
            delete mistralMessage[key];
          }
        });

        return mistralMessage;
      } catch (error) {
        this.logger.error(`Failed to transform message at index ${index}`, {
          message,
          error: error.message
        });
        throw error;
      }
    });
  }

  /**
   * Extract text content from Claude Code Router's complex message format
   * Handles both simple strings and complex content arrays
   * @private
   */
  _extractTextContent(content) {
    if (content === null || content === undefined) {
      return '';
    }

    // Handle simple string content
    if (typeof content === 'string') {
      return content;
    }

    // Handle complex content array (Claude Code Router format)
    if (Array.isArray(content)) {
      // Extract text from all text blocks
      const textParts = content
        .filter(block => block.type === 'text' && block.text)
        .map(block => block.text)
        .filter(text => text && text.trim());

      return textParts.join('\n') || '';
    }

    // Handle object format (fallback)
    if (typeof content === 'object') {
      // Try to extract text property
      if (content.text) {
        return String(content.text);
      }
      // Try to extract from content array if present
      if (content.content && Array.isArray(content.content)) {
        return this._extractTextContent(content.content);
      }
    }

    // Final fallback
    return String(content);
  }

  /**
   * Map unified role to Mistral role
   * @private
   */
  _mapRole(role) {
    const roleMap = {
      'user': 'user',
      'assistant': 'assistant',
      'system': 'system',
      'tool': 'tool'
    };

    return roleMap[role] || 'user';
  }

  /**
   * Transform unified tools to Mistral tool format
   * @private
   */
  _transformTools(tools) {
    return tools.map((tool, index) => {
      try {
        if (!tool.function || !tool.function.name) {
          throw new Error(`Invalid tool at index ${index}: missing function name`);
        }

        const mistralTool = {
          type: 'function',
          function: {
            name: String(tool.function.name),
            description: tool.function.description ? String(tool.function.description) : '',
            parameters: this._validateToolParameters(tool.function.parameters || {})
          }
        };

        // Clean undefined values
        Object.keys(mistralTool.function).forEach(key => {
          if (mistralTool.function[key] === undefined) {
            delete mistralTool.function[key];
          }
        });

        return mistralTool;
      } catch (error) {
        this.logger.error(`Failed to transform tool at index ${index}`, {
          tool,
          error: error.message
        });
        throw error;
      }
    });
  }

  /**
   * Validate and normalize tool parameters
   * @private
   */
  _validateToolParameters(parameters) {
    if (!parameters || typeof parameters !== 'object') {
      return {};
    }

    // Ensure parameters is a valid JSON schema object
    const validatedParams = {
      type: 'object',
      properties: {},
      required: []
    };

    if (parameters.type && typeof parameters.type === 'string') {
      validatedParams.type = parameters.type;
    }

    if (parameters.properties && typeof parameters.properties === 'object') {
      validatedParams.properties = { ...parameters.properties };
    }

    if (parameters.required && Array.isArray(parameters.required)) {
      validatedParams.required = parameters.required.filter(r => typeof r === 'string');
    }

    // Clean undefined values
    Object.keys(validatedParams).forEach(key => {
      if (validatedParams[key] === undefined ||
          (Array.isArray(validatedParams[key]) && validatedParams[key].length === 0)) {
        delete validatedParams[key];
      }
    });

    return validatedParams;
  }

  /**
   * Transform Mistral usage to unified format
   * @private
   */
  _transformUsage(usage) {
    const defaultUsage = {
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0
    };

    if (!usage || typeof usage !== 'object') {
      return defaultUsage;
    }

    return {
      prompt_tokens: this._validateTokenCount(usage.prompt_tokens),
      completion_tokens: this._validateTokenCount(usage.completion_tokens),
      total_tokens: this._validateTokenCount(usage.total_tokens)
    };
  }

  /**
   * Validate and normalize token count
   * @private
   */
  _validateTokenCount(count) {
    if (count === undefined || count === null) {
      return 0;
    }
    const numericCount = Number(count);
    return isNaN(numericCount) || numericCount < 0 ? 0 : Math.floor(numericCount);
  }

  /**
   * Check if response is an SSE chunk
   * @private
   */
  _isSSEChunk(response) {
    if (!response) {
      return false;
    }

    // Handle string responses (raw SSE)
    if (typeof response === 'string') {
      return response.includes('data:') || response.includes('[DONE]');
    }

    // Handle object responses
    if (typeof response === 'object') {
      // Check for SSE-specific patterns
      return (
        response.hasOwnProperty('data') ||
        response.hasOwnProperty('event') ||
        response.hasOwnProperty('chunk') ||
        response.type === 'stream' ||
        (response.choices && Array.isArray(response.choices) &&
         response.choices.some(choice => choice.hasOwnProperty('delta')))
      );
    }

    return false;
  }

  /**
   * Transform SSE chunk to unified streaming format
   * @private
   */
  _transformSSEChunk(chunk, context) {
    try {
      this.logger.debug('Transforming SSE chunk', { chunk, context });

      // Handle raw SSE string data
      if (typeof chunk === 'string') {
        return this._parseSSEString(chunk, context);
      }

      // Handle structured SSE chunk
      const transformedChunks = [];

      // Handle [DONE] event
      if (chunk.event === 'done' || chunk.data === '[DONE]') {
        transformedChunks.push({
          event: 'done',
          object: 'stream.chunk',
          id: `chunk-done-${Date.now()}`,
          provider: {
            name: 'mistral',
            type: 'api',
            responseType: 'streaming'
          }
        });
        return transformedChunks;
      }

      // Parse data field if present
      if (chunk.data) {
        const dataChunks = this._parseSSEData(chunk.data, context);
        transformedChunks.push(...dataChunks);
      }

      // Handle direct chunk structure
      if (chunk.choices && Array.isArray(chunk.choices)) {
        for (const choice of chunk.choices) {
          const parsedChunk = this._parseStreamingChoice(choice, context);
          if (parsedChunk) {
            parsedChunk.created = chunk.created || this._getCreatedTimestamp(chunk);
            parsedChunk.model = chunk.model || context.model;
            parsedChunk.id = chunk.id || parsedChunk.id;
            transformedChunks.push(parsedChunk);
          }
        }
      } else if (chunk.delta) {
        const parsedChunk = this._parseStreamingChoice({ delta: chunk.delta }, context);
        if (parsedChunk) {
          parsedChunk.created = chunk.created || this._getCreatedTimestamp(chunk);
          parsedChunk.model = chunk.model || context.model;
          parsedChunk.id = chunk.id || parsedChunk.id;
          transformedChunks.push(parsedChunk);
        }
      }

      return transformedChunks;
    } catch (error) {
      this.logger.error('SSE chunk transformation failed', {
        error: error.message,
        chunk,
        stack: error.stack
      });
      // Return empty array to avoid breaking the stream
      return [];
    }
  }

  /**
   * Parse SSE data string into chunks
   * @private
   */
  _parseSSEString(dataString, context) {
    const chunks = [];
    const lines = dataString.split('\n');

    for (const line of lines) {
      if (line.trim() === '') continue;

      if (line.startsWith('data: ')) {
        const data = line.slice(6).trim(); // Remove 'data: ' prefix

        if (data === '[DONE]') {
          chunks.push({
            event: 'done',
            object: 'stream.chunk',
            id: `chunk-done-${Date.now()}`,
            provider: {
              name: 'mistral',
              type: 'api',
              responseType: 'streaming'
            }
          });
          continue;
        }

        try {
          const parsedData = JSON.parse(data);
          const dataChunks = this._parseSSEData(parsedData, context);
          chunks.push(...dataChunks);
        } catch (parseError) {
          this.logger.warn('Failed to parse SSE data', {
            data,
            error: parseError.message
          });
        }
      }
    }

    return chunks;
  }

  /**
   * Parse SSE data object into streaming chunks
   * @private
   */
  _parseSSEData(data, context) {
    const chunks = [];

    if (!data || typeof data !== 'object') {
      return chunks;
    }

    // Handle error in streaming
    if (data.error) {
      chunks.push({
        event: 'error',
        object: 'stream.chunk',
        id: `chunk-error-${Date.now()}`,
        error: this._transformErrorResponse(data, context),
        provider: {
          name: 'mistral',
          type: 'api',
          responseType: 'streaming'
        }
      });
      return chunks;
    }

    // Handle streaming choice data
    if (data.choices && Array.isArray(data.choices)) {
      for (const choice of data.choices) {
        const chunk = this._parseStreamingChoice(choice, context);
        if (chunk) {
          chunks.push(chunk);
        }
      }
    }

    return chunks;
  }

  /**
   * Parse streaming choice into unified chunk format
   * @private
   */
  _parseStreamingChoice(choice, context) {
    if (!choice || typeof choice !== 'object') {
      return null;
    }

    const chunk = {
      object: 'stream.chunk',
      id: `chunk-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
      index: choice.index || 0,
      created: this._getCreatedTimestamp(choice),
      model: choice.model || context.model,
      provider: {
        name: 'mistral',
        type: 'api',
        responseType: 'streaming'
      }
    };

    // Handle delta content
    if (choice.delta && typeof choice.delta === 'object') {
      chunk.delta = this._transformDelta(choice.delta);
    }

    // Handle message structure
    if (choice.message && typeof choice.message === 'object') {
      chunk.message = this._transformChoiceMessage(choice.message, choice.index || 0);
    }

    // Handle finish reason
    if (choice.finish_reason) {
      chunk.finish_reason = this._validateFinishReason(choice.finish_reason);
    }

    // Handle tool calls in streaming
    if (choice.delta && choice.delta.tool_calls) {
      chunk.delta.tool_calls = this._transformToolCalls(choice.delta.tool_calls, choice.index || 0);
    }

    return chunk;
  }

  /**
   * Transform delta content for streaming
   * @private
   */
  _transformDelta(delta) {
    const transformedDelta = {};

    if (delta.role) {
      transformedDelta.role = this._validateMessageRole(delta.role);
    }

    if (delta.content !== undefined && delta.content !== null) {
      transformedDelta.content = this._validateMessageContent(delta.content);
    }

    if (delta.tool_calls && Array.isArray(delta.tool_calls)) {
      transformedDelta.tool_calls = this._transformToolCalls(delta.tool_calls, 0);
    }

    return transformedDelta;
  }

  /**
   * Check if response is an error response
   * @private
   */
  _isErrorResponse(response) {
    if (!response || typeof response !== 'object') {
      return false;
    }

    return (
      response.error ||
      response.status_code ||
      (response.status && response.status >= 400) ||
      response.type === 'error' ||
      (response.message && typeof response.message === 'string' && response.message.includes('error'))
    );
  }

  /**
   * Transform error response to unified format
   * @private
   */
  _transformErrorResponse(response, context) {
    const errorCode = response.status_code || response.status || 500;
    const errorMessage = response.error?.message || response.message || response.error || 'Unknown error';

    return {
      id: response.id || `error-${Date.now()}`,
      object: 'error',
      created: response.created || Math.floor(Date.now() / 1000),
      model: response.model || 'unknown',
      error: {
        code: errorCode,
        message: errorMessage,
        type: response.error?.type || 'api_error',
        param: response.error?.param,
        status: errorCode
      },
      provider: {
        name: 'mistral',
        type: 'api',
        responseType: 'error'
      }
    };
  }

  /**
   * Transform streaming error response
   * @private
   */
  _transformStreamingErrorResponse(response, context) {
    const errorCode = response.status_code || response.status || 500;
    const errorMessage = response.error?.message || response.message || response.error || 'Streaming error';

    return {
      id: response.id || `stream-error-${Date.now()}`,
      object: 'stream.error',
      created: response.created || Math.floor(Date.now() / 1000),
      model: response.model || 'unknown',
      error: {
        code: errorCode,
        message: errorMessage,
        type: response.error?.type || 'stream_error',
        param: response.error?.param,
        status: errorCode
      },
      provider: {
        name: 'mistral',
        type: 'api',
        responseType: 'streaming'
      }
    };
  }

  /**
   * Validate response structure
   * @private
   */
  _validateResponseStructure(response, context) {
    if (!response) {
      throw new Error('Invalid Mistral response: must be an object');
    }

    // Handle string responses (could be raw SSE)
    if (typeof response === 'string') {
      // Only allow SSE-formatted strings
      if (!response.includes('data:') && !response.includes('[DONE]')) {
        throw new Error('Invalid Mistral response: must be an object');
      }
      return;
    }

    if (typeof response !== 'object') {
      throw new Error('Invalid Mistral response: must be an object');
    }

    // Skip validation for streaming chunks - they have different structure
    if (this._isSSEChunk(response) || response.type === 'stream' || (context && context.stream)) {
      return;
    }

    // For successful responses, validate required structure
    if (!this._isErrorResponse(response)) {
      // Check for valid choices array
      if (!response.choices || !Array.isArray(response.choices)) {
        throw new Error('Invalid Mistral response: missing or invalid choices array');
      }

      // Validate each choice
      response.choices.forEach((choice, index) => {
        if (!choice || typeof choice !== 'object') {
          throw new Error(`Invalid choice at index ${index}: must be an object`);
        }

        // Check if this is a streaming choice with delta
        if (choice.delta && typeof choice.delta === 'object') {
          // Streaming choice - validate delta structure
          if (choice.delta.content === undefined && !choice.delta.tool_calls && !choice.delta.role) {
            // Allow empty delta for streaming (it could be just finishing)
          }
          return;
        }

        // Regular choice - validate message structure
        if (!choice.message || typeof choice.message !== 'object') {
          throw new Error(`Invalid message in choice ${index}: must be an object`);
        }

        if (!choice.message.role || typeof choice.message.role !== 'string') {
          throw new Error(`Invalid role in choice ${index}: must be a string`);
        }

        if (choice.message.content === undefined && !choice.message.tool_calls) {
          throw new Error(`Invalid content in choice ${index}: must have content or tool_calls`);
        }
      });
    }
  }

  /**
   * Get validated response ID
   * @private
   */
  _getResponseId(response) {
    if (response.id && typeof response.id === 'string') {
      return response.id;
    }
    return `mistral-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
  }

  /**
   * Get created timestamp
   * @private
   */
  _getCreatedTimestamp(response) {
    if (response.created && typeof response.created === 'number') {
      return response.created;
    }
    return Math.floor(Date.now() / 1000);
  }

  /**
   * Get response type
   * @private
   */
  _getResponseType(response) {
    if (this._isErrorResponse(response)) {
      return 'error';
    }
    if (response.stream || this._isSSEChunk(response) || response.type === 'stream') {
      return 'streaming';
    }
    return 'completion';
  }

  /**
   * Transform Mistral choices to unified format
   * @private
   */
  _transformChoices(choices) {
    if (!Array.isArray(choices)) {
      return [{
        index: 0,
        message: {
          role: 'assistant',
          content: ''
        },
        finish_reason: 'stop'
      }];
    }

    return choices.map((choice, index) => {
      const indexValue = choice.index !== undefined ? choice.index : index;

      return {
        index: indexValue,
        message: this._transformChoiceMessage(choice.message, indexValue),
        finish_reason: this._validateFinishReason(choice.finish_reason),
        logprobs: choice.logprobs
      };
    });
  }

  /**
   * Transform choice message with validation
   * @private
   */
  _transformChoiceMessage(message, index) {
    if (!message || typeof message !== 'object') {
      this.logger.warn(`Invalid message in choice ${index}, using default message`);
      return {
        role: 'assistant',
        content: ''
      };
    }

    const transformedMessage = {
      role: this._validateMessageRole(message.role),
      content: this._validateMessageContent(message.content)
    };

    // Handle tool calls if present
    if (message.tool_calls && Array.isArray(message.tool_calls)) {
      transformedMessage.tool_calls = this._transformToolCalls(message.tool_calls, index);
    }

    return transformedMessage;
  }

  /**
   * Validate and normalize message role
   * @private
   */
  _validateMessageRole(role) {
    const validRoles = ['user', 'assistant', 'system', 'tool'];
    if (role && validRoles.includes(role)) {
      return role;
    }
    return 'assistant';
  }

  /**
   * Validate and normalize message content
   * @private
   */
  _validateMessageContent(content) {
    return this._extractTextContent(content);
  }

  /**
   * Transform tool calls with validation
   * @private
   */
  _transformToolCalls(toolCalls, choiceIndex) {
    return toolCalls.map((toolCall, index) => {
      if (!toolCall || typeof toolCall !== 'object') {
        this.logger.warn(`Invalid tool call at choice ${choiceIndex}, index ${index}`);
        return {
          id: `call_${Date.now()}_${choiceIndex}_${index}`,
          type: 'function',
          function: {
            name: 'unknown',
            arguments: '{}'
          }
        };
      }

      return {
        id: toolCall.id || `call_${Date.now()}_${choiceIndex}_${index}`,
        type: toolCall.type || 'function',
        function: {
          name: toolCall.function?.name || 'unknown',
          arguments: typeof toolCall.function?.arguments === 'string'
            ? toolCall.function.arguments
            : JSON.stringify(toolCall.function?.arguments || {})
        }
      };
    });
  }

  /**
   * Transform streaming tool calls with incremental data support
   * @private
   */
  _transformStreamingToolCalls(toolCalls, choiceIndex) {
    return toolCalls.map((toolCall, index) => {
      if (!toolCall || typeof toolCall !== 'object') {
        this.logger.warn(`Invalid streaming tool call at choice ${choiceIndex}, index ${index}`);
        return {
          index,
          id: `stream-call_${Date.now()}_${choiceIndex}_${index}`,
          type: 'function',
          function: {
            name: 'unknown',
            arguments: '{}'
          }
        };
      }

      return {
        index,
        id: toolCall.id || `stream-call_${Date.now()}_${choiceIndex}_${index}`,
        type: toolCall.type || 'function',
        function: {
          name: toolCall.function?.name || 'unknown',
          arguments: toolCall.function?.arguments || '{}'
        }
      };
    });
  }

  /**
   * Validate finish reason
   * @private
   */
  _validateFinishReason(reason) {
    const validReasons = ['stop', 'length', 'tool_calls', 'content_filter', 'null'];
    if (reason && validReasons.includes(reason)) {
      return reason;
    }
    return 'stop';
  }

  /**
   * Validate streaming message role
   * @private
   */
  _validateStreamingRole(role) {
    const validRoles = ['user', 'assistant', 'system', 'tool'];
    if (role && validRoles.includes(role)) {
      return role;
    }
    return 'assistant';
  }

  /**
   * Validate streaming message content
   * @private
   */
  _validateStreamingContent(content) {
    if (content === null || content === undefined) {
      return '';
    }
    if (typeof content === 'string') {
      return content;
    }
    // Handle incremental content in streaming
    return String(content);
  }


  /**
   * Validate request with context-aware validation
   * @private
   */
  _validateRequestWithContext(request, context) {
    try {
      this._validateRequest(request);

      // Additional context-aware validation
      if (context) {
        // Validate streaming context
        if (context.stream && request.stream === undefined) {
          this.logger.warn('Stream context detected but request.stream not set');
        }

        // Validate rate limiting context
        if (context.rateLimited) {
          this.logger.info('Processing rate-limited request');
        }
      }
    } catch (error) {
      // Add context information to validation errors
      throw this._createValidationError(error.message, request, context);
    }
  }

  /**
   * Categorize error for better error handling
   * @private
   */
  _categorizeError(error, request, context) {
    const errorMessage = error.message || 'Unknown error';

    // Categorize by error type
    if (errorMessage.includes('Invalid') || errorMessage.includes('missing') || errorMessage.includes('required')) {
      return this._createValidationError(errorMessage, request, context);
    }

    if (errorMessage.includes('network') || errorMessage.includes('timeout') || errorMessage.includes('connection')) {
      return this._createNetworkError(errorMessage, error.stack, request, context);
    }

    if (errorMessage.includes('rate limit') || errorMessage.includes('quota') || errorMessage.includes('too many')) {
      return this._createRateLimitError(errorMessage, error.stack, request, context);
    }

    // Default to internal error
    return this._createInternalError(errorMessage, error.stack, request, context);
  }

  /**
   * Create validation error with recovery information
   * @private
   */
  _createValidationError(message, request, context) {
    const error = new Error(`Validation Error: ${message}`);
    error.type = 'VALIDATION_ERROR';
    error.recoverable = false;
    error.requestId = request.id;
    error.context = context;
    error.statusCode = 400;
    return error;
  }

  /**
   * Create network error with retry information
   * @private
   */
  _createNetworkError(message, stack, request, context) {
    const error = new Error(`Network Error: ${message}`);
    error.type = 'NETWORK_ERROR';
    error.recoverable = true;
    error.retryCount = (context?.retryCount || 0) + 1;
    error.maxRetries = this.maxRetries;
    error.requestId = request.id;
    error.stack = stack;
    error.statusCode = 503;
    return error;
  }

  /**
   * Create rate limit error with backoff information
   * @private
   */
  _createRateLimitError(message, stack, request, context) {
    const error = new Error(`Rate Limit Error: ${message}`);
    error.type = 'RATE_LIMIT_ERROR';
    error.recoverable = true;
    error.retryCount = (context?.retryCount || 0) + 1;
    error.retryAfter = context?.retryAfter || this.retryDelay;
    error.requestId = request.id;
    error.stack = stack;
    error.statusCode = 429;
    return error;
  }

  /**
   * Create internal error with diagnostic information
   * @private
   */
  _createInternalError(message, stack, request, context) {
    const error = new Error(`Internal Error: ${message}`);
    error.type = 'INTERNAL_ERROR';
    error.recoverable = false;
    error.requestId = request.id;
    error.stack = stack;
    error.context = context;
    error.statusCode = 500;
    return error;
  }

  /**
   * Update performance metrics
   * @private
   */
  _updatePerformanceMetrics(success, processingTime) {
    if (success) {
      this.performanceMetrics.successfulRequests++;
    } else {
      this.performanceMetrics.failedRequests++;
    }

    // Calculate moving average for response time
    const totalRequests = this.performanceMetrics.totalRequests;
    const currentAverage = this.performanceMetrics.averageResponseTime;

    this.performanceMetrics.averageResponseTime =
      ((currentAverage * (totalRequests - 1)) + processingTime) / totalRequests;
  }

  /**
   * Get performance metrics
   * @returns {Object} Performance statistics
   */
  getPerformanceMetrics() {
    return {
      ...this.performanceMetrics,
      successRate: this.performanceMetrics.totalRequests > 0
        ? (this.performanceMetrics.successfulRequests / this.performanceMetrics.totalRequests) * 100
        : 0,
      failureRate: this.performanceMetrics.totalRequests > 0
        ? (this.performanceMetrics.failedRequests / this.performanceMetrics.totalRequests) * 100
        : 0
    };
  }

  /**
   * Health check for the transformer with detailed status
   * @returns {Promise<Object>} Health status object
   */
  async healthCheck() {
    const metrics = this.getPerformanceMetrics();

    return {
      healthy: metrics.failureRate < 10, // Less than 10% failure rate
      status: metrics.failureRate < 10 ? 'HEALTHY' : 'DEGRADED',
      metrics,
      uptime: process.uptime(),
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Reset performance metrics
   */
  resetMetrics() {
    this.performanceMetrics = {
      totalRequests: 0,
      successfulRequests: 0,
      failedRequests: 0,
      averageResponseTime: 0
    };
  }

  /**
   * Get transformer metadata with advanced features
   * @returns {Object} Transformer information
   */
  getInfo() {
    return {
      name: 'mistral-transformer',
      version: '1.2.0',
      description: 'Mistral API transformer for Claude Code Router with comprehensive advanced features support',
      supportedModels: ['devstral-latest', 'mistral-large-latest'],
      features: [
        'tools', 'streaming', 'parameters', 'sse-parsing', 'incremental-content',
        'safe_prompt', 'random_seed', 'response_format', 'advanced-error-handling',
        'performance-monitoring', 'structured-logging', 'circuit-breaker', 'retry-policy'
      ],
      advancedParameters: [
        'safe_prompt', 'random_seed', 'response_format', 'tool_choice',
        'frequency_penalty', 'presence_penalty', 'temperature', 'top_p', 'max_tokens'
      ],
      configuration: this.getConfiguration(),
      performance: this.getPerformanceMetrics()
    };
  }

  /**
   * Validate transformer is properly configured
   * @returns {Promise<Object>} Validation result
   */
  async validate() {
    const validationResults = [];

    // Validate configuration
    if (this.maxTokens > 32000) {
      validationResults.push({ type: 'WARNING', message: 'maxTokens exceeds recommended limit' });
    }

    if (this.temperature < 0 || this.temperature > 2) {
      validationResults.push({ type: 'ERROR', message: 'temperature must be between 0 and 2' });
    }

    if (this.topP < 0 || this.topP > 1) {
      validationResults.push({ type: 'ERROR', message: 'topP must be between 0 and 1' });
    }

    // Validate performance metrics
    const metrics = this.getPerformanceMetrics();
    if (metrics.failureRate > 10) {
      validationResults.push({ type: 'WARNING', message: 'High failure rate detected' });
    }

    return {
      valid: validationResults.every(result => result.type !== 'ERROR'),
      validationResults,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Export transformer state for debugging
   * @returns {Object} Complete transformer state
   */
  exportState() {
    return {
      configuration: this.getConfiguration(),
      performance: this.getPerformanceMetrics(),
      options: { ...this.options },
      circuitBreaker: this._createCircuitBreaker().getStatus(),
      timestamp: new Date().toISOString(),
      transformerVersion: '1.2.0'
    };
  }
}