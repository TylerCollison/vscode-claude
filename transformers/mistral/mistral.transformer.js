// Mistral Transformer for Claude Code Router
// Transforms unified Claude Code Router requests to Mistral API format

export default class MistralTransformer {
  constructor(options = {}, logger = console) {
    this.options = options;
    this.logger = logger;

    // Configure transformer options
    this.maxTokens = options.maxTokens || 4096;
    this.temperature = options.temperature || 0.7;
    this.topP = options.topP || 1.0;

    this.logger.debug('MistralTransformer initialized', { options });
  }

  /**
   * Transform unified Claude Code Router request to Mistral API format
   * @param {Object} request - Unified request object
   * @param {string} provider - Provider configuration
   * @param {Object} context - Context information
   * @returns {Object} Transformed Mistral API request
   */
  transformRequestIn(request, provider, context) {
    try {
      this.logger.debug('Transforming request to Mistral format', {
        request: JSON.stringify(request, null, 2),
        provider
      });

      // Validate input request structure
      this._validateRequest(request);

      // Create base Mistral request with validated fields only
      const mistralRequest = {
        model: this._getValidatedModel(request, provider),
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

      this.logger.debug('Transformed Mistral request', mistralRequest);
      return mistralRequest;
    } catch (error) {
      this.logger.error('Request transformation failed', {
        error: error.message,
        requestId: request.id,
        stack: error.stack
      });
      throw error;
    }
  }

  /**
   * Transform Mistral API response to unified Claude Code Router format
   * @param {Object} response - Mistral API response
   * @param {Object} context - Context information
   * @returns {Object} Transformed unified response
   */
  transformResponseIn(response, context) {
    this.logger.debug('Transforming Mistral response to unified format', {
      response: JSON.stringify(response, null, 2)
    });

    if (!response || typeof response !== 'object') {
      throw new Error('Invalid Mistral response format');
    }

    const unifiedResponse = {
      id: response.id || `mistral-${Date.now()}`,
      object: 'chat.completion',
      created: response.created || Math.floor(Date.now() / 1000),
      model: response.model || 'unknown',
      usage: this._transformUsage(response.usage),
      choices: this._transformChoices(response.choices)
    };

    this.logger.debug('Transformed unified response', unifiedResponse);
    return unifiedResponse;
  }

  /**
   * Get appropriate Mistral model based on request and provider
   * @private
   */
  _getMistralModel(request, provider) {
    // Use specified model or fallback to provider default
    const model = request.model ||
                  (provider.models && provider.models[0]) ||
                  'devstral-latest';

    return model;
  }

  /**
   * Get validated Mistral model with safety checks
   * @private
   */
  _getValidatedModel(request, provider) {
    const model = this._getMistralModel(request, provider);

    // Validate model name format
    if (!model || typeof model !== 'string') {
      throw new Error('Invalid model parameter: must be a non-empty string');
    }

    // Basic validation for model names
    if (!/^[a-zA-Z0-9-_]+$/.test(model)) {
      throw new Error(`Invalid model name format: ${model}`);
    }

    return model;
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

      if (message.content === undefined || (typeof message.content !== 'string' && message.content !== null)) {
        throw new Error(`Invalid message content at index ${index}: must be string or null`);
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

    // Add Mistral-supported optional parameters
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
          content: message.content !== undefined && message.content !== null ? String(message.content) : ''
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
    if (!usage) {
      return {
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0
      };
    }

    return {
      prompt_tokens: usage.prompt_tokens || 0,
      completion_tokens: usage.completion_tokens || 0,
      total_tokens: usage.total_tokens || 0
    };
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

    return choices.map((choice, index) => ({
      index: choice.index || index,
      message: {
        role: choice.message?.role || 'assistant',
        content: choice.message?.content || '',
        tool_calls: choice.message?.tool_calls
      },
      finish_reason: choice.finish_reason || 'stop'
    }));
  }

  /**
   * Health check for the transformer
   * @returns {Promise<boolean>} True if transformer is healthy
   */
  async healthCheck() {
    // Simple health check - transformer is always healthy
    // Could be extended to test API connectivity if needed
    return true;
  }

  /**
   * Get transformer metadata
   * @returns {Object} Transformer information
   */
  getInfo() {
    return {
      name: 'mistral-transformer',
      version: '1.0.0',
      description: 'Mistral API transformer for Claude Code Router',
      supportedModels: ['devstral-latest', 'mistral-large-latest'],
      features: ['tools', 'streaming', 'parameters']
    };
  }
}