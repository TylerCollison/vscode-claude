#!/usr/bin/with-contenv bash

export GOOGLE_API_KEY="${GOOGLE_API_KEY:-dummy-key}"
export CEREBRAS_API_KEY="${CEREBRAS_API_KEY:-dummy-key}"
export NIM_API_KEY="${NIM_API_KEY:-dummy-key}"
export OPENCODE_ZEN_API_KEY="${OPENCODE_ZEN_API_KEY:-dummy-key}"
export MISTRAL_API_KEY="${MISTRAL_API_KEY:-dummy-key}"

cd /lite-llm

# Model picker mode: MODEL_PICKER_ENABLED selects lite-llm-picker.yaml (the
# hand-maintained picker fork); the static default config is used otherwise.
LITELLM_CONFIG="/lite-llm/lite-llm-default.yaml"
case "${MODEL_PICKER_ENABLED:-}" in
  true|TRUE|True|1|yes|YES|Yes|on|ON)
    LITELLM_CONFIG="/lite-llm/lite-llm-picker.yaml"
    ;;
esac

if [[ "${LOGGING:-}" == "verbose" ]]; then
  litellm --host 127.0.0.1 --port 5090 --config "$LITELLM_CONFIG" &
else
  litellm --host 127.0.0.1 --port 5090 --config "$LITELLM_CONFIG" >>/tmp/litellm.log 2>&1 &
fi