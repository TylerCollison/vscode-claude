# Mistral Transformer

A transformer configuration for Claude Code Router to handle Mistral API compatibility issues.

## Purpose

This transformer resolves 422 errors that occur when Claude Code Router sends requests to Mistral API endpoints due to format incompatibility.

## Features

- Transforms Claude Code Router request format to Mistral API format
- Maps Claude-specific parameters to Mistral equivalents
- Handles streaming responses properly
- Supports multiple Mistral models (large, small, codestral)

## Configuration

Set the `MISTRAL_API_KEY` environment variable:

```bash
export MISTRAL_API_KEY="your-api-key-here"
```

## Usage

This transformer is automatically applied when using the Mistral provider configuration.

## Models Supported

- `mistral-large-latest` - Latest large model for general use
- `mistral-small-latest` - Smaller, faster model for background tasks
- `codestral-latest` - Specialized model for coding tasks