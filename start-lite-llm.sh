#!/usr/bin/with-contenv bash

export GOOGLE_API_KEY="${GOOGLE_API_KEY:-dummy-key}"
export CEREBRAS_API_KEY="${CEREBRAS_API_KEY:-dummy-key}"
export NIM_API_KEY="${NIM_API_KEY:-dummy-key}"
export OPENCODE_ZEN_API_KEY="${OPENCODE_ZEN_API_KEY:-dummy-key}"
export MISTRAL_API_KEY="${MISTRAL_API_KEY:-dummy-key}"

cd /lite-llm
if [[ "${LOGGING:-}" == "verbose" ]]; then
  litellm --host 127.0.0.1 --port 5090 --config /lite-llm/lite-llm-default.yaml &
else
  litellm --host 127.0.0.1 --port 5090 --config /lite-llm/lite-llm-default.yaml >/dev/null 2>&1 &
fi