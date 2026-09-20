---
name: claude-conx-litellm-router
description: Use when you need to configure, use, or troubleshoot the LiteLLM model router in the ClaudeConX container. Trigger when the user asks about model routing, API key configuration, model selection, or LiteLLM proxy settings.
---

# LiteLLM Router (ClaudeConX)

Configure and use the LiteLLM model router for multi-provider model access with automatic routing, fallbacks, and content-aware model selection.

## Overview

The LiteLLM router runs as a local proxy at `http://127.0.0.1:5090` inside the ClaudeConX container. All Claude Code requests are automatically routed through this proxy, which selects the best model based on:

- Request content (images → vision model, web search → search-capable model)
- Task complexity (simple → fast model, complex → reasoning model)
- Provider availability and rate limits
- Configured fallback chains

## Model Groups

| Model Group | Purpose | Default Provider |
|-------------|---------|------------------|
| `lite-llm/router` | Main entry point — multi-stage routing pipeline | Auto-routed |
| `lite-llm/default` | Standard chat and coding tasks | OpenCode Zen (DeepSeek v4 Flash) |
| `lite-llm/think` | Complex reasoning and deep analysis | NVIDIA NIM (DeepSeek v4 Pro) |
| `lite-llm/webSearch` | Queries requiring web search | Google AI Studio (Gemini 3.5 Flash) |
| `lite-llm/image` | Image analysis and vision tasks | Google AI Studio (Gemini 3.5 Flash) |
| `lite-llm/longContext` | Long-context tasks (>100k tokens) | NVIDIA NIM (DeepSeek v4 Pro) |

## Configuration

### API Keys (Environment Variables)

Set these to enable providers:

| Variable | Provider | Enables |
|----------|----------|---------|
| `NIM_API_KEY` | NVIDIA NIM | DeepSeek v4 Pro, Llama 3.1, Nemotron |
| `GOOGLE_API_KEY` | Google AI Studio | Gemini 3.5 Flash/Pro, Vision |
| `MISTRAL_API_KEY` | Mistral AI | Mistral Large, Codestral |
| `CEREBRAS_API_KEY` | Cerebras | Llama 3.1 on Cerebras wafer-scale |
| `OPENCODE_ZEN_API_KEY` | OpenCode Zen | DeepSeek v4 Flash/Pro |
| `EXA_API_KEY` | EXA AI | Web search capability |

### Claude Code Integration

Claude Code is pre-configured to use the LiteLLM proxy:

```bash
# Internal proxy URL (automatically set)
ANTHROPIC_BASE_URL=http://127.0.0.1:5090
ANTHROPIC_API_KEY=litellm  # Dummy key for proxy auth
```

Model names in Claude Code map to router groups:
- `sonnet` → `lite-llm/default`
- `opus` → `lite-llm/think`
- `haiku` → `lite-llm/default` (fast tier)

## Usage

### Check Router Status

```bash
# Health check
curl http://127.0.0.1:5090/health

# List models
curl http://127.0.0.1:5090/models
```

### View Routing Logs

```bash
# Container logs
docker logs <container> | grep litellm

# Or inside container
journalctl -u litellm -f
```

### Override Model for Specific Request

In Claude Code, use model aliases:
- `claude-3-5-sonnet` → routes to `lite-llm/default`
- `claude-3-opus` → routes to `lite-llm/think`

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No models available | Check API keys are set; verify `litellm-health-check.py` passes |
| Routing to wrong model | Check request content; verify model group mappings |
| Rate limited | Fallback chains should activate; check provider quotas |
| Proxy not responding | Restart: `systemctl restart litellm` (inside container) |
| Auth errors | Verify API key format; check provider dashboard |

## Health Check Script

```bash
python3 /workspace/litellm-health-check.py
```

Outputs status of each provider and model group.

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load on keywords like "litellm", "model router", "model routing", "API keys"; others require explicit `skill` tool invocation.
- **Tool mapping:** Uses generic action language:
  - "run a shell command" → executes `curl`, `litellm-health-check.py`, environment variable checks
  - "read a file" → reads LiteLLM config (`/etc/litellm/config.yaml`), logs
  - "write a file" → updates config, sets environment variables
  - "fetch a URL" → calls LiteLLM proxy REST API (`/health`, `/models`, `/chat/completions`)
- **No hardcoded harness list:** Works with ANY harness implementing agentskills.io spec.
- **Harness-specific caveats:**
  - **Claude Code:** Pre-configured to use proxy automatically; model names map to router groups
  - **Codex/OpenCode:** Must configure `OPENAI_BASE_URL=http://127.0.0.1:5090` and `OPENAI_API_KEY=litellm` manually
  - **All harnesses:** The proxy is a local HTTP service — harness-agnostic once configured
  - **Provider keys:** Set as environment variables in container; not harness-specific