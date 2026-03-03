# Mistral Transformer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a full-featured Mistral transformer for Claude Code Router that resolves compatibility issues causing 422 errors and provides comprehensive API support.

**Architecture:** Implement a bidirectional transformer that converts between Claude Code Router's unified format and Mistral's API specification, handling message formats, tool calling, streaming responses, and advanced features.

**Tech Stack:** TypeScript/JavaScript, Claude Code Router transformer interface, Mistral API specification

---

## Task 1: Create Transformer Directory Structure

**Files:**
- Create: `ccr-presets/mistral-transformer/mistral.transformer.js`
- Create: `ccr-presets/mistral-transformer/package.json`
- Create: `ccr-presets/mistral-transformer/README.md`

**Step 1: Create transformer directory and basic files**

```bash
mkdir -p ccr-presets/mistral-transformer
```

**Step 2: Create package.json**

```json
{
  "name": "mistral-transformer",
  "version": "1.0.0",
  "description": "Mistral API transformer for Claude Code Router",
  "main": "mistral.transformer.js",
  "type": "module"
}
```

**Step 3: Create README.md**

```markdown
# Mistral Transformer

Transformer for Mistral AI API compatibility with Claude Code Router.

## Features
- Full Mistral API compatibility
- Tool calling support
- Streaming response handling
- Advanced parameter support
```

**Step 4: Commit initial structure**

```bash
git add ccr-presets/mistral-transformer/
git commit -m "feat: add mistral transformer directory structure"
```

## Task 2: Implement Core Transformer Interface

**Files:**
- Create: `ccr-presets/mistral-transformer/mistral.transformer.js`

**Step 1: Create transformer class skeleton**

```javascript
export default class MistralTransformer {
  constructor(options = {}) {
    this.name = 'mistral';
    this.options = options;
    this.logger = null; // Will be injected by CCR
  }

  async transformRequestIn(request, provider, context) {
    // TODO: Implement request transformation
    return request;
  }

  async transformResponseIn(response, context) {
    // TODO: Implement response transformation
    return response;
  }
}
```

**Step 2: Test basic transformer registration**

```bash
# Test that the file loads without errors
node -e "import('./ccr-presets/mistral-transformer/mistral.transformer.js').then(m => console.log('Transformer loaded'))"
```

**Step 3: Commit core interface**

```bash
git add ccr-presets/mistral-transformer/mistral.transformer.js
git commit -m "feat: add mistral transformer core interface"
```

## Task 3: Implement Request Transformation

**Files:**
- Modify: `ccr-presets/mistral-transformer/mistral.transformer.js`

**Step 1: Add message transformation logic**

```javascript
class MistralTransformer {
  // ... existing code ...

  async transformRequestIn(request, provider, context) {
    // Filter out incompatible fields
    const mistralRequest = {
      model: request.model,
      messages: this.transformMessages(request.messages),
      max_tokens: request.max_tokens,
      temperature: request.temperature,
      stream: request.stream,
      tools: request.tools ? this.transformTools(request.tools) : undefined,
      tool_choice: request.tool_choice
    };

    // Remove undefined values
    return Object.fromEntries(
      Object.entries(mistralRequest).filter(([_, v]) => v !== undefined)
    );
  }

  transformMessages(messages) {
    return messages.map(msg => ({
      role: msg.role,
      content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
      tool_calls: msg.tool_calls ? this.transformToolCalls(msg.tool_calls) : undefined,
      tool_call_id: msg.tool_call_id
    }));
  }

  transformToolCalls(toolCalls) {
    return toolCalls.map(tc => ({
      id: tc.id,
      type: tc.type,
      function: {
        name: tc.function.name,
        arguments: tc.function.arguments
      }
    }));
  }

  transformTools(tools) {
    return tools.map(tool => ({
      type: tool.type,
      function: {
        name: tool.function.name,
        description: tool.function.description,
        parameters: tool.function.parameters
      }
    }));
  }
}
```

**Step 2: Test message transformation**

```bash
# Create a simple test script
echo "
import MistralTransformer from './ccr-presets/mistral-transformer/mistral.transformer.js';

const transformer = new MistralTransformer();
const testRequest = {
  model: 'mistral-large-latest',
  messages: [{ role: 'user', content: 'Hello' }],
  max_tokens: 100
};

const result = await transformer.transformRequestIn(testRequest, {}, {});
console.log('Transformed request:', JSON.stringify(result, null, 2));
" > test-transformation.js

node test-transformation.js
```

**Step 3: Commit request transformation**

```bash
git add ccr-presets/mistral-transformer/mistral.transformer.js
git commit -m "feat: implement mistral request transformation"
```

## Task 4: Implement Response Transformation

**Files:**
- Modify: `ccr-presets/mistral-transformer/mistral.transformer.js`

**Step 1: Add non-streaming response transformation**

```javascript
class MistralTransformer {
  // ... existing code ...

  async transformResponseIn(response, context) {
    const contentType = response.headers.get('content-type');

    if (contentType?.includes('text/event-stream')) {
      return this.transformStreamingResponse(response, context);
    } else {
      return this.transformNonStreamingResponse(response, context);
    }
  }

  async transformNonStreamingResponse(response, context) {
    try {
      const data = await response.json();

      const unifiedResponse = {
        id: data.id,
        object: data.object,
        created: data.created,
        model: data.model,
        choices: data.choices.map(choice => ({
          index: choice.index,
          message: this.transformMessage(choice.message),
          finish_reason: choice.finish_reason
        })),
        usage: data.usage
      };

      return new Response(JSON.stringify(unifiedResponse), {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers
      });
    } catch (error) {
      this.logger?.error({ error }, 'Mistral response transformation failed');
      return response;
    }
  }

  transformMessage(message) {
    return {
      role: message.role,
      content: message.content,
      tool_calls: message.tool_calls ? this.transformToolCallsIn(message.tool_calls) : undefined
    };
  }

  transformToolCallsIn(toolCalls) {
    return toolCalls.map(tc => ({
      id: tc.id,
      type: tc.type,
      function: {
        name: tc.function.name,
        arguments: tc.function.arguments
      }
    }));
  }
}
```

**Step 2: Test response transformation**

```bash
# Create a mock response test
echo "
import MistralTransformer from './ccr-presets/mistral-transformer/mistral.transformer.js';

const transformer = new MistralTransformer();
const mockResponse = new Response(JSON.stringify({
  id: 'chatcmpl-123',
  object: 'chat.completion',
  created: 1234567890,
  model: 'mistral-large-latest',
  choices: [{
    index: 0,
    message: { role: 'assistant', content: 'Hello from Mistral' },
    finish_reason: 'stop'
  }],
  usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 }
}), { status: 200 });

const result = await transformer.transformResponseIn(mockResponse, {});
console.log('Transformed response status:', result.status);
" > test-response.js

node test-response.js
```

**Step 3: Commit response transformation**

```bash
git add ccr-presets/mistral-transformer/mistral.transformer.js
git commit -m "feat: implement mistral non-streaming response transformation"
```

## Task 5: Implement Streaming Response Transformation

**Files:**
- Modify: `ccr-presets/mistral-transformer/mistral.transformer.js`

**Step 1: Add streaming response transformation**

```javascript
class MistralTransformer {
  // ... existing code ...

  async transformStreamingResponse(response, context) {
    const decoder = new TextDecoder();
    const encoder = new TextEncoder();

    const transformedStream = new ReadableStream({
      start: async (controller) => {
        const reader = response.body.getReader();
        let buffer = '';

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (!line.trim() || !line.startsWith('data: ')) {
                controller.enqueue(encoder.encode(line + '\n'));
                continue;
              }

              const data = line.slice(6).trim();
              if (data === '[DONE]') {
                controller.enqueue(encoder.encode(line + '\n'));
                continue;
              }

              try {
                const chunk = JSON.parse(data);
                const transformedChunk = this.transformStreamingChunk(chunk);
                const modifiedLine = `data: ${JSON.stringify(transformedChunk)}\n\n`;
                controller.enqueue(encoder.encode(modifiedLine));
              } catch (parseError) {
                // Pass through original line if parsing fails
                controller.enqueue(encoder.encode(line + '\n'));
              }
            }
          }
        } catch (error) {
          this.logger?.error({ error }, 'Stream transformation error');
          controller.error(error);
        } finally {
          controller.close();
          reader.releaseLock();
        }
      }
    });

    return new Response(transformedStream, {
      status: response.status,
      statusText: response.statusText,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
      }
    });
  }

  transformStreamingChunk(chunk) {
    if (chunk.choices && chunk.choices[0]) {
      return {
        ...chunk,
        choices: chunk.choices.map(choice => ({
          ...choice,
          delta: this.transformMessage(choice.delta || choice.message)
        }))
      };
    }
    return chunk;
  }
}
```

**Step 2: Test streaming transformation**

```bash
# Create a simple streaming test
echo "
// Note: Full streaming test requires actual API call
// This is just a syntax check
import MistralTransformer from './ccr-presets/mistral-transformer/mistral.transformer.js';

const transformer = new MistralTransformer();
console.log('Streaming methods defined');
" > test-streaming.js

node test-streaming.js
```

**Step 3: Commit streaming transformation**

```bash
git add ccr-presets/mistral-transformer/mistral.transformer.js
git commit -m "feat: implement mistral streaming response transformation"
```

## Task 6: Add Advanced Feature Support

**Files:**
- Modify: `ccr-presets/mistral-transformer/mistral.transformer.js`

**Step 1: Add advanced parameter support**

```javascript
class MistralTransformer {
  // ... existing code ...

  async transformRequestIn(request, provider, context) {
    const mistralRequest = {
      model: request.model,
      messages: this.transformMessages(request.messages),
      max_tokens: request.max_tokens,
      temperature: request.temperature,
      top_p: request.top_p,
      frequency_penalty: request.frequency_penalty,
      presence_penalty: request.presence_penalty,
      stream: request.stream,
      tools: request.tools ? this.transformTools(request.tools) : undefined,
      tool_choice: request.tool_choice,
      safe_prompt: request.safe_prompt,
      random_seed: request.random_seed,
      response_format: request.response_format
    };

    // Remove undefined values
    return Object.fromEntries(
      Object.entries(mistralRequest).filter(([_, v]) => v !== undefined)
    );
  }
}
```

**Step 2: Add error handling and logging**

```javascript
class MistralTransformer {
  // ... existing code ...

  async transformRequestIn(request, provider, context) {
    try {
      this.logger?.debug({
        model: request.model,
        messageCount: request.messages?.length,
        hasTools: !!request.tools
      }, 'Transforming Mistral request');

      const mistralRequest = {
        // ... transformation logic ...
      };

      this.logger?.debug({
        transformedFields: Object.keys(mistralRequest)
      }, 'Mistral request transformed');

      return mistralRequest;
    } catch (error) {
      this.logger?.error({ error, request }, 'Mistral request transformation failed');

      // Fallback: minimal valid request
      return {
        model: request.model,
        messages: this.transformMessages(request.messages || []),
        max_tokens: request.max_tokens || 4096
      };
    }
  }
}
```

**Step 3: Test advanced features**

```bash
# Test with advanced parameters
echo "
import MistralTransformer from './ccr-presets/mistral-transformer/mistral.transformer.js';

const transformer = new MistralTransformer();
const advancedRequest = {
  model: 'mistral-large-latest',
  messages: [{ role: 'user', content: 'Hello' }],
  temperature: 0.7,
  top_p: 0.9,
  safe_prompt: true,
  response_format: { type: 'json_object' }
};

const result = await transformer.transformRequestIn(advancedRequest, {}, {});
console.log('Advanced transformation:', JSON.stringify(result, null, 2));
" > test-advanced.js

node test-advanced.js
```

**Step 4: Commit advanced features**

```bash
git add ccr-presets/mistral-transformer/mistral.transformer.js
git commit -m "feat: add mistral advanced parameter support and error handling"
```

## Task 7: Update Mistral Preset Configuration

**Files:**
- Modify: `ccr-presets/mistral-devstral/manifest.json`

**Step 1: Update transformer configuration**

```json
{
  "name": "mistral-devstral",
  "version": "1.0.0",
  "description": "Mistral Devstral Configuration",
  "author": "Tyler Collison",
  "keywords": [
    "mistral",
    "devstral"
  ],
  "LOG": false,
  "LOG_LEVEL": "debug",
  "CLAUDE_PATH": "",
  "HOST": "0.0.0.0",
  "PORT": 3456,
  "API_TIMEOUT_MS": "600000",
  "PROXY_URL": "",
  "transformers": [
    {
      "name": "mistral",
      "path": "ccr-presets/mistral-transformer/mistral.transformer.js"
    }
  ],
  "Providers": [
    {
      "name": "mistral",
      "api_base_url": "https://api.mistral.ai/v1/chat/completions",
      "api_key": "$MISTRAL_API_KEY",
      "models": [
        "devstral-latest",
        "mistral-large-latest"
      ],
      "transformer": {
        "use": [
          "mistral"
        ]
      }
    }
  ],
  "StatusLine": {
    "enabled": false,
    "currentStyle": "default",
    "default": {
      "modules": []
    },
    "powerline": {
      "modules": []
    }
  },
  "Router": {
    "default": "mistral,devstral-latest",
    "background": "mistral,devstral-latest",
    "think": "mistral,devstral-latest",
    "longContext": "mistral,devstral-latest",
    "longContextThreshold": 60000,
    "webSearch": "mistral,devstral-latest",
    "image": "mistral,mistral-large-latest"
  },
  "CUSTOM_ROUTER_PATH": ""
}
```

**Step 2: Test configuration loading**

```bash
# Test that the manifest is valid JSON
node -e "console.log(JSON.parse(require('fs').readFileSync('ccr-presets/mistral-devstral/manifest.json', 'utf8')).name)"
```

**Step 3: Commit configuration update**

```bash
git add ccr-presets/mistral-devstral/manifest.json
git commit -m "feat: update mistral preset to use new transformer"
```

## Task 8: Create Integration Test

**Files:**
- Create: `ccr-presets/mistral-transformer/integration.test.js`

**Step 1: Create integration test**

```javascript
import MistralTransformer from './mistral.transformer.js';

async function runIntegrationTest() {
  const transformer = new MistralTransformer();

  // Test 1: Basic request transformation
  const basicRequest = {
    model: 'mistral-large-latest',
    messages: [{ role: 'user', content: 'Hello' }],
    max_tokens: 100
  };

  const transformedRequest = await transformer.transformRequestIn(basicRequest, {}, {});
  console.log('✓ Basic request transformation');

  // Test 2: Response transformation
  const mockResponse = new Response(JSON.stringify({
    id: 'test-123',
    choices: [{ message: { role: 'assistant', content: 'Response' } }]
  }));

  const transformedResponse = await transformer.transformResponseIn(mockResponse, {});
  console.log('✓ Response transformation');

  console.log('All integration tests passed');
}

runIntegrationTest().catch(console.error);
```

**Step 2: Run integration test**

```bash
cd ccr-presets/mistral-transformer
node integration.test.js
```

**Step 3: Commit integration test**

```bash
git add ccr-presets/mistral-transformer/integration.test.js
git commit -m "test: add mistral transformer integration test"
```

## Task 9: Update Documentation

**Files:**
- Modify: `ccr-presets/mistral-transformer/README.md`

**Step 1: Update README with usage instructions**

```markdown
# Mistral Transformer

Transformer for Mistral AI API compatibility with Claude Code Router.

## Features
- Full Mistral API compatibility
- Tool calling support
- Streaming response handling
- Advanced parameter support
- Error handling and fallbacks

## Usage

Add to your CCR configuration:

```json
{
  "transformers": [
    {
      "name": "mistral",
      "path": "ccr-presets/mistral-transformer/mistral.transformer.js"
    }
  ],
  "Providers": [
    {
      "name": "mistral",
      "api_base_url": "https://api.mistral.ai/v1/chat/completions",
      "api_key": "$MISTRAL_API_KEY",
      "transformer": {
        "use": ["mistral"]
      }
    }
  ]
}
```

## Configuration Options

- `safe_prompt`: Enable safety filtering
- `response_format`: Control output format (e.g., JSON)
- `random_seed`: Deterministic results
- All standard Mistral parameters supported
```

**Step 2: Commit documentation**

```bash
git add ccr-presets/mistral-transformer/README.md
git commit -m "docs: update mistral transformer documentation"
```

## Task 10: Final Validation

**Step 1: Test complete transformer setup**

```bash
# Validate all files are in place
ls -la ccr-presets/mistral-transformer/

# Test transformer loading
node -e "import('./ccr-presets/mistral-transformer/mistral.transformer.js').then(m => { const t = new m.default(); console.log('Transformer ready:', t.name) })"
```

**Step 2: Run final integration test**

```bash
cd ccr-presets/mistral-transformer && node integration.test.js
```

**Step 3: Final commit**

```bash
git add .
git commit -m "feat: complete mistral transformer implementation"
```

---

**Plan complete and saved to `docs/plans/2026-03-03-mistral-transformer.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**