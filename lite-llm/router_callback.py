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


# Instruction injected into every picker-routed request, telling the model
# the agent loop's actual turn rule: a response with no tool call ends the
# turn. Claude Code's own system prompt never states this, so a model that
# narrates its plan in prose (instead of emitting the calls) stalls the
# turn. This states the rule up front, in addition to the client's system
# prompt — it never replaces it.
_TOOL_CALL_INSTRUCTION = (
    "Include at least one tool call in every response while you still have "
    "work to do. A response with no tool call ends your turn, so only respond "
    "with text alone when your task is complete."
)
_TOOL_CALL_INSTRUCTION_MARKER = "A response with no tool call ends your turn"


def _content_text(content) -> str:
    """Plain text of a message/system content, str or block list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return ""


def _instruction_present(data: dict) -> bool:
    """True when the tool-call instruction is already in this request."""
    system = data.get("system")
    if system is not None and _TOOL_CALL_INSTRUCTION_MARKER in _content_text(system):
        return True
    for msg in data.get("messages", []) or []:
        if isinstance(msg, dict) and _TOOL_CALL_INSTRUCTION_MARKER in _content_text(msg.get("content", "")):
            return True
    return False


def _inject_tool_call_instruction(data: dict) -> None:
    """Add the tool-call instruction to the request, once, at the start.

    Anthropic-shaped requests carry the system prompt top-level (``system``);
    OpenAI-shaped requests carry it as the leading system-role message(s).
    The instruction goes after the client's system prompt, never replacing
    it. Idempotent: a request that already carries the instruction is left
    alone (the hook can run again on a retried request).
    """
    if _instruction_present(data):
        return
    system = data.get("system")
    if system is not None:
        if isinstance(system, str):
            data["system"] = system + "\n\n" + _TOOL_CALL_INSTRUCTION
        elif isinstance(system, list):
            data["system"] = list(system) + [{"type": "text", "text": _TOOL_CALL_INSTRUCTION}]
        return
    messages = data.get("messages")
    if not isinstance(messages, list):
        return
    insert_at = 0
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "system":
            insert_at += 1
        else:
            break
    messages.insert(insert_at, {"role": "system", "content": _TOOL_CALL_INSTRUCTION})


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
            "acompletion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
            "anthropic_messages",
        ],
    ) -> dict:
        # All three proxy surfaces must go through the routing pipeline:
        #   - /v1/chat/completions passes call_type="acompletion" (litellm
        #     >=1.104 passes the route_type verbatim; older releases passed
        #     "completion" — keep accepting both)
        #   - /v1/responses and other passthroughs are unaffected
        #   - /v1/messages Anthropic passthrough passes "anthropic_messages"
        if call_type not in ("completion", "acompletion", "anthropic_messages"):
            return data

        original_model = data.get("model", "")
        if original_model not in ("lite-llm/router", ""):
            return data

        messages = data.get("messages", [])

        # Tell the model the loop's turn rule up front, before routing.
        _inject_tool_call_instruction(data)

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
