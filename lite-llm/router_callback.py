"""
LiteLLM Proxy Custom Callback: Content-Aware Router (image detection only)

Stage-1 of the lite-llm/router pipeline: detect image data and route to
lite-llm/image.  All non-image requests are forwarded to
lite-llm/semantic-router, which handles stages 2 and 3 natively.
"""

from litellm.integrations.custom_logger import CustomLogger
from litellm.proxy.proxy_server import UserAPIKeyAuth, DualCache
from typing import Literal


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


class MultiStageRouter(CustomLogger):
    """
    Routes incoming requests:

      1. Image data present  → lite-llm/image
      2. All other           → lite-llm/semantic-router
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
        ],
    ) -> dict:
        if call_type != "completion":
            return data

        original_model = data.get("model", "")
        if original_model not in ("lite-llm/router", ""):
            return data

        messages = data.get("messages", [])

        # Stage 1: Image content detection
        if _contains_images(messages):
            data["model"] = "lite-llm/image"
            return data

        # Stage 2-3: Delegate to LiteLLM's semantic router, which checks
        # web search utterances and falls back to the complexity router.
        data["model"] = "lite-llm/semantic-router"
        return data


# Singleton instance referenced from lite-llm-default.yaml
router_handler = MultiStageRouter()