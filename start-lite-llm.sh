#!/usr/bin/with-contenv bash

cd /lite-llm
if [[ "${LOGGING:-}" == "verbose" ]]; then
  litellm --host 127.0.0.1 --port 5090 --config /lite-llm/lite-llm-default.yaml &
else
  litellm --host 127.0.0.1 --port 5090 --config /lite-llm/lite-llm-default.yaml >/dev/null 2>&1 &
fi