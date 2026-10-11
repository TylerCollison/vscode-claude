"""
Model Picker: litellm complexity-router routing plugin + passive stats logger.

Wired from lite-llm-picker.yaml:

    complexity_router_config:
      plugins: ["model_picker_plugin.picker"]
    litellm_settings:
      callbacks: [..., "model_picker_plugin.stats_logger"]

The plugin runs AFTER the complexity router's tier classification (it is the
sanctioned downstream hook: ComplexityRouter._pick_model_for_tier runs
complexity_router_config.plugins against the chosen tier's pool and routes to
the surviving value with no pool validation). It narrows the pool to the single
best free chat model per the tier rubric and may return a dynamic
``pollinations/<catalog-id>`` name served by the ``pollinations/*`` wildcard
model_list entry, or any existing static group name.

litellm's ``get_instance_fn`` exec's this file with spec_from_file_location
WITHOUT registering it in sys.modules, so a plain ``import model_picker``
would not resolve, and this file being referenced from both the plugins list
and the callbacks list would otherwise produce two independent module copies.
The _load_sibling guard registers the sibling once under a fixed sys.modules
key so the catalog cache and rolling stats are shared by every instance.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from datetime import datetime

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
# Tier detection
# ---------------------------------------------------------------------------

_TIER_BY_POOL = {
    frozenset({"lite-llm/default"}): model_picker.TIER_DEFAULT,
    frozenset({"lite-llm/think"}): model_picker.TIER_THINK,
    frozenset({"lite-llm/ultra-think"}): model_picker.TIER_THINK,
}


def detect_tier(candidate_models: list[str]) -> str | None:
    """Map the complexity router's tier pool onto a picker rubric.

    The pool is the tier's configured model group(s), possibly intersected with
    a context-fit filter. Anything unrecognized passes through untouched.
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

        # context.metadata is a pydantic COPY of the request metadata — safe to
        # read (litellm stamps attempted_retries into the real dict before the
        # copy), but writes through it never reach the request. Pick history
        # therefore lives in the call-scoped PriorPickRegistry, keyed by the
        # litellm_call_id that every proxy request carries.
        metadata = context.metadata if context.metadata else {}
        call_id = str(metadata.get("litellm_call_id") or "")
        prior_picks = self.prior_picks.get(call_id)

        estimate = model_picker.estimate_tokens(context.structured_messages)
        snapshot = await self.manager.get_snapshot(_get_router_model_list())
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
            "model_picker: tier=%s estimate=%dtok pick=%s (score=%.3f ctx=%s provider=%s free=%s stale=%s attempt_excluded=%s)",
            tier,
            estimate,
            pick.name,
            ranked[0].health_score,
            pick.context_length or "?",
            pick.provider,
            pick.free,
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


def _get_router_model_list() -> list[dict]:
    """Best-effort access to the proxy router's model_list for static discovery."""
    try:
        from litellm.proxy.proxy_server import llm_router

        if llm_router is not None:
            return list(getattr(llm_router, "model_list", None) or [])
    except Exception:  # noqa: BLE001 — unit-test / non-proxy contexts
        pass
    return []


# ---------------------------------------------------------------------------
# Passive stats logger
# ---------------------------------------------------------------------------


def _resolve_group_name(kwargs: dict) -> str:
    """Model group a success/failure event belongs to.

    The router stamps ``deployment_model_name`` (the group) into the request
    metadata; fall back to the standard model_group/model fields.
    """
    for holder in (kwargs.get("litellm_metadata"), kwargs.get("metadata"), kwargs.get("litellm_params")):
        if isinstance(holder, dict):
            for key in ("deployment_model_name", "model_group"):
                value = holder.get(key)
                if value:
                    return str(value)
    group = kwargs.get("model_group") or kwargs.get("model")
    return str(group) if group else ""


def _event_ttft_seconds(kwargs: dict, start_time: datetime) -> float | None:
    """TTFT for streaming successes; None for non-streaming calls."""
    completion_start = kwargs.get("completion_start_time")
    if isinstance(completion_start, datetime):
        return (completion_start - start_time).total_seconds()
    return None


class ModelPickerStatsLogger(CustomLogger):
    """Records per-group success/failure/TTFT observations for the picker."""

    def __init__(self, stats=None) -> None:
        self._stats = stats

    @property
    def stats(self):
        if self._stats is None:
            self._stats = model_picker.get_shared_stats()
        return self._stats

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        group = _resolve_group_name(kwargs)
        if not group:
            return
        # Pollinations returns hard failures (credit gate, relayed upstream
        # errors) as HTTP 200 with the error text as message content. Record
        # those as failures so the recency guard and demotion proofs see them.
        text = model_picker.extract_response_text(response_obj)
        if model_picker.is_soft_failure_content(text):
            snippet = " ".join(text.split())[:100]
            logger.info("model_picker: soft failure recorded for %s (content=%r)", group, snippet)
            self.stats.record_failure(group, model_picker.FAILURE_CLASS_ERROR)
            return
        self.stats.record_success(group, _event_ttft_seconds(kwargs, start_time))

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        group = _resolve_group_name(kwargs)
        if not group:
            return
        exception = kwargs.get("exception")
        self.stats.record_failure(group, model_picker.classify_exception(exception))


# Module-level instances referenced from lite-llm-picker.yaml.
picker = ModelPickerPlugin()
stats_logger = ModelPickerStatsLogger()
