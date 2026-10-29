"""
Model Picker: litellm complexity-router routing plugin + passive stats logger
+ soft-failure interception.

Wired from lite-llm-picker.yaml:

    complexity_router_config:
      plugins: ["model_picker_plugin.picker"]
    litellm_settings:
      callbacks: [..., "model_picker_plugin.stats_logger"]

The plugin runs AFTER the complexity router's tier classification (it is the
sanctioned downstream hook: ComplexityRouter._pick_model_for_tier runs
complexity_router_config.plugins against the chosen tier's pool and routes to
the surviving value with no pool validation). It narrows the pool to the single
best model per the tier rubric and may return a dynamic
``pollinations/<catalog-id>`` name served by the ``pollinations/*`` wildcard
model_list entry, or any existing static group name.

The stats_logger callback additionally INTERCEPTS soft failures: pollinations
serves hard errors (account credit gate, relayed upstream errors) as HTTP 200
with the error text as assistant message content, which litellm treats as a
success — no retry, no fallback. On the streaming path the iterator hook drops
the failed stream before the error chunk is yielded and retries through the
routing pipeline with failed models excluded — continuing until a model
succeeds or every candidate has been tried (bounded by the pool size, with a
repeat-detector for pool exhaustion) — then synthesizes the winning answer
into the same SSE stream; the non-streaming path swaps the response wholesale.
The user never sees provider error content.

Mid-stream upstream failures — dropped connections, stream timeouts, and the
in-band error events litellm's Anthropic adapter converts them into — get the
same treatment in both phases: the failed model is recorded (demoted) and the
request retries with a different model, the retry's answer continuing the same
SSE stream after any partial content already delivered. A truncated answer is
never allowed to end the turn as though it were complete.

Retries re-enter the routing pipeline through the entry point matching the
request's shape: /v1/messages bodies stay anthropic-shaped (top-level
``system``, ``tool_use``/``tool_result`` content blocks) all the way to the
post-call hooks, so they must go back through the router's anthropic_messages
entry — handing them to acompletion ships anthropic blocks to OpenAI-format
providers and 400s every candidate on a payload the provider never saw fit to
accept.

Thinking-only responses — a completed response whose message is thinking
(or redacted thinking) with no actionable text or tool block, on a
turn-ending stop reason — get the same retry-with-exclusion, and ONLY then:
the check runs on the completed response, never mid-stream, and never when
text or tool calls give the turn something to continue from. Thinking-only
failures record ERROR, not SOFT, because they are prompt-class-dependent
(the same model answers plain prompts) and must not fire the instant
demotion proof; the per-request exclusion is what unblocks the turn.

litellm's ``get_instance_fn`` exec's this file with spec_from_file_location
WITHOUT registering it in sys.modules, so a plain ``import model_picker``
would not resolve, and this file being referenced from both the plugins list
and the callbacks list would otherwise produce two independent module copies.
The _load_sibling guard registers the sibling once under a fixed sys.modules
key so the catalog cache and rolling stats are shared by every instance.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import logging
import os
import sys
from datetime import datetime

import litellm
from litellm.integrations.custom_logger import CustomLogger
from litellm.types.router import RoutingContext

logger = logging.getLogger("model_picker")

# litellm's root logging config leaves third-party loggers at WARNING, which
# would hide the per-request pick lines operators need to see routing decisions.
# Attach our own handler, level-tunable via MODEL_PICKER_LOG_LEVEL.
if not logger.handlers and os.environ.get("MODEL_PICKER_LOG_LEVEL", "INFO").upper() != "NONE":
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(os.environ.get("MODEL_PICKER_LOG_LEVEL", "INFO").upper())

_HERE = os.path.dirname(os.path.abspath(__file__))

# Observability key written into the (copied) request metadata. Actual retry
# exclusion state lives in the shared PriorPickRegistry, keyed by litellm_call_id.
_PICKS_METADATA_KEY = "model_picker_picks"


def _load_sibling(name: str):
    """Load a config-adjacent module once, registered in sys.modules."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(_HERE, f"{name}.py"))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load sibling module {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


model_picker = _load_sibling("model_picker")


# ---------------------------------------------------------------------------
# Legacy max_tokens for OpenAI-compatible providers
# ---------------------------------------------------------------------------

# Every `openai/`-prefixed deployment in this proxy is an OpenAI-COMPATIBLE
# third party (pollinations, llm7) — none is actual OpenAI. litellm
# renames max_tokens -> max_completion_tokens for gpt-named models (an OpenAI
# API requirement), and pollinations' credit gate treats that parameter name
# punitively (gated at any value, even 1, while the legacy max_tokens passes).
# Restore the legacy name on the wire: for these providers it is the safe,
# universally-supported form.
def _preserve_legacy_max_tokens() -> None:
    try:
        from litellm.llms.openai.chat.gpt_5_transformation import OpenAIGPT5Config

        original = OpenAIGPT5Config.map_openai_params

        def map_openai_params(self, non_default_params, optional_params, model, drop_params):
            params = original(self, non_default_params, optional_params, model, drop_params)
            if isinstance(params, dict) and "max_completion_tokens" in params and "max_tokens" not in params:
                params["max_tokens"] = params.pop("max_completion_tokens")
            return params

        OpenAIGPT5Config.map_openai_params = map_openai_params
        logger.debug("model_picker: legacy max_tokens preservation installed for OpenAIGPT5Config")
    except Exception as e:  # noqa: BLE001 — a patch failure must not break the proxy
        logger.warning("model_picker: could not install legacy max_tokens preservation (%s)", e)


# Catalog-discovered models are absent from litellm's static model map
# (model_prices_and_context_window.json): litellm only knows the models the
# world submitted PRs for. Routing paths that need a routed model's context
# window (the router's pre-call checks, the complexity router's context
# compaction) go through Router.get_router_model_info, which RAISES
# ModelNotMappedError for anything unmapped — 500-ing every request that
# lands on a discovered candidate. Fall back to what the picker already
# knows: the catalog's published context window (enriched from modelgrep
# when the provider publishes none), then the deployment's own model_info,
# then a default. The default must comfortably exceed client output
# allowances (Claude Code sends max_tokens=32000): the compaction budget is
# int(window*0.9) - output, and a window at or below the allowance leaves no
# budget and 400s the request before it reaches the provider.
_FALLBACK_MAX_INPUT_TOKENS = 131072
_FALLBACK_MAX_OUTPUT_TOKENS = 8192


def _unmapped_model_info_fallback(deployment, manager=None, resolved_name=None) -> dict:
    """Model info for a catalog-discovered model absent from litellm's map."""
    info: dict = {}
    candidate = None
    lookup_names = []
    if resolved_name:
        lookup_names.append(str(resolved_name))
    if isinstance(deployment, dict) and deployment.get("model_name"):
        lookup_names.append(str(deployment["model_name"]))
    for name in lookup_names:
        if "*" in name:
            continue  # the wildcard literal never matches a candidate
        try:
            mgr = manager or model_picker.get_shared_manager()
            candidate = mgr.peek_candidate(name)
        except Exception:  # noqa: BLE001 — the fallback must never fail
            candidate = None
        if candidate is not None:
            break
    if isinstance(deployment, dict):
        user_info = deployment.get("model_info") or {}
        if isinstance(user_info, dict):
            info.update({k: v for k, v in user_info.items() if v is not None})
    if candidate is not None and candidate.context_length:
        max_input = max(1024, candidate.context_length - _FALLBACK_MAX_OUTPUT_TOKENS)
    else:
        max_input = info.get("max_input_tokens") or _FALLBACK_MAX_INPUT_TOKENS
    info.setdefault("max_input_tokens", max_input)
    info.setdefault("max_output_tokens", _FALLBACK_MAX_OUTPUT_TOKENS)
    info.setdefault("max_tokens", _FALLBACK_MAX_OUTPUT_TOKENS)
    if candidate is not None:
        info.setdefault("litellm_provider", candidate.provider)
    return info


def _fallback_model_info_for_unmapped_models() -> None:
    try:
        from litellm.router import Router as _Router

        original = _Router.get_router_model_info

        def get_router_model_info(self, deployment, received_model_name=None, *args, **kwargs):
            try:
                return original(self, deployment, received_model_name, *args, **kwargs)
            except Exception as e:
                if "isn't mapped" not in str(e) and "ModelNotMapped" not in type(e).__name__:
                    raise
                # the deployment's model_name is the wildcard literal; the
                # received name is the resolved candidate
                name = received_model_name or (
                    deployment.get("model_name") if isinstance(deployment, dict) else deployment
                )
                logger.info("model_picker: unmapped-model fallback info for %s", name)
                info = _unmapped_model_info_fallback(deployment, resolved_name=name)
                if isinstance(name, str) and name:
                    info.setdefault("key", name)
                return info

        get_router_model_info._model_picker_patch = True  # marker for tests/introspection
        _Router.get_router_model_info = get_router_model_info
        logger.debug("model_picker: unmapped-model info fallback installed")
    except Exception as e:  # noqa: BLE001 — a patch failure must not break the proxy
        logger.warning("model_picker: could not install unmapped-model info fallback (%s)", e)


# Catalog-driven pools inevitably contain listed-but-dead models (a NIM model
# 404s while still appearing in its catalog) and models whose real windows
# cannot serve a request. litellm refuses to retry NotFoundError
# unconditionally, and refuses ContextWindowExceededError unless
# context_window_fallbacks are configured — either way the request would die
# on the first bad candidate. The picker's exclusion walk is exactly the
# right handler for both: record the failure, exclude the model, try the next
# candidate (a larger-context one, once real windows are enriched).
def _retry_not_found_errors() -> None:
    try:
        import litellm as _litellm

        router_cls = _litellm.router.Router
        original = router_cls.should_retry_this_error

        def should_retry_this_error(self, error, *args, **kwargs):
            try:
                return original(self, error, *args, **kwargs)
            except _litellm.NotFoundError:
                logger.info("model_picker: NotFoundError made retryable for the exclusion walk")
                return True
            except _litellm.ContextWindowExceededError:
                logger.info("model_picker: ContextWindowExceededError made retryable for the exclusion walk")
                return True

        router_cls.should_retry_this_error = should_retry_this_error
        logger.debug("model_picker: NotFoundError/ContextWindow retry patch installed")
    except Exception as e:  # noqa: BLE001 — a patch failure must not break the proxy
        logger.warning("model_picker: could not install NotFoundError retry patch (%s)", e)


_preserve_legacy_max_tokens()
_retry_not_found_errors()
_fallback_model_info_for_unmapped_models()

# ---------------------------------------------------------------------------
# Tier detection
# ---------------------------------------------------------------------------

_TIER_BY_POOL = {
    frozenset({"lite-llm/default"}): model_picker.TIER_DEFAULT,
    # COMPLEX (think) uses the default rubric: health floor, then top-N%
    # healthiest, then most capable. Only REASONING (ultra-think) keeps
    # the capability-first rubric.
    frozenset({"lite-llm/think"}): model_picker.TIER_DEFAULT,
    frozenset({"lite-llm/ultra-think"}): model_picker.TIER_THINK,
}


def detect_tier(candidate_models: list[str]) -> str | None:
    """Map the complexity router's tier pool onto a picker rubric.

    The pool is the tier's configured model group(s), possibly intersected with
    a context-fit filter. Anything unrecognized passes through untouched.
    The think pool maps to the default rubric; only ultra-think maps to the
    capability-first rubric.
    """
    return _TIER_BY_POOL.get(frozenset(candidate_models or []))


# ---------------------------------------------------------------------------
# Routing plugin
# ---------------------------------------------------------------------------


class ModelPickerPlugin:
    """Narrows the complexity router's tier pool to the single best model."""

    def __init__(self, manager=None, stats=None, config=None, prior_picks=None) -> None:
        self._manager = manager
        self._stats = stats
        self._config = config
        self._prior_picks = prior_picks

    @property
    def manager(self):
        if self._manager is None:
            self._manager = model_picker.get_shared_manager()
        return self._manager

    @property
    def stats(self):
        if self._stats is None:
            self._stats = model_picker.get_shared_stats()
        return self._stats

    @property
    def config(self):
        if self._config is None:
            self._config = model_picker.PickerConfig()
        return self._config

    @property
    def prior_picks(self):
        if self._prior_picks is None:
            self._prior_picks = model_picker.get_shared_prior_picks()
        return self._prior_picks

    async def run(self, context: RoutingContext) -> RoutingContext:
        """RoutingPlugin entry point. Never breaks routing on internal errors."""
        if not model_picker.picker_enabled():
            return context
        try:
            return await self.run_and_apply(context)
        except Exception as e:  # noqa: BLE001 — a picker failure must never fail the request
            logger.warning("model_picker: plugin error (%s); passing tier pool through", e)
            return context

    async def run_and_apply(self, context: RoutingContext) -> RoutingContext:
        tier = detect_tier(context.candidate_models)
        if tier is None:
            return context
        # The tier pool itself, for the pick log: think requests now log as
        # tier=default (they use the default rubric), so the pool is what
        # tells them apart from default requests.
        pool = list(context.candidate_models or [])

        # context.metadata is a pydantic COPY of the request metadata — safe to
        # read (litellm stamps attempted_retries into the real dict before the
        # copy), but writes through it never reach the request. Pick history
        # therefore lives in the call-scoped PriorPickRegistry, keyed by the
        # litellm_call_id that every proxy request carries. The soft-failure
        # retry hook additionally passes an explicit model_picker_exclude list
        # through the request metadata for models this request already saw
        # fail.
        metadata = context.metadata if context.metadata else {}
        call_id = str(metadata.get("litellm_call_id") or "")
        if not call_id:
            # litellm does not surface litellm_call_id to routing plugins, so
            # key the per-request pick history on the conversation itself —
            # the router's in-request retries replay the same messages, which
            # makes this stable across attempts (and unique enough per
            # request that identical concurrent retries sharing a history is
            # benign: they would hit the same broken models anyway).
            call_id = "conv-" + hashlib.sha1(
                json.dumps(context.structured_messages, sort_keys=True, default=str).encode()
            ).hexdigest()
        prior_picks = list(self.prior_picks.get(call_id))
        for extra in metadata.get("model_picker_exclude") or []:
            if extra not in prior_picks:
                prior_picks.append(str(extra))

        estimate = model_picker.estimate_tokens(context.structured_messages)
        snapshot = await self.manager.get_snapshot()
        ranked = model_picker.rank_candidates(
            snapshot.candidates,
            tier,
            self.stats,
            self.config,
            estimate=estimate,
            exclude=frozenset(prior_picks),
        )
        if not ranked:
            logger.info("model_picker: no eligible candidates; passing tier pool through")
            return context

        pick = ranked[0].candidate
        logger.info(
            "model_picker: tier=%s pool=%s estimate=%dtok pick=%s (score=%.3f ctx=%s provider=%s free=%s bench=%s stale=%s attempt_excluded=%s)",
            tier,
            pool,
            estimate,
            pick.name,
            ranked[0].health_score,
            pick.context_length or "?",
            pick.provider,
            pick.free,
            f"{pick.benchmark_score:.2f}" if pick.benchmarked else "-",
            snapshot.stale,
            prior_picks,
        )
        if call_id:
            self.prior_picks.add(call_id, pick.name)
        # Observability only (this dict is a pydantic copy; litellm ignores it).
        metadata[_PICKS_METADATA_KEY] = prior_picks + [pick.name]
        metadata["model_picker_decision"] = {
            "tier": tier,
            "estimate_tokens": estimate,
            "score": ranked[0].health_score,
            "free": pick.free,
            "stale_snapshot": snapshot.stale,
        }
        context.candidate_models = [pick.name]
        return context


# ---------------------------------------------------------------------------
# Passive stats logger
# ---------------------------------------------------------------------------


def _resolve_group_name(kwargs: dict) -> str:
    """Model group a success/failure event belongs to.

    The router stamps ``deployment_model_name`` (the group) into the request
    metadata; fall back to the standard model_group/model fields. A wildcard
    deployment name (``nvidia_nim/*``) is NOT a model — recording stats
    under it orphans them, because no candidate is ever named that (this
    is how NIM failures in production never demoted the picked model).
    Wildcard names are skipped here so callers fall through to a resolved
    name, or to "" when none is available.
    """
    values: list[str] = []
    for holder in (kwargs.get("litellm_metadata"), kwargs.get("metadata"), kwargs.get("litellm_params")):
        if isinstance(holder, dict):
            for key in ("deployment_model_name", "model_group"):
                value = holder.get(key)
                if value:
                    values.append(str(value))
    for key in ("model_group", "model"):
        value = kwargs.get(key)
        if value:
            values.append(str(value))
    for value in values:
        if "*" not in value:
            return value
    return ""


def _event_ttft_seconds(kwargs: dict, start_time: datetime) -> float | None:
    """TTFT for streaming successes; None for non-streaming calls."""
    completion_start = kwargs.get("completion_start_time")
    if isinstance(completion_start, datetime):
        return (completion_start - start_time).total_seconds()
    return None


# ---------------------------------------------------------------------------
# Soft-failure retry (the user must never see a provider error as chat content)
# ---------------------------------------------------------------------------

# Pollinations serves hard failures as HTTP 200 with the error text as the
# assistant message — litellm sees a SUCCESS: no router retry, no fallback, no
# attempt exclusion. The hooks below intercept at the proxy boundary: clean
# chunks pass through untouched (true streaming), and when the error text
# appears, the failed stream is dropped and the request is retried (bounded)
# through the full routing pipeline with the failed models excluded. The
# client only ever receives the retry's answer, synthesized into the same
# SSE stream.

# The retry walk has NO attempt cap: it continues until a model succeeds or
# the picker runs out of distinct candidates. Termination is guaranteed by
# bounding the walk at the candidate-pool size (plus attribution slack) and by
# a repeat-detector — when the picker re-offers an already-failed model, the
# pool is exhausted.
_RETRY_WALK_SLACK = 4
_RETRY_WALK_SAFETY_CAP = 256

# Request fields copied into the non-streaming retry. The anthropic-only
# fields matter on the /v1/messages route: ``system`` is top-level there (not
# a message), and dropping it silently stripped the system prompt from every
# retry; ``stop_sequences``/``thinking`` are anthropic's spellings.
_RETRY_PASSTHROUGH_KEYS = (
    "model",
    "messages",
    "system",
    "max_tokens",
    "metadata",
    "temperature",
    "top_p",
    "top_k",
    "stop",
    "stop_sequences",
    "thinking",
    "tools",
    "tool_choice",
    "response_format",
    "seed",
    "stream_timeout",
    "timeout",
    "num_retries",
    "litellm_metadata",
    "proxy_server_request",
)

# Content block types that exist ONLY in anthropic message bodies. OpenAI
# content parts use different names (image_url, input_audio, ...), so any of
# these marks a request acompletion cannot carry to an OpenAI-format provider.
_ANTHROPIC_BLOCK_TYPES = (
    "tool_result",
    "tool_use",
    "thinking",
    "redacted_thinking",
    "document",
    "image",
    "search_result",
    "server_tool_use",
    "web_search_tool_result",
)

# OpenAI finish_reason -> anthropic stop_reason (unknown maps to end_turn).
_STOP_REASON_MAP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "tool_calls": "tool_use",
    "function_call": "tool_use",
    "end_turn": "end_turn",
    "max_tokens": "max_tokens",
    "stop_sequence": "stop_sequence",
    "tool_use": "tool_use",
}


def _is_anthropic_request(request_data: object) -> bool:
    """True when a request body is anthropic-shaped (the /v1/messages route).

    The tells are unambiguous: a top-level ``system`` field (OpenAI chat
    carries the system prompt as a message), anthropic-exclusive content
    block types, or anthropic tool definitions (``input_schema``). Text-only
    requests are valid in both formats and stay on the openai entry, where
    acompletion already handles them.
    """
    if not isinstance(request_data, dict):
        return False
    if request_data.get("system") is not None:
        return True
    tools = request_data.get("tools")
    if isinstance(tools, list) and any(isinstance(t, dict) and "input_schema" in t for t in tools):
        return True
    messages = request_data.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") in _ANTHROPIC_BLOCK_TYPES:
                    return True
    return False

_FALLBACK_REPLY = (
    "[model_picker] every available model was tried for this request without success "
    "({tried} attempts, last failure: {reason}); please retry in a moment."
)


def _delta_text_of(event: dict) -> str:
    if event.get("type") != "content_block_delta":
        return ""
    delta = event.get("delta") or {}
    if not isinstance(delta, dict):
        return ""
    return str(delta.get("text") or delta.get("thinking") or "")


def _chunk_events(chunk: object) -> list[dict]:
    """Anthropic events carried by one streamed chunk.

    Chunks arrive either as event dicts (agentic/fake-stream paths) or as
    already-encoded SSE frames — strings/bytes holding `event:`/`data:` lines
    (the /v1/messages streaming path). Normalize both to event dicts.
    """
    if isinstance(chunk, (bytes, bytearray)):
        chunk = chunk.decode("utf-8", errors="ignore")
    if isinstance(chunk, dict):
        return [chunk]
    if isinstance(chunk, str):
        events: list[dict] = []
        for line in chunk.splitlines():
            stripped = line.strip()
            if not stripped.startswith("data:"):
                continue
            payload = stripped[len("data:"):].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except Exception:  # noqa: BLE001 — never break the stream on a parse miss
                continue
            if isinstance(event, dict):
                events.append(event)
        return events
    # Non-dict objects (defensive): reuse the response-text extractor.
    text = model_picker.extract_response_text(chunk)
    return [{"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}}] if text else []


def _event_text(chunk: object) -> str:
    """Assistant text carried by one streamed chunk (any shape)."""
    return "".join(_delta_text_of(e) for e in _chunk_events(chunk))


def _is_in_band_error(chunk: object) -> bool:
    """Detect provider/litellm errors smuggled INTO the stream as events.

    litellm's Anthropic adapter converts mid-stream exceptions (ReadTimeouts
    raised as MidStreamFallbackError) into in-band anthropic `error` events
    and completes the stream normally — no exception ever reaches the hook's
    iterator. OpenAI-compatible streams do the same with top-level `error`
    objects. Such chunks must never reach the client.
    """
    if isinstance(chunk, dict):
        if chunk.get("type") == "error" or isinstance(chunk.get("error"), dict):
            return True
        return any(e.get("type") == "error" or isinstance(e.get("error"), dict) for e in _chunk_events(chunk))
    if isinstance(chunk, (str, bytes, bytearray)):
        for event in _chunk_events(chunk):
            if event.get("type") == "error" or isinstance(event.get("error"), dict):
                return True
        # raw error frames the JSON parser could not complete (truncated streams)
        if isinstance(chunk, str):
            return '"type": "error"' in chunk or '"type":"error"' in chunk
        return b'"type": "error"' in chunk or b'"type":"error"' in chunk
    # ModelResponseStream-shaped objects: OpenAI-style top-level error objects
    error = getattr(chunk, "error", None)
    if isinstance(error, dict):
        return True
    return False


def _sse_frame(event: dict) -> str:
    """Encode an anthropic event dict as an SSE frame matching the stream."""
    return f"event: {event.get('type', '')}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"


def _usage_dict(response_obj: object) -> dict:
    """input/output token counts from a retry response's usage, any shape.

    OpenAI responses carry usage.prompt_tokens/completion_tokens attributes;
    anthropic responses are dicts with input_tokens/output_tokens keys.
    """
    usage = getattr(response_obj, "usage", None)
    if usage is None and isinstance(response_obj, dict):
        usage = response_obj.get("usage")
    out: dict = {}
    if isinstance(usage, dict):
        prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
        completion = usage.get("completion_tokens", usage.get("output_tokens"))
    else:
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
    if isinstance(prompt, (int, float)) and not isinstance(prompt, bool):
        out["input_tokens"] = int(prompt)
    if isinstance(completion, (int, float)) and not isinstance(completion, bool):
        out["output_tokens"] = int(completion)
    return out


def _finish_reason(response_obj: object, has_tool_uses: bool = False) -> str:
    """anthropic stop_reason for the synthesized message_delta.

    OpenAI finish_reasons are mapped into anthropic vocabulary — the client
    parses an anthropic stream, where 'stop' is as foreign as 'end_turn' is
    to an OpenAI client. A tool-call finish only survives the mapping when
    tool_use blocks were actually synthesized.
    """
    try:
        if isinstance(response_obj, dict):
            reason = response_obj.get("stop_reason")
        else:
            reason = response_obj.choices[0].finish_reason  # type: ignore[index,union-attr]
    except Exception:  # noqa: BLE001 — synthesis must never fail the request
        reason = None
    mapped = _STOP_REASON_MAP.get(str(reason or ""), "end_turn")
    if mapped == "tool_use" and not has_tool_uses:
        return "end_turn"  # never claim tool_use without the blocks to back it
    return mapped


def _response_tool_uses(response_obj: object) -> list[dict]:
    """anthropic tool_use blocks from a retry response, any shape.

    Anthropic responses carry tool_use content blocks directly; OpenAI
    responses carry tool_calls whose function arguments arrive as a JSON
    string. Returns [{"id", "name", "input"}] for stream synthesis.
    """
    out: list[dict] = []
    try:
        if isinstance(response_obj, dict):
            content = response_obj.get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    out.append(
                        {
                            "id": str(block.get("id") or ""),
                            "name": str(block.get("name") or ""),
                            "input": block.get("input") if isinstance(block.get("input"), dict) else {},
                        }
                    )
        else:
            for choice in getattr(response_obj, "choices", None) or []:
                message = getattr(choice, "message", None)
                for call in getattr(message, "tool_calls", None) or []:
                    function = getattr(call, "function", None)
                    name = str(getattr(function, "name", "") or "") if function is not None else ""
                    if not name:
                        continue
                    try:
                        arguments = json.loads(getattr(function, "arguments", None) or "{}")
                    except Exception:  # noqa: BLE001 — malformed arguments must not break synthesis
                        arguments = {}
                    out.append(
                        {
                            "id": str(getattr(call, "id", "") or ""),
                            "name": name,
                            "input": arguments if isinstance(arguments, dict) else {},
                        }
                    )
    except Exception:  # noqa: BLE001 — synthesis must never fail the request
        return []
    return [tool_use for tool_use in out if tool_use["name"]]


def _response_model_name(response_obj: object) -> str:
    """A retry response's model name, attribute- or dict-shaped."""
    model = getattr(response_obj, "model", None)
    if model is None and isinstance(response_obj, dict):
        model = response_obj.get("model")
    return str(model) if model else ""


# Turn-ending stop reasons: the agent loop terminates the turn on these
# when the message carries nothing to execute and nothing to show.
# tool_use/pause_turn name a continuation, and refusal is a policy outcome,
# not a model failure — none of those may trigger a thinking-only retry.
_TURN_ENDING_STOP_REASONS = frozenset({"end_turn", "max_tokens", "stop_sequence"})


def _block_type(block: object) -> str:
    if isinstance(block, dict):
        return str(block.get("type") or "")
    return str(getattr(block, "type", "") or "")


def _block_text(block: object) -> str:
    if isinstance(block, dict):
        text = block.get("text")
        return text if isinstance(text, str) else ""
    text = getattr(block, "text", None)
    return text if isinstance(text, str) else ""


def _anthropic_blocks_thinking_only(blocks: object) -> bool:
    """Shape rule for an anthropic content list: at least one thinking or
    redacted_thinking block, and nothing else but whitespace-only text.

    A thinking block plus an empty text block (what the bridge emits for a
    reasoning-only upstream response with empty content) is still
    thinking-only: the empty text gives the turn nothing to show. Any
    other block type (tool_use, server_tool_use, ...) means the turn
    continues from that block, so it breaks thinking-only.
    """
    if not isinstance(blocks, (list, tuple)) or not blocks:
        return False
    saw_thinking = False
    for block in blocks:
        btype = _block_type(block)
        if btype in ("thinking", "redacted_thinking"):
            saw_thinking = True
        elif btype == "text":
            if _block_text(block).strip():
                return False
        else:
            return False
    return saw_thinking


def _openai_message_thinking_only(message: object) -> bool:
    """Shape rule for one OpenAI chat message (dict or object).

    Reasoning present (reasoning_content or thinking_blocks), content
    absent/blank, and no tool calls: the model thought and then stopped
    without answering or acting.
    """
    if isinstance(message, dict):
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        thinking_blocks = message.get("thinking_blocks")
        content = message.get("content")
        tool_calls = message.get("tool_calls")
    else:
        reasoning = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)
        thinking_blocks = getattr(message, "thinking_blocks", None)
        content = getattr(message, "content", None)
        tool_calls = getattr(message, "tool_calls", None)
    has_reasoning = bool(isinstance(reasoning, str) and reasoning.strip()) or bool(thinking_blocks)
    if not has_reasoning or tool_calls:
        return False
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        for part in content:
            if isinstance(part, str):
                if part.strip():
                    return False
            elif isinstance(part, dict):
                if isinstance(part.get("text"), str) and part["text"].strip():
                    return False
                if part.get("type") not in ("text", None):
                    return False
        return True
    return content is None


def _response_is_thinking_only(response_obj: object) -> bool:
    """True when a COMPLETED response is thinking-only on a turn-ending
    stop reason — the message the agent loop would terminate on with
    nothing to show and nothing to execute.

    This is deliberately a completed-response check only: it must never
    run on a partial stream (thinking deltas precede text in every normal
    reasoning response). The streaming hook evaluates it once, after the
    stream ends; the non-streaming hook evaluates the whole response.

    "The turn would have stopped" is operationalized as: the finished
    message gives the loop nothing to execute (no tool_use or server-tool
    block) and nothing to show (no non-blank text), on a stop reason that
    terminates the turn. A missing reason counts as turn-ending (a stream
    that ends without message_delta, or a response carrying no reason,
    still ends the turn). Unrecognized shapes fail closed (False): a
    response the detector cannot classify is never retried on this rule.
    """
    try:
        if isinstance(response_obj, dict):
            content = response_obj.get("content")
            if isinstance(content, list):
                stop = response_obj.get("stop_reason")
                if stop is not None and str(stop) not in _TURN_ENDING_STOP_REASONS:
                    return False
                return _anthropic_blocks_thinking_only(content)
            choices = response_obj.get("choices") or []
            if choices and isinstance(choices[0], dict):
                choice = choices[0]
                message = choice.get("message") or choice.get("delta") or {}
                mapped = _STOP_REASON_MAP.get(str(choice.get("finish_reason") or ""), "end_turn")
                if mapped not in _TURN_ENDING_STOP_REASONS:
                    return False
                return _openai_message_thinking_only(message)
            return False
        choices = getattr(response_obj, "choices", None) or []
        if choices:
            choice = choices[0]
            message = getattr(choice, "message", None) or getattr(choice, "delta", None)
            mapped = _STOP_REASON_MAP.get(str(getattr(choice, "finish_reason", None) or ""), "end_turn")
            if mapped not in _TURN_ENDING_STOP_REASONS:
                return False
            return _openai_message_thinking_only(message)
        return False
    except Exception:  # noqa: BLE001 — classification must never fail the request
        return False


def _classify_stream_event(event: dict) -> tuple[bool, bool]:
    """(thinking, actionable) flags contributed by one anthropic stream event.

    thinking: a thinking/redacted_thinking block started, or a thinking_delta.
    actionable: a non-whitespace text_delta, a tool_use/server_tool_use block
    started, or tool input streaming (input_json_delta) — anything the agent
    loop would continue the turn from. Anything else contributes neither.
    """
    if not isinstance(event, dict):
        return False, False
    etype = event.get("type")
    if etype == "content_block_start":
        block = event.get("content_block") or {}
        btype = _block_type(block)
        if btype in ("thinking", "redacted_thinking"):
            return True, False
        if btype in ("tool_use", "server_tool_use"):
            return False, True
        return False, False
    if etype == "content_block_delta":
        delta = event.get("delta") or {}
        if not isinstance(delta, dict):
            return False, False
        dtype = delta.get("type")
        if dtype == "thinking_delta" or ("thinking" in delta and dtype != "text_delta"):
            return True, False
        if dtype == "text_delta":
            return False, bool(str(delta.get("text") or "").strip())
        if dtype == "input_json_delta":
            return False, True
        if "text" in delta:
            return False, bool(str(delta.get("text") or "").strip())
        return False, False
    return False, False


class ModelPickerStatsLogger(CustomLogger):
    """Records per-group success/failure/TTFT observations for the picker."""

    def __init__(self, stats=None, manager=None, prior_picks=None) -> None:
        self._stats = stats
        self._manager = manager
        self._prior_picks = prior_picks

    @property
    def stats(self):
        if self._stats is None:
            self._stats = model_picker.get_shared_stats()
        return self._stats

    @property
    def manager(self):
        if self._manager is None:
            self._manager = model_picker.get_shared_manager()
        return self._manager

    @property
    def prior_picks(self):
        if self._prior_picks is None:
            self._prior_picks = model_picker.get_shared_prior_picks()
        return self._prior_picks

    def _event_group(self, kwargs: dict) -> str:
        """Group name for an event, aligned with the picker's candidate names.

        litellm stamps pattern-resolved wildcard deployments (model_name
        ``pollinations/*``) WITHOUT the group prefix — a pick the picker tracks
        as ``pollinations/community/x`` records its health under
        ``community/x``, so the picker's per-candidate lookups never match.
        Re-prefix from the cached catalog snapshot when unambiguous.

        Two attribution rules that fix production misattribution (#2):

        * The picker's own pick record (PriorPickRegistry, keyed by
          litellm_call_id when the event carries one) is authoritative and
          wins over any stamped name — it is the only channel that knows
          which provider a pick came from.
        * A bare id shared by several providers (e.g. ``z-ai/glm-5.3``
          exists under both ``pollinations/`` and ``nvidia_nim/``) is
          ambiguous and must NOT be guessed into ``pollinations/<id>``.
          Guessing is how NIM failures demoted the pollinations twin while
          the NIM model itself stayed "untried". Ambiguous bare ids return
          "" (unattributable: the caller records nothing rather than
          polluting a sibling's stats). A wildcard name likewise returns "".
        """
        if isinstance(kwargs, dict):
            call_id = ""
            for holder in (kwargs.get("litellm_metadata"), kwargs.get("metadata")):
                if isinstance(holder, dict) and holder.get("litellm_call_id"):
                    call_id = str(holder["litellm_call_id"])
                    break
            if not call_id and kwargs.get("litellm_call_id"):
                call_id = str(kwargs["litellm_call_id"])
            if call_id:
                picks = self.prior_picks.get(call_id)
                if picks:
                    return picks[-1]
        group = _resolve_group_name(kwargs)
        if not group or "*" in group:
            return ""
        names = self.manager.peek_candidate_names()
        if not names:
            return group
        if group in names:
            return group
        # Bare / unqualified id: resolve by candidate suffix only when the
        # match is unique across providers.
        suffix_matches = [name for name in names if name.endswith("/" + group)]
        if len(suffix_matches) == 1:
            return suffix_matches[0]
        if len(suffix_matches) > 1:
            return ""
        return group

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        group = self._event_group(kwargs)
        if not group:
            return
        # Pollinations returns hard failures (credit gate, relayed upstream
        # errors) as HTTP 200 with the error text as message content. Record
        # those as failures so the recency guard and demotion proofs see them.
        text = model_picker.extract_response_text(response_obj)
        if model_picker.is_soft_failure_response(text, response_obj):
            snippet = " ".join(text.split())[:100]
            logger.info("model_picker: soft failure recorded for %s (content=%r)", group, snippet)
            self.stats.record_failure(group, model_picker.FAILURE_CLASS_SOFT)
            return
        if _response_is_thinking_only(response_obj):
            # a 200 "success" that ends the turn on thinking alone must not
            # reinforce the model the way a real answer would — and, like a
            # soft failure, it must not be recorded as a success on paths
            # where the post-call hook did not already retry it. ERROR, not
            # SOFT: thinking-only is prompt-class-dependent, so one
            # observation must not fire the instant-demotion proof.
            logger.info("model_picker: thinking-only response recorded as failure for %s (no actionable content)", group)
            self.stats.record_failure(group, model_picker.FAILURE_CLASS_ERROR)
            return
        self.stats.record_success(group, _event_ttft_seconds(kwargs, start_time))

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        group = self._event_group(kwargs)
        if not group:
            return
        exception = kwargs.get("exception")
        self.stats.record_failure(group, model_picker.classify_exception(exception))
        # A context_length 400 proves the model's real window, which the
        # catalog overstated (minimax-m3.1-flash: catalog 1,048,576, NIM
        # 262,144). Learn it so the fit filter never picks this model for
        # an oversized request again — the lie costs one failure, not
        # every oversized request until the session is compacted.
        limit = model_picker.extract_context_limit(exception)
        if limit is not None:
            self.stats.record_context_limit(group, limit)
            logger.info("model_picker: learned context window for %s: %d tokens", group, limit)

    # -- soft-failure interception ------------------------------------------

    def _failed_group(self, request_data: dict, response: object) -> str:
        """Group a failed (intercepted) attempt belongs to, reconciled.

        Proxy-level request metadata carries the wildcard group name
        (``pollinations/*``) rather than the resolved candidate, so the
        picker's own pick record (PriorPickRegistry, keyed by litellm_call_id)
        is the authoritative first source; the response's model and the
        metadata group follow. A group is only trusted when it names a tracked
        candidate.
        """
        candidates: list[str] = []
        call_id = ""
        logging_obj = getattr(response, "logging_obj", None)
        if isinstance(request_data, dict):
            for holder in (request_data.get("litellm_metadata"), request_data.get("metadata")):
                if isinstance(holder, dict) and holder.get("litellm_call_id"):
                    call_id = str(holder["litellm_call_id"])
                    break
        if not call_id and logging_obj is not None:
            call_id = str(getattr(logging_obj, "litellm_call_id", "") or "")
        if call_id:
            picks = self.prior_picks.get(call_id)
            if picks:
                candidates.append(picks[-1])
        # the stream's logging object carries the router-stamped deployment
        # group (the same channel the stats logger records from) — and,
        # crucially, the resolved model after wildcard substitution, which
        # is the name that actually served the request. The wildcard
        # deployment name itself is never a candidate and is dropped by
        # _event_group; the resolved model is what fixes NIM attribution.
        call_details = getattr(logging_obj, "model_call_details", None)
        if isinstance(call_details, dict):
            holder = call_details.get("litellm_metadata")
            if isinstance(holder, dict):
                for key in ("deployment_model_name", "model_group"):
                    value = holder.get(key)
                    if value:
                        candidates.append(str(value))
            for key in ("model", "model_group"):
                value = call_details.get(key)
                if isinstance(value, str) and value:
                    candidates.append(value)
            params = call_details.get("litellm_params")
            if isinstance(params, dict):
                value = params.get("model")
                if isinstance(value, str) and value:
                    candidates.append(value)
        model = getattr(response, "model", None)
        if isinstance(model, str) and model:
            candidates.append(model)
        metadata_group = self._event_group(request_data if isinstance(request_data, dict) else {})
        if metadata_group:
            candidates.append(metadata_group)
        known = self.manager.peek_candidate_names()
        for group in candidates:
            reconciled = self._event_group({"litellm_metadata": {"model_group": group}})
            if reconciled and (known is None or reconciled in known):
                return reconciled
        # Fallback: the metadata group, already vetted by _event_group
        # (wildcard and ambiguous bare ids come back as ""). A
        # fully-qualified name is worth recording even when it is not in
        # the current snapshot — catalogs churn, and stats outlive
        # snapshots, so a model that re-enters the catalog later still
        # carries its failure history. Only wildcard/ambiguous names
        # (now "") are dropped, because recording under "nvidia_nim/*"
        # or a sibling provider's twin pollutes a bucket that never ranks
        # while leaving the failed model "untried".
        return metadata_group

    @staticmethod
    def _exclude_group(request_data: dict, group: str) -> None:
        """Record a failed model on the request so the picker skips it."""
        if not group or not isinstance(request_data, dict):
            return
        for key in ("litellm_metadata", "metadata"):
            holder = request_data.get(key)
            if isinstance(holder, dict):
                excluded = holder.setdefault("model_picker_exclude", [])
                if isinstance(excluded, list) and group not in excluded:
                    excluded.append(group)

    @staticmethod
    def _retry_data(request_data: dict) -> dict | None:
        """A non-streaming copy of the request for the retry call.

        The router rewrites data["model"] to the RESOLVED deployment model
        (e.g. pollinations/openai/gpt-5.4-nano), so retrying with it would
        re-hit the same failed model forever. Retries must re-enter the
        ORIGINAL entry point (lite-llm/complexity) so the picker can exclude
        the failed model and rank the next candidate; direct (non-tier)
        calls keep their own model.

        Anthropically-shaped requests (/v1/messages) keep their shape —
        _retry_entry_call re-dispatches them through the router's
        anthropic_messages entry, never acompletion — and their top-level
        system prompt is carried along instead of silently dropped.
        """
        if not isinstance(request_data, dict) or not request_data.get("messages"):
            return None
        retry: dict = {}
        for key in _RETRY_PASSTHROUGH_KEYS:
            if key in request_data:
                retry[key] = request_data[key]
        entry_model = ""
        for holder in (request_data.get("litellm_metadata"), request_data.get("metadata")):
            if isinstance(holder, dict) and holder.get("model_group"):
                entry_model = str(holder["model_group"])
                break
        if entry_model:
            retry["model"] = entry_model
        retry["stream"] = False
        return retry

    async def _router_acompletion(self, retry_data: dict):
        """One retry through the routing pipeline, shape-matched entry."""
        from litellm.proxy.proxy_server import llm_router

        return await self._retry_entry_call(llm_router, retry_data)

    @staticmethod
    async def _retry_entry_call(router, retry_data: dict):
        """Dispatch one retry through the entry point matching the request's
        shape.

        /v1/messages bodies stay anthropic-shaped all the way to the
        post-call hooks (top-level ``system``, ``tool_use``/``tool_result``
        content blocks); handing that body to acompletion ships the blocks
        to OpenAI-format providers and 400s every candidate ("Invalid user
        message") — the walk burns the whole pool on a payload no provider
        ever accepted. The router's anthropic_messages entry (the one the
        proxy itself dispatches /v1/messages through) applies the
        per-provider transformation the original request already got.
        """
        if _is_anthropic_request(retry_data):
            entry = getattr(router, "anthropic_messages", None) if router is not None else getattr(litellm, "anthropic_messages", None)
            if entry is not None:
                return await entry(**retry_data)
            logger.warning("model_picker: no anthropic retry entry on this litellm build; retrying through acompletion")
        if router is not None:
            return await router.acompletion(**retry_data)
        return await litellm.acompletion(**retry_data)

    async def _candidate_cap(self) -> int:
        """Walk bound: one attempt per distinct candidate, plus slack for
        unattributed attempts. Falls back to a safety cap when the pool is
        unavailable."""
        try:
            snap = await self.manager.get_snapshot()
            return len(snap.candidates) + _RETRY_WALK_SLACK
        except Exception:  # noqa: BLE001 — the walk must stay bounded regardless
            return _RETRY_WALK_SAFETY_CAP

    async def _retry_until_clean(
        self,
        request_data: dict,
        first_group: str,
        first_failure_class: str = model_picker.FAILURE_CLASS_SOFT,
        first_failure_label: str = "soft failure",
    ):
        """Retry the request until a model succeeds or none are left to try.

        Returns (response, failure_summary) — response is None when every
        available candidate failed. Each failed attempt is recorded and
        excluded from the next pick; soft failures (200-with-error-content),
        thinking-only responses, and hard exceptions all continue the walk.
        Termination: the walk is bounded by the candidate-pool size, and a
        re-offered already-failed model means the picker has nothing fresh
        left.

        The intercepted attempt's failure class is caller-chosen: soft
        failures are deterministic per model+account, so SOFT (instant
        demotion proof) is right for them, but a thinking-only response is
        prompt-class-dependent — the same model answers plain prompts fine —
        so thinking-only entries record ERROR instead: per-request exclusion
        still applies, but persistent demotion needs the normal failure
        proof (repeated thinking-only turns), not a single observation.
        """
        failed_groups: list[str] = []
        last_reason = "unknown"
        group = first_group
        pending_class = first_failure_class
        pending_label = first_failure_label
        attempts = 1  # the intercepted attempt
        cap = await self._candidate_cap()
        while attempts < cap:
            if group and group in failed_groups:
                # the picker is re-offering an already-failed model: no fresh
                # candidates remain
                logger.info("model_picker: candidate pool exhausted after %d attempts", attempts)
                break
            if group:
                self.stats.record_failure(group, pending_class)
                self._exclude_group(request_data, group)
                failed_groups.append(group)
                logger.info("model_picker: %s intercepted for %s; retrying", pending_label, group)
            retry_data = self._retry_data(request_data)
            if retry_data is None:
                break
            attempts += 1
            if os.environ.get("MODEL_PICKER_DEBUG_HOOKS"):
                logger.info("model_picker: retry attempt=%d model=%s", attempts, retry_data.get("model"))
            try:
                retry_resp = await self._router_acompletion(retry_data)
            except Exception as e:  # noqa: BLE001 — one bad provider must not end the walk
                last_reason = f"upstream error ({type(e).__name__})"
                group = self._event_group({"litellm_metadata": {"model_group": _response_model_name(e)}})
                pending_class = model_picker.FAILURE_CLASS_SOFT
                pending_label = "soft failure"
                logger.warning("model_picker: retry attempt failed (%s); trying next candidate", e)
                continue
            text = model_picker.extract_response_text(retry_resp)
            if model_picker.is_soft_failure_response(text, retry_resp):
                last_reason = "provider error in response content"
                group = self._event_group({"litellm_metadata": {"model_group": _response_model_name(retry_resp)}})
                pending_class = model_picker.FAILURE_CLASS_SOFT
                pending_label = "soft failure"
                continue
            if _response_is_thinking_only(retry_resp):
                # a retry that also comes back thinking-only is not a clean
                # answer: keep walking instead of handing the client a
                # notice while untried candidates remain
                last_reason = "thinking-only response"
                group = self._event_group({"litellm_metadata": {"model_group": _response_model_name(retry_resp)}})
                pending_class = model_picker.FAILURE_CLASS_ERROR
                pending_label = "thinking-only response"
                continue
            return retry_resp, {"tried": attempts, "reason": last_reason, "groups": failed_groups}
        return None, {"tried": attempts, "reason": last_reason, "groups": failed_groups}

    @staticmethod
    def _synthesize_tail_events(
        response_obj: object,
        open_block: tuple[int, str] | None,
        next_index: int,
        fallback_text: str = "",
    ) -> list[dict]:
        """Anthropic SSE events continuing the stream with a retry's answer.

        The retry's text continues the still-open text block (or opens a
        fresh one), its tool calls are synthesized as tool_use blocks so
        agent turns recovered mid-flight keep their working tool calls, and
        the message closes with the retry's stop reason and usage in
        anthropic vocabulary.
        """
        text = model_picker.extract_response_text(response_obj) or fallback_text or _FALLBACK_REPLY.format(
            tried=0, reason="unknown"
        )
        tool_uses = _response_tool_uses(response_obj)
        for i, tool_use in enumerate(tool_uses):
            if not tool_use["id"]:
                tool_use["id"] = f"toolu_model_picker_{i}"
        events: list[dict] = []
        index = next_index
        if text:
            if open_block is not None and open_block[1] == "text":
                index = open_block[0]
            else:
                if open_block is not None:
                    events.append({"type": "content_block_stop", "index": open_block[0]})
                events.append({"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
            events.append({"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}})
            events.append({"type": "content_block_stop", "index": index})
            index += 1
        elif open_block is not None:
            # nothing to continue the open block with (a text-less tool
            # answer): close whatever the dead stream left open
            events.append({"type": "content_block_stop", "index": open_block[0]})
            index = max(next_index, open_block[0] + 1)
        for tool_use in tool_uses:
            events.append(
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "tool_use", "id": tool_use["id"], "name": tool_use["name"], "input": {}},
                }
            )
            events.append(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "input_json_delta", "partial_json": json.dumps(tool_use["input"] or {}, separators=(",", ":"))},
                }
            )
            events.append({"type": "content_block_stop", "index": index})
            index += 1
        events.append(
            {
                "type": "message_delta",
                "delta": {"stop_reason": _finish_reason(response_obj, has_tool_uses=bool(tool_uses)), "stop_sequence": None},
                "usage": _usage_dict(response_obj),
            }
        )
        events.append({"type": "message_stop"})
        return events

    @staticmethod
    def _message_start_event(model: str) -> dict:
        """A minimal anthropic message_start, for retries before any upstream chunk."""
        return {
            "type": "message_start",
            "message": {
                "id": "msg_model_picker_retry",
                "type": "message",
                "role": "assistant",
                "content": [],
                "model": model,
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            },
        }

    async def async_post_call_streaming_iterator_hook(self, user_api_key_dict, response, request_data):
        """Sniff streamed chunks; on a soft failure, drop the stream and retry.

        Clean chunks pass through untouched (zero added latency). The credit
        gate arrives atomically in a single delta chunk, so detection happens
        before that chunk is yielded and the client never sees it.

        Mid-stream upstream failures (connection drops, stream timeouts, and
        the in-band error events litellm's adapter converts them into) get
        the same treatment in BOTH phases: the failed model is recorded and
        demoted, and the request retries through the walk with that model
        excluded. The retry's answer continues the same SSE stream — appended
        after any partial content already delivered — so an incomplete
        answer never stands as the turn's final answer.

        Thinking-only responses get the same retry, but ONLY when the turn
        would otherwise have stopped: the check runs once, after the stream
        ends normally, and fires only when the assembled message is thinking
        (or redacted thinking) with no actionable text or tool block and a
        turn-ending stop reason. Thinking deltas mid-stream never fire —
        they precede text in every normal reasoning response — and a
        thinking block alongside text or tool calls never fires, because
        the turn continues from those. Terminal message_delta/message_stop
        events are held back until the stream ends so a thinking-only close
        can be replaced by the retry's tail instead of ending the turn
        empty; clean streams yield them unchanged, in order, at the end.
        """
        open_block: tuple[int, str] | None = None
        next_index = 0
        accumulated = ""
        soft_text: str | None = None
        in_band_error = False  # litellm converted a mid-stream failure into an error event
        saw_text = False  # content text already delivered to the client
        saw_any_chunk = False  # anything at all delivered
        saw_thinking = False  # a thinking/redacted_thinking block appeared
        saw_actionable = False  # non-blank text or a tool block appeared
        stream_stop_reason: str | None = None  # from message_delta, when seen
        pending_terminal: list = []  # terminal-only chunks held for the end decision
        terminal_yielded = False  # a terminal event already went out (mixed chunk)
        try:
            async for chunk in response:
                saw_any_chunk = True
                text = ""
                chunk_terminal_only = False
                try:
                    if _is_in_band_error(chunk):
                        # litellm's adapter already swallowed the upstream
                        # exception (e.g. MidStreamFallbackError on a read
                        # timeout) and emitted an in-band error event; no
                        # exception will ever reach us. Drop the chunk — the
                        # client must never see it — and handle it below.
                        in_band_error = True
                        break
                    text = _event_text(chunk)
                    if text:
                        accumulated += text
                    events = _chunk_events(chunk)
                    chunk_terminal_only = bool(events) and all(
                        e.get("type") in ("message_delta", "message_stop") for e in events
                    )
                    for event in events:
                        etype = event.get("type")
                        if etype in ("message_delta", "message_stop"):
                            if etype == "message_delta":
                                delta = event.get("delta") or {}
                                if isinstance(delta, dict) and delta.get("stop_reason"):
                                    stream_stop_reason = str(delta["stop_reason"])
                            if not chunk_terminal_only:
                                # a terminal event riding with content has
                                # already been delivered with this chunk: the
                                # stream is closed from the client's side and
                                # no tail can replace it
                                terminal_yielded = True
                            continue
                        thinking, actionable = _classify_stream_event(event)
                        saw_thinking = saw_thinking or thinking
                        saw_actionable = saw_actionable or actionable
                        if etype == "content_block_start":
                            block = event.get("content_block") or {}
                            open_block = (int(event.get("index", 0) or 0), str(block.get("type") or "text"))
                            next_index = max(next_index, open_block[0] + 1)
                        elif etype == "content_block_stop":
                            next_index = max(next_index, int(event.get("index", 0) or 0) + 1)
                            open_block = None
                    if text and model_picker.is_soft_failure_content(accumulated):
                        soft_text = accumulated
                        break  # dropped before yield — the client never sees it
                except Exception as e:  # noqa: BLE001 — sniffing must never break the stream
                    logger.debug("model_picker: stream sniff error (%s)", e)
                if text:
                    saw_text = True
                if chunk_terminal_only:
                    pending_terminal.append(chunk)
                else:
                    yield chunk
        except (asyncio.CancelledError, GeneratorExit):
            raise
        except Exception as e:
            # the upstream stream itself failed mid-response. Treat it exactly
            # like a soft failure in both phases: the walk below records the
            # failure (demoting the model) and retries with a different one —
            # an incomplete answer must never stand as the turn's answer,
            # not even when partial content is already with the client.
            group = self._failed_group(request_data if isinstance(request_data, dict) else {}, response)
            logger.warning(
                "model_picker: upstream stream failed mid-response for %s (%s: %s); saw_text=%s; retrying",
                group,
                type(e).__name__,
                str(e)[:120],
                saw_text,
            )
            soft_text = soft_text or "mid-stream upstream failure"

        if in_band_error:
            # the adapter's error event never reached the client (dropped
            # above); the walk below applies the same handling as exceptions
            group = self._failed_group(request_data if isinstance(request_data, dict) else {}, response)
            logger.warning(
                "model_picker: in-band error event intercepted for %s; saw_text=%s; retrying",
                group,
                saw_text,
            )
            soft_text = soft_text or "in-band error event"

        if soft_text is None:
            # Normal completion — the only place the thinking-only rule may
            # fire. The stream already delivered the thinking block (it
            # cannot be un-yielded), but the held terminal events have not
            # gone out, so the retry's tail replaces the empty close: the
            # assembled message gains the retry's text/tool blocks and the
            # turn continues instead of ending on thinking alone.
            if (
                saw_thinking
                and not saw_actionable
                and not terminal_yielded
                and (stream_stop_reason is None or stream_stop_reason in _TURN_ENDING_STOP_REASONS)
            ):
                try:
                    group = self._failed_group(request_data, response)
                    retry_resp, summary = await self._retry_until_clean(
                        request_data,
                        group,
                        first_failure_class=model_picker.FAILURE_CLASS_ERROR,
                        first_failure_label="thinking-only response",
                    )
                    if retry_resp is None:
                        logger.warning(
                            "model_picker: retry walk exhausted after %d attempts (%s); replying with fallback notice",
                            summary["tried"],
                            summary["groups"],
                        )
                    fallback = _FALLBACK_REPLY.format(tried=summary["tried"], reason=summary["reason"])
                    for event in self._synthesize_tail_events(retry_resp, open_block, next_index, fallback):
                        yield _sse_frame(event)
                except Exception as e:  # noqa: BLE001 — retry errors must not crash the SSE stream
                    logger.warning("model_picker: thinking-only retry error (%s)", e)
                    for event in self._synthesize_tail_events(None, open_block, next_index):
                        yield _sse_frame(event)
                return
            for chunk in pending_terminal:
                yield chunk
            return

        if not saw_any_chunk:
            # the stream died before yielding anything: synthesize the
            # message_start that the tail synthesis below completes
            model_name = ""
            if isinstance(request_data, dict):
                model_name = str(request_data.get("model") or "")
            yield _sse_frame(self._message_start_event(model_name))
            # leave open_block alone: the synthesis opens its own
            # content_block_start when none has been streamed yet

        try:
            group = self._failed_group(request_data, response)
            retry_resp, summary = await self._retry_until_clean(request_data, group)
            if retry_resp is None:
                logger.warning(
                    "model_picker: retry walk exhausted after %d attempts (%s); replying with fallback notice",
                    summary["tried"],
                    summary["groups"],
                )
            fallback = _FALLBACK_REPLY.format(tried=summary["tried"], reason=summary["reason"])
            for event in self._synthesize_tail_events(retry_resp, open_block, next_index, fallback):
                yield _sse_frame(event)
        except Exception as e:  # noqa: BLE001 — retry errors must not crash the SSE stream
            logger.warning("model_picker: stream retry error (%s)", e)
            for event in self._synthesize_tail_events(None, open_block, next_index):
                yield _sse_frame(event)

    async def async_post_call_success_hook(self, user_api_key_dict, data, response):
        """Non-streaming twin: swap a soft-failed response for a retried one."""
        import os as _os

        if _os.environ.get("MODEL_PICKER_DEBUG_HOOKS"):
            logger.info(
                "model_picker: success-hook invoked type=%s text=%r",
                type(response).__name__,
                model_picker.extract_response_text(response)[:60],
            )
        text = model_picker.extract_response_text(response)
        thinking_only = _response_is_thinking_only(response)
        if not thinking_only and (not text or not model_picker.is_soft_failure_response(text, response)):
            return response
        anthropic_shape = isinstance(response, dict) and isinstance(response.get("content"), list)
        try:
            group = self._failed_group(data if isinstance(data, dict) else {}, response)
            retry_resp, summary = await self._retry_until_clean(
                data,
                group,
                first_failure_class=model_picker.FAILURE_CLASS_ERROR if thinking_only else model_picker.FAILURE_CLASS_SOFT,
                first_failure_label="thinking-only response" if thinking_only else "soft failure",
            )
            if retry_resp is not None:
                if anthropic_shape:
                    return self._as_anthropic_dict(response, retry_resp, "")
                return retry_resp
            logger.warning(
                "model_picker: retry walk exhausted after %d attempts (%s); replying with fallback notice",
                summary["tried"],
                summary["groups"],
            )
            notice_text = _FALLBACK_REPLY.format(tried=summary["tried"], reason=summary["reason"])
        except Exception as e:  # noqa: BLE001 — hook errors must not fail the request
            logger.warning("model_picker: non-streaming retry error (%s)", e)
            notice_text = _FALLBACK_REPLY.format(tried=1, reason="retry error")
        # never return the error-bearing original response; preserve the
        # caller's wire shape so anthropic clients keep parsing
        if anthropic_shape:
            return self._as_anthropic_dict(response, None, notice_text)
        return litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": notice_text}, "finish_reason": "stop"}]
        )

    @staticmethod
    def _as_anthropic_dict(original: dict, retry_obj: object, fallback_text: str) -> dict:
        """Anthropic-shaped replacement carrying the retry's answer.

        Preserves the caller's wire shape; carries the retry's text AND its
        tool_use blocks (agent turns recovered mid-flight keep their tool
        calls) with an anthropic stop_reason.
        """
        tool_uses = _response_tool_uses(retry_obj)
        for i, tool_use in enumerate(tool_uses):
            if not tool_use["id"]:
                tool_use["id"] = f"toolu_model_picker_{i}"
        content: list[dict] = []
        text = model_picker.extract_response_text(retry_obj) or fallback_text
        if text:
            content.append({"type": "text", "text": text})
        content += [{"type": "tool_use", "id": t["id"], "name": t["name"], "input": t["input"]} for t in tool_uses]
        if not content:
            content = [{"type": "text", "text": fallback_text}]
        return {
            "id": original.get("id") or "msg_model_picker",
            "type": "message",
            "role": "assistant",
            "model": original.get("model") or "",
            "content": content,
            "stop_reason": "tool_use" if tool_uses else "end_turn",
            "stop_sequence": None,
            "usage": original.get("usage") or {"input_tokens": 0, "output_tokens": 0},
        }


# Module-level instances referenced from lite-llm-picker.yaml.
picker = ModelPickerPlugin()
stats_logger = ModelPickerStatsLogger()
