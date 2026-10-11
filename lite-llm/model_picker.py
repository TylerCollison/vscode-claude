"""
Model Picker library: catalog snapshots, rubric ranking, and rolling stats.

Pure stdlib + httpx — deliberately free of litellm imports so it can be unit
tested and loaded standalone. Consumed by model_picker_plugin.py, which loads
this module via a sys.modules-guarded sibling loader (litellm's
``get_instance_fn`` exec's config-adjacent files without registering them in
``sys.modules``, so a plain ``import model_picker`` would neither resolve nor
share state across the plugin/stats-logger references).

Design (beads workspace-c8o, revised in workspace-4wr):

- Candidates: free chat-capable models from the pollinations catalog
  (metric-backed) plus curated static groups from the other providers
  (metric-less). Gemini groups are excluded outright.
- Ranking classes: UNKNOWN (untried metric-less, favored — ranks above
  everything on the health dimension, except deprioritized providers such as
  llm7 whose untried groups start at a neutral prior below healthy
  metric-backed candidates), METRIC (published health, or our own tracked
  health once the group has observations), KNOWN (demoted while the current
  observation window proves it bad).
- Self-tracked health (workspace-4wr): once a metric-less group has
  observations it competes on the decayed, rate-limit-weighted success rate
  (Laplace-smoothed), so a sustained 429 streak (e.g. an llm7 daily token
  quota with a ~24h Retry-After) demotes it below healthy metric-backed
  candidates and real successes promote it back — no published metrics needed.
- Demotion proofs (re-derived from the rolling window on every evaluation, so
  recovery is automatic): >= MIN_OBS observations with derived hard-failure
  rate below best-metric-score minus margin; >= MIN_OBS streaming TTFT
  observations with decayed mean above the TTFT threshold; or an
  AuthenticationError (dead until a success). Rate-limit failures never fire
  the hard proof (busy-but-working) but do weigh down the tracked score.
- Rubric: default tier sorts health-first then context; think tiers sort
  context-first then health (class only breaks ties). Latency-demoted models
  carry a class floor below all metric-backed candidates in the default tier.
- Recency guard: a candidate whose most recent observation is a failure within
  the recency window is skipped; one success restores eligibility.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger("model_picker")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLLINATIONS_MODELS_URL = "https://gen.pollinations.ai/v1/models"
NIM_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"
OLLAMA_MODELS_URL = "https://ollama.com/v1/models"

DEFAULT_TTL_SECONDS = 300.0
DEFAULT_MIN_OBS = 3
DEFAULT_DEMOTE_TTFT_SECONDS = 15.0
DEFAULT_DEMOTE_MARGIN = 0.02
DEFAULT_RECENCY_WINDOW_SECONDS = 60.0
DEFAULT_HALF_LIFE_SECONDS = 24 * 3600.0
DEFAULT_FALLBACK_MODEL = "openai/gpt-5.4-nano"
DEFAULT_UNKNOWN_CONTEXT_TOKENS = 0  # 0 = unknown; unknown-context candidates bypass fit filtering
# Metric-less providers that must NOT get the untried benefit-of-the-doubt:
# llm7 has no published metrics and its groups trip daily token quotas (429 +
# ~24h Retry-After), so an untried llm7 group starts at a neutral prior below
# healthy metric-backed candidates instead of at the top of the list.
DEFAULT_DEPRIORITIZED_PROVIDERS = "llm7"
# Score an untried deprioritized-provider group competes with: below healthy
# metric-backed candidates (published wilson > 0.5), above zero-evidence ones.
DEFAULT_UNTRIED_PRIOR_SCORE = 0.5

CATALOG_FETCH_TIMEOUT_SECONDS = 10.0

# api_base substrings -> provider for static-group discovery. Pollinations
# groups are handled by the catalog; gemini groups are excluded per spec.
_STATIC_PROVIDER_BY_API_BASE = (
    ("ollama.com", "ollama"),
    ("api.llm7.io", "llm7"),
)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


class PickerConfig:
    """Snapshot of the env-tunable knobs."""

    def __init__(self) -> None:
        self.ttl_seconds = _env_float("MODEL_PICKER_TTL_SECONDS", DEFAULT_TTL_SECONDS)
        self.min_obs = _env_int("MODEL_PICKER_MIN_OBS", DEFAULT_MIN_OBS)
        self.demote_ttft_seconds = _env_float("MODEL_PICKER_DEMOTE_TTFT_SECONDS", DEFAULT_DEMOTE_TTFT_SECONDS)
        self.demote_margin = _env_float("MODEL_PICKER_DEMOTE_MARGIN", DEFAULT_DEMOTE_MARGIN)
        self.recency_window_seconds = _env_float("MODEL_PICKER_RECENCY_WINDOW_SECONDS", DEFAULT_RECENCY_WINDOW_SECONDS)
        self.half_life_seconds = _env_float("MODEL_PICKER_HALF_LIFE_SECONDS", DEFAULT_HALF_LIFE_SECONDS)
        self.fallback_model = os.environ.get("MODEL_PICKER_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)
        self.pollinations_url = os.environ.get("MODEL_PICKER_MODELS_URL", POLLINATIONS_MODELS_URL)
        self.deprioritized_providers = frozenset(
            p.strip()
            for p in os.environ.get("MODEL_PICKER_DEPRIORITIZED_PROVIDERS", DEFAULT_DEPRIORITIZED_PROVIDERS).split(",")
            if p.strip()
        )
        self.untried_prior_score = _env_float("MODEL_PICKER_UNTRIED_PRIOR_SCORE", DEFAULT_UNTRIED_PRIOR_SCORE)


def picker_enabled() -> bool:
    """Truthiness of MODEL_PICKER_ENABLED ('1', 'true', 'yes', 'on')."""
    return os.environ.get("MODEL_PICKER_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------


@dataclass
class ModelCandidate:
    """One rankable model, normalized across providers."""

    name: str  # routable model group name: "pollinations/<id>" or a static group
    provider: str  # pollinations | nvidia_nim | ollama | llm7
    context_length: int = 0  # 0 = unknown (bypasses fit filtering)
    metricless: bool = True  # no published metrics -> favored while UNKNOWN
    success_rate: float = 1.0  # published 0..1 (placeholder for metric-less)
    requests: int = 0  # published sample size
    available: bool = True  # False when an existence check proved it gone
    existence_id: str = ""  # upstream id to check in the provider's catalog ("" = not checkable)
    source: str = "prior"  # pollinations_api | prior

    @property
    def wilson_score(self) -> float:
        """Wilson lower bound (z=1.96) of the published success rate."""
        return wilson_lower_bound(self.success_rate, self.requests)


def wilson_lower_bound(success_rate: float, n: int, z: float = 1.96) -> float:
    """Wilson score lower bound; 0 observations or 0 rate both bound near 0."""
    if n <= 0:
        return 0.0
    p = min(max(success_rate, 0.0), 1.0)
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - spread) / denom)


# ---------------------------------------------------------------------------
# Catalog parsing
# ---------------------------------------------------------------------------


def parse_pollinations_models(payload: dict) -> list[ModelCandidate]:
    """Parse GET /v1/models from pollinations into free chat-capable candidates."""
    out: list[ModelCandidate] = []
    for m in (payload or {}).get("data") or []:
        if not isinstance(m, dict):
            continue
        model_id = m.get("id") or ""
        if not model_id:
            continue
        if m.get("paid_only"):
            continue
        output_modalities = m.get("output_modalities") or []
        input_modalities = m.get("input_modalities") or []
        if "text" not in output_modalities or "text" not in input_modalities:
            continue
        if "/v1/chat/completions" not in (m.get("supported_endpoints") or []):
            continue
        health = m.get("health") or {}
        if (health.get("status") or "unknown").lower() == "down":
            continue
        success_rate = health.get("success_rate")
        out.append(
            ModelCandidate(
                name=f"pollinations/{model_id}",
                provider="pollinations",
                context_length=int(m.get("context_length") or 0),
                metricless=False,
                success_rate=float(success_rate) / 100.0 if isinstance(success_rate, (int, float)) else 0.0,
                requests=int(health.get("requests") or 0),
                source="pollinations_api",
            )
        )
    return out


def parse_model_ids(payload: dict | list) -> set[str]:
    """Bare model-id set from a provider's /v1/models (existence checks)."""
    data = payload.get("data") if isinstance(payload, dict) else payload
    if data is None:
        data = []
    ids: set[str] = set()
    for m in data:
        if isinstance(m, dict) and m.get("id"):
            ids.add(str(m["id"]))
        elif isinstance(m, str):
            ids.add(m)
    return ids


def apply_existence(candidates: list[ModelCandidate], listed_ids: set[str], provider: str) -> None:
    """Mark candidates of *provider* unavailable when absent from its catalog.

    Catches laguna-style model removal without waiting for failures. Empty
    ``listed_ids`` (fetch failed) leaves candidates untouched — stale-serve.
    """
    if not listed_ids:
        return
    for c in candidates:
        if c.provider == provider and c.existence_id and c.existence_id not in listed_ids:
            c.available = False


# ---------------------------------------------------------------------------
# Static group discovery (metric-less candidates from the litellm config)
# ---------------------------------------------------------------------------


@dataclass
class StaticGroup:
    group_name: str
    provider: str
    upstream_model: str  # provider-facing id (for existence checks / ctx xref)


def _strip_provider_prefix(model: str) -> str:
    for prefix in ("nvidia_nim/", "openai/", "gemini/"):
        if model.startswith(prefix):
            return model[len(prefix):]
    return model


def discover_static_groups(model_list: list[dict]) -> list[StaticGroup]:
    """Derive metric-less candidate groups from the router's model_list.

    Recognizes nvidia_nim (by model prefix), ollama and llm7 (by api_base).
    Pollinations-backed groups are handled by the catalog; gemini groups are
    excluded per spec; anything unrecognized is ignored.
    """
    out: list[StaticGroup] = []
    seen: set[str] = set()
    for entry in model_list or []:
        if not isinstance(entry, dict):
            continue
        group_name = entry.get("model_name") or ""
        params = entry.get("litellm_params") or {}
        model = str(params.get("model") or "")
        api_base = str(params.get("api_base") or "")
        if not group_name or group_name in seen:
            continue

        provider: str | None = None
        upstream = _strip_provider_prefix(model)
        if model.startswith("nvidia_nim/"):
            provider = "nvidia_nim"
        else:
            for needle, prov in _STATIC_PROVIDER_BY_API_BASE:
                if needle in api_base:
                    provider = prov
                    break
        if provider is None:
            continue  # pollinations (catalog), gemini (excluded), complexity, unknown
        seen.add(group_name)
        out.append(StaticGroup(group_name=group_name, provider=provider, upstream_model=upstream))
    return out


def static_groups_to_candidates(
    groups: list[StaticGroup],
    pollinations_context_by_id: dict[str, int] | None = None,
) -> list[ModelCandidate]:
    """Build metric-less candidates; context from config model_info or pollinations xref."""
    ctx_by_id = pollinations_context_by_id or {}
    out = []
    for g in groups:
        out.append(
            ModelCandidate(
                name=g.group_name,
                provider=g.provider,
                context_length=ctx_by_id.get(g.upstream_model, DEFAULT_UNKNOWN_CONTEXT_TOKENS),
                metricless=True,
                success_rate=1.0,
                requests=0,
                source="prior",
                existence_id="" if g.provider == "llm7" else g.upstream_model,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Rolling stats (passive observation)
# ---------------------------------------------------------------------------

FAILURE_CLASS_AUTH = "auth"
FAILURE_CLASS_RATE_LIMIT = "rate_limit"
FAILURE_CLASS_TIMEOUT = "timeout"
FAILURE_CLASS_CONNECTION = "connection"
FAILURE_CLASS_ERROR = "error"

# 429 = busy-but-working: mild penalty, fast recovery. Everything else is a
# full failure. Auth additionally dead-marks the group until a success.
_FAILURE_WEIGHTS = {
    FAILURE_CLASS_AUTH: 1.0,
    FAILURE_CLASS_RATE_LIMIT: 0.25,
    FAILURE_CLASS_TIMEOUT: 1.0,
    FAILURE_CLASS_CONNECTION: 1.0,
    FAILURE_CLASS_ERROR: 1.0,
}

_MAX_EVENTS_PER_GROUP = 200


def classify_exception(exc: BaseException | None) -> str:
    """Map a litellm exception to a failure class by type name.

    Type names are matched loosely so the module works with or without a
    litellm import available (the litellm exception classes all carry
    distinctive names).
    """
    name = type(exc).__name__ if exc is not None else ""
    lowered = name.lower()
    if "authentication" in lowered:
        return FAILURE_CLASS_AUTH
    if "ratelimit" in lowered.replace("_", ""):
        return FAILURE_CLASS_RATE_LIMIT
    if "timeout" in lowered:
        return FAILURE_CLASS_TIMEOUT
    if "connection" in lowered:
        return FAILURE_CLASS_CONNECTION
    return FAILURE_CLASS_ERROR


@dataclass
class DerivedStats:
    """Decayed aggregates for one group."""

    success_rate: float = 1.0  # decayed successes / (successes + weighted failures)
    hard_rate: float = 1.0  # success rate over HARD failures only (429s excluded)
    successes: float = 0.0  # decayed success mass in the window
    failures: float = 0.0  # decayed weighted failure mass (429s count 0.25)
    n_obs: int = 0  # total observations in the window
    ttft_mean: float = 0.0  # decayed mean TTFT over streaming successes (0 = no data)
    ttft_n: int = 0
    dead: bool = False  # auth failure observed, no success since
    demoted: bool = False  # KNOWN at the last evaluation (transition logging)
    last_obs_age: float = float("inf")
    last_obs_was_failure: bool = False


class GroupStats:
    """Time-decayed event log for one model group."""

    def __init__(self, half_life_seconds: float) -> None:
        self.half_life_seconds = half_life_seconds
        self._events: deque[tuple[float, bool, float | None, str | None]] = deque()
        self.dead = False
        self.demoted = False  # rank_class was KNOWN at the last evaluation (transition logging)
        self.last_obs_ts: float | None = None
        self.last_obs_was_failure = False

    def _prune(self, now: float) -> None:
        max_age = 4 * self.half_life_seconds
        while self._events and now - self._events[0][0] > max_age:
            self._events.popleft()

    def record_success(self, now: float, ttft_seconds: float | None) -> None:
        self._events.append((now, True, ttft_seconds, None))
        if len(self._events) > _MAX_EVENTS_PER_GROUP:
            self._events.popleft()
        self.dead = False  # a success proves the credential/model alive again
        self.last_obs_ts = now
        self.last_obs_was_failure = False

    def record_failure(self, now: float, failure_class: str) -> None:
        self._events.append((now, False, None, failure_class))
        if len(self._events) > _MAX_EVENTS_PER_GROUP:
            self._events.popleft()
        if failure_class == FAILURE_CLASS_AUTH:
            self.dead = True
        self.last_obs_ts = now
        self.last_obs_was_failure = True

    def derived(self, now: float) -> DerivedStats:
        self._prune(now)
        half = self.half_life_seconds
        successes = failures = hard_failures = 0.0
        ttft_weighted_sum = ttft_weight = 0.0
        ttft_n = 0
        n_obs = 0
        for ts, ok, ttft, failure_class in self._events:
            weight = 0.5 ** ((now - ts) / half)
            n_obs += 1
            if ok:
                successes += weight
                if ttft is not None:
                    ttft_weighted_sum += ttft * weight
                    ttft_weight += weight
                    ttft_n += 1
            else:
                failures += weight * _FAILURE_WEIGHTS.get(failure_class or FAILURE_CLASS_ERROR, 1.0)
                # Rate limits are busy-but-working: transient, never sticky-
                # demoted. Only hard failures feed the demotion proof.
                if failure_class != FAILURE_CLASS_RATE_LIMIT:
                    hard_failures += weight
        denom = successes + failures
        hard_denom = successes + hard_failures
        last_age = (now - self.last_obs_ts) if self.last_obs_ts is not None else float("inf")
        return DerivedStats(
            success_rate=(successes / denom) if denom > 0 else 1.0,
            hard_rate=(successes / hard_denom) if hard_denom > 0 else 1.0,
            successes=successes,
            failures=failures,
            n_obs=n_obs,
            ttft_mean=(ttft_weighted_sum / ttft_weight) if ttft_weight > 0 else 0.0,
            ttft_n=ttft_n,
            dead=self.dead,
            demoted=self.demoted,
            last_obs_age=last_age,
            last_obs_was_failure=self.last_obs_was_failure,
        )


class StatsRegistry:
    """Per-group rolling stats shared by the plugin and the stats logger."""

    def __init__(self, half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS) -> None:
        self.half_life_seconds = half_life_seconds
        self._groups: dict[str, GroupStats] = {}

    def group(self, name: str) -> GroupStats:
        stats = self._groups.get(name)
        if stats is None:
            stats = GroupStats(self.half_life_seconds)
            self._groups[name] = stats
        return stats

    def record_success(self, name: str, ttft_seconds: float | None = None, now: float | None = None) -> None:
        self.group(name).record_success(time.time() if now is None else now, ttft_seconds)

    def record_failure(self, name: str, failure_class: str, now: float | None = None) -> None:
        self.group(name).record_failure(time.time() if now is None else now, failure_class)

    def derived(self, name: str, now: float | None = None) -> DerivedStats:
        return self.group(name).derived(time.time() if now is None else now)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

TIER_DEFAULT = "default"
TIER_THINK = "think"

_CLASS_FAVORED = 0
_CLASS_METRIC = 1
_CLASS_KNOWN = 2


@dataclass
class RankedCandidate:
    candidate: ModelCandidate
    health_score: float
    rank_class: int  # _CLASS_FAVORED | _CLASS_METRIC | _CLASS_KNOWN
    demotion_reason: str = ""  # auth | failures | latency when KNOWN, else ""


def tracked_health_score(stats: DerivedStats) -> float:
    """Self-tracked health for a metric-less group with observations.

    Laplace-smoothed decayed success rate over rate-limit-weighted events:
    one pseudo-success and one pseudo-failure keep small samples off the rails
    (a single transient 429 lands mid-pack instead of at zero) while a
    sustained 429 streak decays toward 0 and real successes promote back.
    """
    return (stats.successes + 1.0) / (stats.successes + stats.failures + 2.0)


def estimate_tokens(messages: list[dict]) -> int:
    """Cheap chars/4 token estimate over OpenAI-shaped messages."""
    total_chars = 0
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        total_chars += len(text)
    return total_chars // 4


def _classify_candidate(
    candidate: ModelCandidate,
    stats: DerivedStats,
    cfg: PickerConfig,
    best_metric_score: float,
) -> tuple[int, float, str]:
    """Return (rank_class, health_score, demotion_reason) for one candidate.

    Pure: class and score are re-derived from the current observation window
    on every evaluation, so demotion recovers (promote) as failures decay or
    successes accrue. Transition logging happens in rank_candidates, which
    tracks the previous class per group.
    """
    if not candidate.metricless:
        return _CLASS_METRIC, candidate.wilson_score, ""

    failure_proof = (
        stats.n_obs >= cfg.min_obs
        and not stats.dead
        and stats.hard_rate < best_metric_score - cfg.demote_margin
    )
    latency_proof = stats.ttft_n >= cfg.min_obs and stats.ttft_mean > cfg.demote_ttft_seconds
    if stats.dead:
        return _CLASS_KNOWN, 0.0, "auth"
    if failure_proof or latency_proof:
        score = wilson_lower_bound(stats.success_rate, max(stats.n_obs, 1))
        return _CLASS_KNOWN, score, "failures" if failure_proof else "latency"

    if stats.n_obs <= 0:
        # Never tried. Untested static groups get the benefit of the doubt —
        # except deprioritized providers (llm7: no published metrics, groups
        # that trip daily token quotas), which start at a neutral prior below
        # healthy metric-backed candidates and compete on tracked evidence
        # from the first observation.
        if candidate.provider in cfg.deprioritized_providers:
            return _CLASS_METRIC, cfg.untried_prior_score, ""
        return _CLASS_FAVORED, 1.0, ""

    # Tried: rank on OUR OWN tracked health (429-weighted, decayed) instead of
    # a static 1.0, so sustained rate-limiting demotes without waiting for a
    # hard-failure proof.
    return _CLASS_METRIC, tracked_health_score(stats), ""


def _log_class_transition(
    stats_registry: StatsRegistry,
    name: str,
    rank_class: int,
    reason: str,
    dstats: DerivedStats,
) -> None:
    """Log KNOWN <-> not-KNOWN transitions for a group.

    GroupStats.demoted mirrors the class the group got at its last evaluation
    (the classification itself is stateless — DerivedStats copies are
    throwaway, and writing the flag there never persisted, which made the old
    demote lines re-fire on every request). Rate limits alone never produce
    KNOWN, so they never log a demotion; the tracked score drop is silent.
    """
    gstats = stats_registry.group(name)
    is_known = rank_class == _CLASS_KNOWN
    if is_known and not gstats.demoted:
        logger.info(
            "model_picker: demoted %s (reason=%s n_obs=%d rate=%.3f ttft=%.1fs)",
            name,
            reason,
            dstats.n_obs,
            dstats.success_rate,
            dstats.ttft_mean,
        )
    elif gstats.demoted and not is_known:
        logger.info(
            "model_picker: promoted %s (n_obs=%d rate=%.3f ttft=%.1fs)",
            name,
            dstats.n_obs,
            dstats.success_rate,
            dstats.ttft_mean,
        )
    gstats.demoted = is_known


def rank_candidates(
    candidates: list[ModelCandidate],
    tier: str,
    stats_registry: StatsRegistry,
    cfg: PickerConfig,
    estimate: int = 0,
    exclude: frozenset[str] = frozenset(),
    now: float | None = None,
) -> list[RankedCandidate]:
    """Rank candidates per the tier rubric, guards, and demotion classes.

    Returns an empty list only when nothing is eligible at all.
    """
    now = time.time() if now is None else now
    metric_scores = [c.wilson_score for c in candidates if not c.metricless and c.available]
    # No metric-backed candidates (e.g. fallback snapshot) -> the relative
    # failure proof can never fire, which is correct: there is nothing to be
    # "below". Auth and latency proofs remain active.
    best_metric_score = max(metric_scores) if metric_scores else 0.0

    pool: list[tuple[ModelCandidate, DerivedStats]] = []
    for c in candidates:
        if not c.available:
            continue
        # Context fit: only enforced where the context length is actually known;
        # metric-less groups with unknown context bypass fit (the in-request
        # retry mechanism backstops a genuine overflow).
        if c.context_length and estimate > c.context_length:
            continue
        pool.append((c, stats_registry.derived(c.name, now)))

    ranked: list[RankedCandidate] = []
    for c, dstats in pool:
        rank_class, score, reason = _classify_candidate(c, dstats, cfg, best_metric_score)
        _log_class_transition(stats_registry, c.name, rank_class, reason, dstats)
        ranked.append(RankedCandidate(candidate=c, health_score=score, rank_class=rank_class, demotion_reason=reason))
    dstats_by_name = {c.name: d for c, d in pool}

    # Recency guard: skip candidates whose most recent observation was a
    # failure inside the recency window; if that leaves nothing, keep all.
    def _is_guarded(r: RankedCandidate) -> bool:
        d = dstats_by_name[r.candidate.name]
        return d.last_obs_was_failure and d.last_obs_age <= cfg.recency_window_seconds

    unguarded = [r for r in ranked if not _is_guarded(r)]
    if unguarded:
        ranked = unguarded

    # Attempt-aware exclusion: models this request already tried.
    if exclude:
        remaining = [r for r in ranked if r.candidate.name not in exclude]
        if remaining:
            ranked = remaining

    # Latency-demoted models carry a class floor below all metric-backed
    # candidates in the default tier (health dimension). Failure-demoted models
    # compete on evidence alongside metric-backed ones. In think tiers the
    # rubric is context-first and rank_class already resolves ties.
    latency_demoted_names: set[str] = set()
    for r in ranked:
        if r.rank_class == _CLASS_KNOWN:
            d = dstats_by_name[r.candidate.name]
            if d.ttft_n >= cfg.min_obs and d.ttft_mean > cfg.demote_ttft_seconds:
                latency_demoted_names.add(r.candidate.name)

    if tier == TIER_THINK:
        # Context-first; class breaks context ties (favored > metric > known).
        ranked.sort(
            key=lambda r: (
                -r.candidate.context_length,
                r.rank_class,
                -r.health_score,
                r.candidate.name,
            )
        )
    else:  # TIER_DEFAULT: favored block first (health all equal -> context
        # tiebreak), then metric + failure-demoted interleaved by evidence
        # score, with latency-demoted floored below all metric-backed.
        def sort_key(r: RankedCandidate):
            favored = 0 if r.rank_class == _CLASS_FAVORED else 1
            effective_score = r.health_score - (1.0 if r.candidate.name in latency_demoted_names else 0.0)
            return (
                favored,
                -effective_score,
                -r.candidate.context_length,
                r.candidate.name,
            )

        ranked.sort(key=sort_key)
    return ranked


# ---------------------------------------------------------------------------
# Catalog fetching
# ---------------------------------------------------------------------------


async def _fetch_json(url: str, api_key: str | None) -> dict | list:
    import httpx

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=CATALOG_FETCH_TIMEOUT_SECONDS) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def fetch_pollinations_catalog(cfg: PickerConfig) -> list[ModelCandidate]:
    payload = await _fetch_json(cfg.pollinations_url, os.environ.get("POLLINATION_API_KEY"))
    return parse_pollinations_models(payload)


async def fetch_listed_ids(url: str, api_key_env: str) -> set[str]:
    try:
        payload = await _fetch_json(url, os.environ.get(api_key_env))
        return parse_model_ids(payload)
    except Exception as e:  # noqa: BLE001 — existence checks are best-effort
        logger.warning("model_picker: existence fetch failed for %s: %s", url, e)
        return set()


# ---------------------------------------------------------------------------
# Snapshot manager (TTL cache, single-flight, stale-serve, fallback)
# ---------------------------------------------------------------------------


@dataclass
class CatalogSnapshot:
    candidates: list[ModelCandidate]
    created_at: float = field(default_factory=time.time)
    stale: bool = False  # served from cache after a refresh failure

    def context_by_id(self) -> dict[str, int]:
        return {
            c.name.split("/", 1)[1]: c.context_length
            for c in self.candidates
            if c.provider == "pollinations" and c.context_length
        }


class CatalogManager:
    """TTL-cached catalog with single-flight refresh and stale/fallback serve."""

    def __init__(self, cfg: PickerConfig | None = None) -> None:
        self.cfg = cfg or PickerConfig()
        self._snapshot: CatalogSnapshot | None = None
        self._lock = asyncio.Lock()
        self._static_groups: list[StaticGroup] | None = None

    def _ensure_static_groups(self, router_model_list: list[dict] | None) -> None:
        if self._static_groups is None and router_model_list:
            self._static_groups = discover_static_groups(router_model_list)

    def _fallback_snapshot(self) -> CatalogSnapshot:
        self._ensure_static_groups(None)
        candidates = static_groups_to_candidates(self._static_groups or [])
        candidates.append(
            ModelCandidate(
                name=f"pollinations/{self.cfg.fallback_model}",
                provider="pollinations",
                context_length=0,
                metricless=False,
                success_rate=1.0,
                requests=0,
                source="prior",
            )
        )
        return CatalogSnapshot(candidates=candidates, stale=True)

    async def get_snapshot(self, router_model_list: list[dict] | None = None) -> CatalogSnapshot:
        """Return a fresh-enough snapshot; single-flight, stale-serve on failure."""
        now = time.time()
        snap = self._snapshot
        if snap is not None and (now - snap.created_at) < self.cfg.ttl_seconds:
            return snap

        async with self._lock:
            now = time.time()
            snap = self._snapshot
            if snap is not None and (now - snap.created_at) < self.cfg.ttl_seconds:
                return snap
            try:
                self._ensure_static_groups(router_model_list)
                pollinations = await fetch_pollinations_catalog(self.cfg)
                nim_ids = await fetch_listed_ids(NIM_MODELS_URL, "NIM_API_KEY")
                ollama_ids = await fetch_listed_ids(OLLAMA_MODELS_URL, "OLLAMA_API_KEY")
                static = static_groups_to_candidates(
                    self._static_groups or [],
                    pollinations_context_by_id={
                        c.name.split("/", 1)[1]: c.context_length for c in pollinations if c.context_length
                    },
                )
                apply_existence(static, nim_ids, "nvidia_nim")
                apply_existence(static, ollama_ids, "ollama")
                candidates = pollinations + static
                if not candidates:
                    raise RuntimeError("pollinations catalog returned no eligible models")
                self._snapshot = CatalogSnapshot(candidates=candidates)
                return self._snapshot
            except Exception as e:  # noqa: BLE001 — never fail routing on catalog trouble
                logger.warning("model_picker: catalog refresh failed (%s); serving stale/fallback", e)
                if snap is not None:
                    snap.stale = True
                    return snap
                self._snapshot = self._fallback_snapshot()
                return self._snapshot


def get_shared_manager() -> CatalogManager:
    """Process-wide manager.

    Shared state lives at module level because model_picker_plugin.py loads
    this file once under a fixed sys.modules key (see its _load_sibling) —
    both the routing-plugin and stats-logger instances get this same module
    object, so both see the same cache and stats.
    """
    global _shared_manager
    if _shared_manager is None:
        _shared_manager = CatalogManager()
    return _shared_manager


def get_shared_stats() -> StatsRegistry:
    global _shared_stats
    if _shared_stats is None:
        _shared_stats = StatsRegistry()
    return _shared_stats


def get_shared_prior_picks() -> "PriorPickRegistry":
    global _shared_prior_picks
    if _shared_prior_picks is None:
        _shared_prior_picks = PriorPickRegistry()
    return _shared_prior_picks


_shared_manager: CatalogManager | None = None
_shared_stats: StatsRegistry | None = None
_shared_prior_picks: "PriorPickRegistry | None" = None


class PriorPickRegistry:
    """Models already tried per in-flight request, keyed by litellm_call_id.

    litellm constructs the RoutingContext with a COPY of the request metadata
    (pydantic validates dicts into new objects), so the plugin cannot persist
    pick history through context.metadata. This registry is the shared channel:
    each retry attempt of the same request re-derives the same litellm_call_id
    and excludes the models this request already tried. Entries are bounded and
    age-evicted so abandoned requests cannot leak.
    """

    def __init__(self, max_entries: int = 1000, ttl_seconds: float = 600.0) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._by_call: dict[str, tuple[float, list[str]]] = {}

    def get(self, call_id: str, now: float | None = None) -> list[str]:
        if not call_id:
            return []
        entry = self._by_call.get(call_id)
        if entry is None:
            return []
        ts, picks = entry
        now = time.time() if now is None else now
        if now - ts > self.ttl_seconds:
            del self._by_call[call_id]
            return []
        return list(picks)

    def add(self, call_id: str, model_name: str, now: float | None = None) -> None:
        if not call_id:
            return
        now = time.time() if now is None else now
        entry = self._by_call.get(call_id)
        picks = list(entry[1]) if entry is not None else []
        picks.append(model_name)
        self._by_call[call_id] = (now, picks)
        while len(self._by_call) > self.max_entries:
            oldest = min(self._by_call, key=lambda k: self._by_call[k][0])
            del self._by_call[oldest]
