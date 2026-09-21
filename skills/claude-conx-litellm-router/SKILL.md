---
name: claude-conx-litellm-router
description: Use when you need to check the health/status of the LiteLLM model router and its configured providers. Trigger when the user asks to run the health check, verify API keys, diagnose routing issues, or check model availability.
---

# LiteLLM Health Check (ClaudeConX)

Use the `litellm-health-check.py` script to verify the LiteLLM model router status, configured providers, and model group availability.

## Overview

The `litellm-health-check.py` script is a diagnostic tool that checks:
- LiteLLM proxy connectivity (`http://127.0.0.1:5090`)
- Each configured provider's API key status
- Model group availability and routing configuration
- Fallback chain integrity

## When to Use

- After container startup to verify router is operational
- When model routing behaves unexpectedly
- Before starting work that depends on specific model capabilities
- To diagnose "no models available" or authentication errors
- After adding/updating API keys to confirm they're recognized

## Running the Health Check

```bash
python3 /workspace/litellm-health-check.py
```

### Sample Output

```
=== LiteLLM Router Health Check ===
Proxy URL: http://127.0.0.1:5090
Proxy Status: HEALTHY

=== Provider Status ===
✓ NVIDIA NIM (NIM_API_KEY) - CONFIGURED
  Models: deepseek-v4-pro, llama-3.1-405b, nemotron-3-ultra
  Groups: lite-llm/think, lite-llm/longContext

✓ Google AI Studio (GOOGLE_API_KEY) - CONFIGURED
  Models: gemini-3.5-flash, gemini-3.5-pro
  Groups: lite-llm/webSearch, lite-llm/image

✗ Mistral AI (MISTRAL_API_KEY) - NOT SET
  Groups: (unavailable)

✗ Cerebras (CEREBRAS_API_KEY) - NOT SET
  Groups: (unavailable)

✓ OpenCode Zen (OPENCODE_ZEN_API_KEY) - CONFIGURED
  Models: deepseek-v4-flash, deepseek-v4-pro
  Groups: lite-llm/default

✗ EXA AI (EXA_API_KEY) - NOT SET
  Groups: lite-llm/webSearch (fallback only)

=== Model Groups ===
✓ lite-llm/router      → Multi-stage pipeline (auto)
✓ lite-llm/default     → OpenCode Zen (DeepSeek v4 Flash)
✓ lite-llm/think       → NVIDIA NIM (DeepSeek v4 Pro)
✓ lite-llm/webSearch   → Google AI Studio (Gemini 3.5 Flash)
✓ lite-llm/image       → Google AI Studio (Gemini 3.5 Flash)
✓ lite-llm/longContext → NVIDIA NIM (DeepSeek v4 Pro)

=== Summary ===
Providers Configured: 3/6
Model Groups Available: 6/6
Router Status: OPERATIONAL
```

## Interpreting Results

| Status | Meaning | Action |
|--------|---------|--------|
| `HEALTHY` | Proxy responding normally | No action needed |
| `DEGRADED` | Proxy up but some providers missing | Check API keys for missing providers |
| `UNHEALTHY` | Proxy not responding | Check `systemctl status litellm`; review logs |
| `CONFIGURED` | Provider API key is set | Provider available for routing |
| `NOT SET` | Provider API key missing | Set environment variable to enable |
| `ERROR` | Provider configured but failing | Check API key validity; review provider dashboard |

## Common Issues and Solutions

| Issue | Diagnosis | Solution |
|-------|-----------|----------|
| Proxy not responding | Health check shows `UNHEALTHY` | Run `systemctl restart litellm`; check `journalctl -u litellm` |
| Models unavailable | Provider shows `NOT SET` | Set required API key environment variable; restart proxy |
| Auth failures | Provider shows `ERROR` | Verify API key format and permissions; check provider quota |
| Routing to wrong model | Groups misconfigured | Check `/etc/litellm/config.yaml` model group mappings |
| Rate limited | Provider shows `CONFIGURED` but requests fail | Fallback chains should activate; check provider rate limits |

## Environment Variables

The health check reads these environment variables to determine provider configuration:

| Variable | Provider | Required For |
|----------|----------|--------------|
| `NIM_API_KEY` | NVIDIA NIM | `lite-llm/think`, `lite-llm/longContext` |
| `GOOGLE_API_KEY` | Google AI Studio | `lite-llm/webSearch`, `lite-llm/image` |
| `MISTRAL_API_KEY` | Mistral AI | Custom model groups |
| `CEREBRAS_API_KEY` | Cerebras | Custom model groups |
| `OPENCODE_ZEN_API_KEY` | OpenCode Zen | `lite-llm/default` |
| `EXA_API_KEY` | EXA AI | Web search fallback |

**Note:** After setting environment variables, restart the LiteLLM proxy for changes to take effect:
```bash
systemctl restart litellm
```

## Cross-Harness Notes

- **Discovery:** This skill follows agentskills.io discovery paths. Install to `~/.agents/skills/` for cross-harness availability, or to `<project>/.<harness>/skills/` for harness-specific installation.
- **Auto-loading:** Some harnesses auto-load on keywords like "litellm", "health check", "model router", "diagnose"; others require explicit `skill` tool invocation.
- **Tool mapping:** Uses generic action language:
  - "run a shell command" → executes `python3 /workspace/litellm-health-check.py`
  - "read a file" → reads LiteLLM config (`/etc/litellm/config.yaml`), logs
  - "fetch a URL" → calls LiteLLM proxy REST API (`/health`, `/models`) for verification
- **No hardcoded harness list:** Works with ANY harness implementing agentskills.io spec.
- **Harness-specific caveats:**
  - The `litellm-health-check.py` script is a **container-internal diagnostic** — only works inside the ClaudeConX container
  - The LiteLLM proxy is a local HTTP service — harness-agnostic once running
  - Provider keys are set as environment variables in container; not harness-specific
  - All harnesses benefit from running the health check to verify router status