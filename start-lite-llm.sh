#!/usr/bin/with-contenv bash

export GOOGLE_API_KEY="${GOOGLE_API_KEY:-dummy-key}"
export CEREBRAS_API_KEY="${CEREBRAS_API_KEY:-dummy-key}"
export NIM_API_KEY="${NIM_API_KEY:-dummy-key}"
export OPENCODE_ZEN_API_KEY="${OPENCODE_ZEN_API_KEY:-dummy-key}"
export MISTRAL_API_KEY="${MISTRAL_API_KEY:-dummy-key}"

# Config directory baked into the image (holds the YAML configs and the
# callback modules they import). Overridable so the config resolution below
# can be exercised outside the container.
LITE_LLM_DIR="${LITE_LLM_DIR:-/lite-llm}"

cd "$LITE_LLM_DIR"

# Model picker mode: MODEL_PICKER_ENABLED selects lite-llm-picker.yaml (the
# hand-maintained picker fork); the static default config is used otherwise.
LITELLM_CONFIG="$LITE_LLM_DIR/lite-llm-default.yaml"
case "${MODEL_PICKER_ENABLED:-}" in
  true|TRUE|True|1|yes|YES|Yes|on|ON)
    LITELLM_CONFIG="$LITE_LLM_DIR/lite-llm-picker.yaml"
    ;;
esac

# A user-supplied config wins over the baked-in one. LITELLM_CONFIG_PATH is the
# path (inside the container) of a mounted file - or of a file inside a mounted
# folder - to serve instead. The proxy still starts from $LITE_LLM_DIR, so the
# callback modules the configs import (router_callback, model_picker_plugin)
# stay resolvable; mounting over $LITE_LLM_DIR itself would hide them.
if [[ -n "${LITELLM_CONFIG_PATH:-}" ]]; then
  if [[ -f "${LITELLM_CONFIG_PATH}" ]]; then
    LITELLM_CONFIG="${LITELLM_CONFIG_PATH}"
  else
    echo "WARNING: LITELLM_CONFIG_PATH=${LITELLM_CONFIG_PATH} is not a file - using ${LITELLM_CONFIG} instead" >&2
  fi
fi

echo "Starting LiteLLM proxy with config ${LITELLM_CONFIG}"

if [[ "${LOGGING:-}" == "verbose" ]]; then
  litellm --host 127.0.0.1 --port 5090 --config "$LITELLM_CONFIG" &
else
  litellm --host 127.0.0.1 --port 5090 --config "$LITELLM_CONFIG" >>/tmp/litellm.log 2>&1 &
fi