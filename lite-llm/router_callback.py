"""
LiteLLM Proxy Custom Callback: Tool-Aware Router

Three-stage routing pipeline implemented as a LiteLLM pre-call hook:

  1. Image content detected         → lite-llm/image
  2. LLM is equipped with a web-    → lite-llm/webSearch
     search tool (matches LiteLLM's
     websearch_interception logic)
  3. All other                      → lite-llm/complexity
                                      (gemini embedding semantic router)

Stage 2 delegates to LiteLLM's own ``is_web_search_tool()`` so that the
routing callback and the ``websearch_interception`` callback use *exactly*
the same criteria to decide whether a tool is a search tool.  This keeps
the two layers in sync: a request is routed to the webSearch model group
iff the ``websearch_interception`` callback would actually intercept it.
"""

from litellm.integrations.custom_logger import CustomLogger
from litellm.integrations.websearch_interception import is_web_search_tool
from litellm.proxy.proxy_server import UserAPIKeyAuth, DualCache
from typing import Literal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _contains_images(messages: list) -> bool:
    """Return True if any message contains image data."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            if "data:image/" in content:
                return True
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                part_type = part.get("type", "")
                if part_type in ("image_url", "image"):
                    return True
    return False


def _has_search_tool(data: dict) -> bool:
    """Return True when *data* contains at least one web-search tool.

    Uses the exact same detection logic as LiteLLM's built-in
    ``websearch_interception`` callback (``is_web_search_tool``).
    Supports all formats — Anthropic native (``web_search_*`` types),
    Claude Code (``web_search``), OpenAI ``tools``, and legacy
    ``functions``.
    """
    for tool in data.get("tools") or data.get("functions") or []:
        if isinstance(tool, dict) and is_web_search_tool(tool):
            return True
    return False


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class MultiStageRouter(CustomLogger):
    """
    Routes incoming requests:

      1. Image data present         → lite-llm/image
      2. Web-search tool present    → lite-llm/webSearch
         (using LiteLLM's detection)
      3. All other                  → lite-llm/complexity
                                       (handles complexity routing natively)
    """

    def __init__(self):
        pass

    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: DualCache,
        data: dict,
        call_type: Literal[
            "completion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
            "anthropic_messages",
        ],
    ) -> dict:
        # Both the /v1/chat/completions (call_type="completion") and
        # /v1/messages / Anthropic passthrough (call_type="anthropic_messages")
        # paths should go through the routing pipeline.
        if call_type not in ("completion", "anthropic_messages"):
            return data

        original_model = data.get("model", "")
        if original_model not in ("lite-llm/router", ""):
            return data

        messages = data.get("messages", [])

        # Stage 1: Image content detection
        if _contains_images(messages):
            data["model"] = "lite-llm/image"
            return data

        # Stage 2: Web-search tool present → route to webSearch model
        if _has_search_tool(data):
            data["model"] = "lite-llm/webSearch"
            return data

        # Stage 3: Delegate to semantic router for complexity routing
        data["model"] = "lite-llm/complexity"
        return data


# Singleton instance referenced from lite-llm-default.yaml
router_handler = MultiStageRouter()
