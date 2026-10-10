"""
LiteLLM Proxy Custom Callback: OpenCode Identity Headers

OpenCode Zen (https://opencode.ai/zen/v1) only serves its free models to
the OpenCode harness: requests that don't carry OpenCode's client-identity
headers are rejected.  This callback stamps that header set onto outgoing
requests so Zen models can be used through the proxy.

The header set mirrors what the opencode CLI itself sends for its own
provider (opencode source: packages/opencode/src/session/llm/request.ts):

  x-opencode-session: session ID
  x-opencode-request: user ID
  x-opencode-client:  which opencode front-end ("cli")
  x-opencode-project: project/workspace ID
  User-Agent:         opencode/<version>

The proxy's real clients are Claude Code and other harnesses, so these are
synthetic identity values.  Each is env-configurable with a sensible
fallback (see the helpers below); by default the session identity is stable
for the lifetime of the proxy process and the request identity rotates per
call.

Set OPENCODE_HEADERS_MODEL_PREFIXES to a comma-separated list of model-name
prefixes to restrict injection to those model groups (e.g. the Zen
deployments); by default headers are added to every routed request.
"""

import os
import socket
import uuid

from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy.proxy_server import UserAPIKeyAuth, DualCache
from typing import Literal


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

DEFAULT_USER_AGENT = "opencode/1.18.35"
DEFAULT_CLIENT = "cli"

# Stable session identity for this proxy process (env override still wins).
_PROCESS_SESSION_ID = str(uuid.uuid4())


def _session_id() -> str:
    return os.environ.get("OPENCODE_SESSION_ID") or _PROCESS_SESSION_ID


def _request_id(user_api_key_dict: UserAPIKeyAuth | None) -> str:
    """The user ID when the virtual key carries one, else a per-call UUID."""
    user_id = getattr(user_api_key_dict, "user_id", None)
    return user_id or str(uuid.uuid4())


def _client() -> str:
    return os.environ.get("OPENCODE_CLIENT") or DEFAULT_CLIENT


def _project_id() -> str:
    return os.environ.get("OPENCODE_PROJECT_ID") or socket.gethostname() or "workspace"


def _user_agent() -> str:
    return os.environ.get("OPENCODE_USER_AGENT") or DEFAULT_USER_AGENT


def _scope_prefixes() -> tuple:
    """Model-name prefixes to scope injection to; empty means all requests."""
    raw = os.environ.get("OPENCODE_HEADERS_MODEL_PREFIXES", "")
    return tuple(prefix.strip() for prefix in raw.split(",") if prefix.strip())


# ---------------------------------------------------------------------------
# Callback
# ---------------------------------------------------------------------------

class OpenCodeHeaders(CustomLogger):
    """Adds the OpenCode client-identity headers to outgoing requests."""

    def __init__(self):
        pass

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict,
        call_type: Literal[
            "completion",
            "acompletion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
            "anthropic_messages",
        ],
    ) -> dict:
        # Only the chat paths carry harness identity; embeddings etc. don't.
        # The proxy delivers "acompletion" for /chat/completions and
        # "anthropic_messages" for the /v1/messages passthrough (verified
        # against litellm 1.102.1); "completion" is the sync spelling.
        if call_type not in ("completion", "acompletion", "anthropic_messages"):
            return data

        prefixes = _scope_prefixes()
        if prefixes and not data.get("model", "").startswith(prefixes):
            return data

        headers = {
            "x-opencode-session": _session_id(),
            "x-opencode-request": _request_id(user_api_key_dict),
            "x-opencode-client": _client(),
            "x-opencode-project": _project_id(),
            "User-Agent": _user_agent(),
        }

        # Key-merge so caller-supplied headers survive; ours win on collision
        # (request-level extra_headers replaces a deployment's wholesale, so
        # the callback must be the single source of these headers).
        merged = data["extra_headers"].copy() if isinstance(data.get("extra_headers"), dict) else {}
        merged.update(headers)
        data["extra_headers"] = merged
        return data


# Singleton instance referenced from lite-llm-default.yaml
opencode_headers_handler = OpenCodeHeaders()
