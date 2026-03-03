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
    this.logger.debug('Transforming request to Mistral format', {
      request: JSON.stringify(request, null, 2),
      provider
    });

    const mistralRequest = {
      model: this._getMistralModel(request, provider),
      messages: this._transformMessages(request.messages),
      temperature: request.temperature || this.temperature,
      top_p: request.topP || this.topP,
      max_tokens: request.maxTokens || this.maxTokens,
      stream: request.stream || false
    };

    // Add optional parameters if present
    if (request.stop) mistralRequest.stop = request.stop;
    if (request.frequency_penalty !== undefined) mistralRequest.frequency_penalty = request.frequency_penalty;
    if (request.presence_penalty !== undefined) mistralRequest.presence_penalty = request.presence_penalty;

    // Handle tool calls if present
    if (request.tools && request.tools.length > 0) {
      mistralRequest.tools = this._transformTools(request.tools);
    }

    this.logger.debug('Transformed Mistral request', mistralRequest);
    return mistralRequest;
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
   * Transform unified messages to Mistral message format
   * @private
   */
  _transformMessages(messages) {
    if (!Array.isArray(messages)) {
      return [];
    }

    return messages.map(message => {
      const mistralMessage = {
        role: this._mapRole(message.role),
        content: message.content || ''
      };

      // Handle tool calls in messages
      if (message.tool_calls) {
        mistralMessage.tool_calls = message.tool_calls.map(toolCall => ({
          id: toolCall.id,
          type: 'function',
          function: {
            name: toolCall.function.name,
            arguments: typeof toolCall.function.arguments === 'string'
              ? toolCall.function.arguments
              : JSON.stringify(toolCall.function.arguments)
          }
        }));
      }

      // Handle tool results
      if (message.tool_call_id) {
        mistralMessage.tool_call_id = message.tool_call_id;
      }

      return mistralMessage;
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
    return tools.map(tool => ({
      type: 'function',
      function: {
        name: tool.function.name,
        description: tool.function.description || '',
        parameters: tool.function.parameters || {}
      }
    }));
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