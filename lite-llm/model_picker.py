"""
Model Picker library: catalog snapshots, rubric ranking, and rolling stats.

Pure stdlib + httpx — deliberately free of litellm imports so it can be unit
tested and loaded standalone. Consumed by model_picker_plugin.py, which loads
this module via a sys.modules-guarded sibling loader (litellm's
``get_instance_fn`` exec's config-adjacent files without registering them in
``sys.modules``, so a plain ``import model_picker`` would neither resolve nor
share state across the plugin/stats-logger references).

Design (beads workspace-c8o, revised in workspace-4wr):

- Candidates: chat-capable models discovered live from every provider's
  catalog API — the pollinations listing (metric-backed; official and
  community both eligible, paid_only/down excluded, and only FREE models
  admitted: a nonzero pollen rate drops the model at parse time, exactly
  like llm7's free-only pool) plus NIM and LLM7 listings. NIM publishes no
  metrics and no pricing (metric-less; NIM filters non-chat families by
  id); all NIM models are treated as free, per the operator's assumption.
  LLM7 publishes availability telemetry, per-token pricing and context
  windows: only its FREE models (zero/absent pricing) are eligible, and
  those with availability telemetry rank as metric-backed on the
  published health. The picker only selects free models: parsers admit
  only free candidates, and rank_candidates additionally drops any
  non-free candidate, so a stale snapshot, the fallback snapshot, or a
  future provider cannot leak a paid model into a pick.
  Each provider's listing is served through a wildcard model_list entry
  (pollinations/*, nvidia_nim/*, llm7/*); a failed provider
  refresh keeps that provider's last-known candidates.
- Ranking classes: UNKNOWN (untried metric-less, favored — starts at the
  neutral prior (0.5, MODEL_PICKER_UNTRIED_PRIOR_SCORE), below healthy
  metric-backed candidates, so known-healthier models outrank it; the
  favored class still breaks ties and health blocks in its favor, and
  deprioritized providers such as llm7 start at the same prior but as
  METRIC, so they lose ties to other untried models), METRIC (published
  health, or our own tracked health once the group has observations),
  KNOWN (demoted while the current observation window proves it bad).
- Self-tracked health (workspace-4wr): once a metric-less group has
  observations it competes on the decayed, rate-limit-weighted success rate
  (Laplace-smoothed), so a sustained 429 streak (e.g. an llm7 daily token
  quota with a ~24h Retry-After) demotes it below healthy metric-backed
  candidates and real successes promote it back — no published metrics needed.
- Demotion proofs (re-derived from the rolling window on every evaluation, so
  recovery is automatic): >= MIN_OBS observations with derived hard-failure
  rate below best-metric-score minus margin; >= MIN_OBS streaming TTFT
  observations with decayed mean above the TTFT threshold; a single soft
  failure (provider error inside a 200 response — deterministic per
  model+account, so one observation is conclusive); or an AuthenticationError
  (dead until a success). Rate-limit failures never fire the hard proof
  (busy-but-working) but do weigh down the tracked score.
- Rubric: default tier filters first — hard health floor
  (MODEL_PICKER_MIN_HEALTH, default 0.3), then the top N% healthiest
  (MODEL_PICKER_HEALTH_TOP_PERCENT, default 25) — and picks the most
  capable model (highest modelgrep benchmark, then largest context) from
  the survivors, with health breaking ties; demoted models never enter the
  cohort. The think (COMPLEX) pool uses this same default rubric. Only
  ultra-think (REASONING) sorts context first, then modelgrep benchmark,
  then the health blocks (known-strong, untried, known-weak, demoted),
  then health. So on equal context and equal benchmark, demonstrated good
  health beats an unmeasured model; a higher-benchmark untried model
  still wins over a lower-benchmark known-strong one — but only on
  ultra-think. Latency-
  demoted models carry a class floor below all metric-backed candidates in
  the default tier.
- Learned health is durable: StatsRegistry can persist its per-group event
  logs to disk (MODEL_PICKER_STATS_PATH, or /config/.model-picker/ in the
  code-server container), so a LiteLLM restart does not reset a model to
  "untried". Per-request attempt exclusion still resets per request — that
  list is "models already tried in this request" — but a model that failed
  stays excluded in practice across turns because its persisted stats
  demote it; a literal forever ban on one transient failure would be wrong
  for a flaky upstream, so demotion still recovers on successes / decay.
- Recency guard: a candidate whose most recent observation is a failure within
  the recency window is skipped; one success restores eligibility.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger("model_picker")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLLINATIONS_MODELS_URL = "https://gen.pollinations.ai/v1/models"
NIM_MODELS_URL = "https://integrate.api.nvidia.com/v1/models"
LLM7_MODELS_URL = "https://api.llm7.io/v1/models"

# modelgrep.com aggregates benchmarks for 300+ models (Artificial Analysis,
# Design Arena). Keyless, edge-cached ~1h — it 403s default Python
# User-Agents, so the fetcher must identify itself.
MODELGREP_MODELS_URL = "https://modelgrep.com/api/v1/models"
MODELGREP_PAGE_LIMIT = 200
MODEL_PICKER_MODELGREP_USER_AGENT = "vscode-claude-model-picker/1.0 (catalog enrichment)"
DEFAULT_BENCHMARK_TTL_SECONDS = 3600.0

DEFAULT_TTL_SECONDS = 300.0
DEFAULT_MIN_OBS = 3
DEFAULT_DEMOTE_TTFT_SECONDS = 15.0
DEFAULT_DEMOTE_MARGIN = 0.02
DEFAULT_RECENCY_WINDOW_SECONDS = 60.0
DEFAULT_HALF_LIFE_SECONDS = 24 * 3600.0
# Cold-start/catastrophic fallback when the catalog is unreachable. Must be a
# community model verified to complete with the account's key (free-tier
# models are currently credit-gated server-side); revisit if it churns out of
# the catalog like its predecessor did.
DEFAULT_FALLBACK_MODEL = "community/vendouple/deepseek-v4-pro"
# Metric-less providers that must NOT get the untried benefit-of-the-doubt:
# llm7 has no published metrics and its groups trip daily token quotas (429 +
# ~24h Retry-After), so an untried llm7 group starts at a neutral prior below
# healthy metric-backed candidates instead of at the top of the list.
DEFAULT_DEPRIORITIZED_PROVIDERS = "llm7"
# Score an untried deprioritized-provider group competes with: below healthy
# metric-backed candidates (published wilson > 0.5), above zero-evidence ones.
DEFAULT_UNTRIED_PRIOR_SCORE = 0.5
# Health at or above this is "known strong" for the ultra-think tier's health
# blocks: well above the neutral 0.5 prior, so a model has to have actually
# demonstrated good health (published Wilson bound, or tracked success rate)
# to outrank an untried model there. Untried models still outrank known-but-weak
# health. (The default tier no longer uses health blocks; see below.)
DEFAULT_STRONG_HEALTH_THRESHOLD = 0.75
# Hard health floor for the default tier: a model below this is too unhealthy
# to be helpful and is filtered out before the capability pick. Lenient by
# design — a sanity gate, not a quality bar (the top-percent filter does the
# quality selection) — and below the 0.5 untried prior, so unmeasured models
# are not eliminated by the floor.
DEFAULT_MIN_HEALTH = 0.3
# Share of the healthiest default-tier candidates that survive to the
# capability pick: after the floor, only the top N% by health compete, and
# the most capable among them wins. With a ~30-model pool, 25% leaves about
# 8 finalists.
DEFAULT_HEALTH_TOP_PERCENT = 25.0
# Default durable stats location in the code-server container, where /config
# is the persistent volume. Overridden by MODEL_PICKER_STATS_PATH; when
# neither applies (local dev, tests), StatsRegistry stays in-memory unless
# a path is passed explicitly.
DEFAULT_STATS_PATH = "/config/.model-picker/model_picker_stats.json"

CATALOG_FETCH_TIMEOUT_SECONDS = 10.0



def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default
    return default if value != value else value  # NaN is never a usable knob


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, TypeError, ValueError):
        return default


def _clamp(value: object, lo: float, hi: float, default: float) -> float:
    """Clamp a config value into [lo, hi]; non-numeric or NaN falls back to default."""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return min(hi, max(lo, v))


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
        self.strong_health_threshold = _env_float(
            "MODEL_PICKER_STRONG_HEALTH_THRESHOLD", DEFAULT_STRONG_HEALTH_THRESHOLD
        )
        self.min_health = _env_float("MODEL_PICKER_MIN_HEALTH", DEFAULT_MIN_HEALTH)
        self.health_top_percent = _env_float(
            "MODEL_PICKER_HEALTH_TOP_PERCENT", DEFAULT_HEALTH_TOP_PERCENT
        )
        self.modelgrep_url = os.environ.get("MODEL_PICKER_MODELGREP_URL", MODELGREP_MODELS_URL)
        self.benchmark_ttl_seconds = _env_float("MODEL_PICKER_BENCHMARK_TTL_SECONDS", DEFAULT_BENCHMARK_TTL_SECONDS)
        self.benchmarks_enabled = os.environ.get("MODEL_PICKER_BENCHMARKS_OFF", "").strip().lower() not in ("1", "true", "yes", "on")


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
    provider: str  # pollinations | nvidia_nim | llm7
    context_length: int = 0  # 0 = unknown (bypasses fit filtering)
    metricless: bool = True  # no published metrics -> favored while UNKNOWN
    success_rate: float = 1.0  # published 0..1 (placeholder for metric-less)
    requests: int = 0  # published sample size
    available: bool = True  # False when the provider's catalog dropped it
    source: str = "prior"  # pollinations_api | prior
    free: bool = False  # True when the model is free-tier: pollinations zero
    # pollen rate, all NIM models (no pricing in NIM's catalog; treated as
    # free per the operator's assumption), llm7 zero pricing. Unknown or
    # priced models default to not-free and are never picked.
    benchmark_score: float = 0.0  # 0..1 modelgrep composite (coding, tool calling, SWE)
    benchmarked: bool = False  # False when modelgrep has no scores for the match
    modelgrep_id: str = ""  # matched modelgrep entry ("" when unmatched -> gated out)

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


def has_free_pricing(pricing: dict | None) -> bool:
    """True when no nonzero pollen rate is declared anywhere.

    Missing or rate-less pricing counts as free: nothing is charged per token.
    """
    for key, value in (pricing or {}).items():
        if key == "currency":
            continue
        try:
            if float(value) > 0:
                return False
        except (TypeError, ValueError):
            continue
    return True


def parse_pollinations_models(payload: dict) -> list[ModelCandidate]:
    """Parse GET /v1/models from pollinations into free chat-capable candidates.

    Official and community models are both eligible; the catalog's pricing
    metadata discerns free-tier models (no nonzero pollen rate), which the
    pollinations backend currently gates behind account credits — sometimes
    even spuriously. Only free-tier models are admitted: a nonzero pollen
    rate drops the model here, not just flags it — the picker only selects
    free models, and the soft-failure sniffing in the stats logger handles
    the credit gating dynamically for the free models that remain.
    """
    out: list[ModelCandidate] = []
    for m in (payload or {}).get("data") or []:
        if not isinstance(m, dict):
            continue
        model_id = m.get("id") or ""
        if not model_id:
            continue
        if m.get("paid_only"):
            continue
        if not has_free_pricing(m.get("pricing")):
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
                free=has_free_pricing(m.get("pricing")),
            )
        )
    return out


# ---------------------------------------------------------------------------
# NIM's catalog lists every hosted model — embeddings, retrievers, vision,
# guard/reward models — with no modality metadata. Exclude the non-chat
# families by id substring; anything chatty that slips through is sorted out
# by the health tracking after a few real requests.
_NIM_NON_CHAT_SUBSTRINGS = (
    "embed",
    "rerank",
    "retriever",
    "guard",
    "safety",
    "reward",
    "clip",
    "vision",
    "deplot",
    "nemotron-parse",
    "riva",
    "diffusion",
    "video-detector",
    "kosmos",
    "neva",
    "vila",
    "fuyu",
    "synthetic",
)


def _is_nim_chat_model(model_id: str) -> bool:
    lowered = model_id.lower()
    return not any(marker in lowered for marker in _NIM_NON_CHAT_SUBSTRINGS)


def _bare_catalog_entries(payload: dict | list) -> list[dict]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    return [m for m in (data or []) if isinstance(m, dict) and m.get("id")]


def parse_nim_models(payload: dict | list) -> list[ModelCandidate]:
    """Parse NIM's /v1/models into chat-capable metric-less candidates.

    NIM's catalog carries no pricing, so every admitted model is treated
    as free (operator assumption): the picker only selects free models,
    and NIM is the free-tier provider in this deployment.
    """
    out: list[ModelCandidate] = []
    for m in _bare_catalog_entries(payload):
        model_id = str(m["id"])
        if not _is_nim_chat_model(model_id):
            continue
        out.append(
            ModelCandidate(
                name=f"nvidia_nim/{model_id}",
                provider="nvidia_nim",
                context_length=int(m.get("context_length") or 0),
                metricless=True,
                source="prior",
                free=True,
            )
        )
    return out


def _llm7_published_health(model: dict) -> float | None:
    """Published availability for one LLM7 model, as 0..1 (None when absent).

    Blends the catalog's telemetry: the last-hour percentage dominates, then
    the availability buckets (recent/mid/old). Weights renormalize over
    whatever the catalog provides.
    """
    availability = model.get("availability") or {}
    parts = (
        (0.5, model.get("availability_last_hour_percent")),
        (0.2, availability.get("recent")),
        (0.2, availability.get("mid")),
        (0.1, availability.get("old")),
    )
    weighted = [(w, v) for w, v in parts if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not weighted:
        return None
    total_weight = sum(w for w, _ in weighted)
    return sum(w * v for w, v in weighted) / total_weight / 100.0


# LLM7's availability telemetry is aggregated server-side without sample
# counts; treat each published figure as a modest-size sample so the Wilson
# lower bound stays conservative around the true rate.
_LLM7_PUBLISHED_SAMPLE_SIZE = 100


def parse_llm7_models(payload: dict | list) -> list[ModelCandidate]:
    """Parse LLM7's /v1/models into free chat-capable candidates.

    LLM7's catalog carries rich metadata: model_type (chat/image/audio/...),
    schema_endpoints, an advertised context window, per-token pricing, and
    availability telemetry. Only OpenAI-endpoint chat models qualify, and
    only FREE ones (zero/absent per-token pricing, the same discernment as
    pollinations) — every currently-listed model is metered, so this pool is
    empty until llm7 lists a free model; that is intentional. Admitted
    models with availability telemetry rank as metric-backed (like
    pollinations' success_rate) instead of riding the metric-less favorite
    boost.
    """
    out: list[ModelCandidate] = []
    for m in _bare_catalog_entries(payload):
        if m.get("model_type") not in (None, "chat"):
            continue
        endpoints = m.get("schema_endpoints") or []
        if endpoints and "openai" not in endpoints:
            continue
        pricing = m.get("pricing")
        if not has_free_pricing(pricing):
            continue
        context_window = m.get("context_window") or {}
        health = _llm7_published_health(m)
        out.append(
            ModelCandidate(
                name=f"llm7/{m['id']}",
                provider="llm7",
                context_length=int(context_window.get("tokens") or 0),
                metricless=health is None,
                success_rate=health if health is not None else 0.0,
                requests=_LLM7_PUBLISHED_SAMPLE_SIZE if health is not None else 0,
                source="prior",
                free=True,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Modelgrep enrichment: benchmark metadata + pool gating
# ---------------------------------------------------------------------------


async def fetch_modelgrep_catalog(url: str) -> list[dict]:
    """Fetch every model entry from modelgrep (paginated).

    modelgrep 403s default Python User-Agents, so the client must identify
    itself. Entries are the raw /models list objects (id, benchmarks, ...).
    """
    import httpx

    entries: list[dict] = []
    offset = 0
    async with httpx.AsyncClient(
        timeout=CATALOG_FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": MODEL_PICKER_MODELGREP_USER_AGENT},
        follow_redirects=True,
    ) as client:
        for _ in range(8):  # hard page cap — 364 models fit in two pages today
            resp = await client.get(url, params={"limit": MODELGREP_PAGE_LIMIT, "offset": offset})
            resp.raise_for_status()
            page = resp.json()
            data = [m for m in (page.get("data") or []) if isinstance(m, dict) and m.get("id")]
            entries += data
            meta = page.get("meta") or {}
            if not meta.get("has_more") or not data:
                break
            offset = int(meta.get("next_offset") or 0)
    return entries


def modelgrep_benchmark_score(entry: dict) -> tuple[float, bool]:
    """0..1 composite of coding, tool-calling, and software-engineering scores.

    Prefers the *_pct percentile fields (already 0..100 across heterogeneous
    raw scales); falls back to the raw Artificial Analysis figures, where
    indexes run 0..100 and fractions (terminalbench, tau2, scicode,
    livecodebench) run 0..1. Averages whatever components exist; (0.0, False)
    when the entry has none.
    """
    aa = (entry.get("benchmarks") or {}).get("artificial_analysis") or {}

    def pct(v):
        return v / 100.0 if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def raw(v):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return None
        return v / 100.0 if v > 1.0 else float(v)

    def first(*values):
        for v in values:
            if v is not None:
                return v
        return None

    coding = first(pct(aa.get("coding_pct")), raw(aa.get("coding")), raw(aa.get("livecodebench")))
    tool_calling = first(pct(aa.get("agentic_pct")), raw(aa.get("agentic")), raw(aa.get("tau2")))
    swe = first(pct(aa.get("terminalbench_pct")), raw(aa.get("terminalbench")), raw(aa.get("scicode")))
    parts = [p for p in (coding, tool_calling, swe) if p is not None]
    if not parts:
        return 0.0, False
    return sum(parts) / len(parts), True


# Name matching. Strict by design: a wrong mapping silently mis-ranks a
# model, which is worse than dropping it. The pipeline tries alias variants
# of the candidate's upstream id in decreasing confidence order, then a
# structured family resolver guarded by version/variant/size equality.
# Only when every strict stage fails does the bidirectional-substring
# fallback run: a candidate matches an entry when either normalized bare
# segment contains the other on token boundaries. That rescues relay names
# carrying vendor prefixes (vercel-nemotron-3.5-lightning -> the
# nemotron-3.5-lightning entry), but it is deliberately unique-hit-only
# (with maker disambiguation) so a generic fragment can never silently
# claim an ambiguous model — and it relaxes the variant guard by design:
# a bare -flash relay now matches a -flash-lite entry when that is the
# unique substring hit.
# Dashless equality runs between the alias loop and the family stage: a
# candidate alias form and an entry id/segment are compared with dashes
# removed, so a provider spelling with different word boundaries
# (Nemotron3.5Lightning) still equals its entry. It is equality, not
# containment, so the variant guard survives (flash != flash-lite) and
# the dashed tokenization the family stage depends on is untouched.
# Unique-hit-only, with maker disambiguation for segment hits, so a
# dashless collision across entries (3-1 vs 31) gates out instead of
# picking one arbitrarily.
_NAME_SEPARATORS = re.compile(r"[\s_:]+")
_NAME_SEPARATORS_KEEPING_DOTS = re.compile(r"[\s_]+")
_NAME_COLLAPSE = re.compile(r"-{2,}")
_DATE_STAMP = re.compile(r"-(\d{4})$")
# serving decorations stripped ONLY when the decorated name has no exact
# match — flash/lite/mini/nano/ultra etc. are NOT here on purpose: they name
# different models
_DECORATION_SUFFIXES = (
    "free",
    "instruct",
    "it",
    "chat",
    "latest",
    "turbo",
    "bf16",
    "cloud",
)
_MAKER_ALIASES = {
    "deepseek-ai": "deepseek",
    "meta": "meta-llama",
    "xai": "x-ai",
}
_SIZE_TOKEN = re.compile(r"^[a-z]?\d+b$")


def _norm_name(name: str) -> str:
    """Canonical comparison form: lowercase, unified separators, collapsed."""
    lowered = name.strip().lower()
    lowered = _NAME_SEPARATORS.sub("-", lowered)
    # versions: dots and dashes are the same model across providers
    lowered = lowered.replace(".", "-")
    return _NAME_COLLAPSE.sub("-", lowered)


def _dashless(name: str) -> str:
    """Separator-free comparison form: _norm_name with dashes removed."""
    return _norm_name(name).replace("-", "")


def _strip_decorations(segment: str) -> list[str]:
    """Progressively less-decorated variants of a model segment (most stripped last)."""
    variants = [segment]
    current = segment
    for _ in range(6):
        stripped = None
        m = _DATE_STAMP.search(current)
        if m:
            stripped = current[: m.start()] or None
        else:
            for suffix in _DECORATION_SUFFIXES:
                if current.endswith("-" + suffix):
                    stripped = current[: -(len(suffix) + 1)]
                    break
        if not stripped or stripped == current:
            break
        current = stripped
        variants.append(current)
    return variants


def _alias_maker(id_or_segment: str) -> str:
    parts = id_or_segment.split("/")
    parts[0] = _MAKER_ALIASES.get(parts[0], parts[0])
    return "/".join(parts)


def _candidate_aliases(upstream_id: str) -> list[tuple[str, float, str]]:
    """(alias, confidence, stage) variants of the upstream id, best first."""
    seen: set[str] = set()
    out: list[tuple[str, float, str]] = []

    def add(alias: str, confidence: float, stage: str) -> None:
        if alias and alias not in seen:
            seen.add(alias)
            out.append((alias, confidence, stage))

    norm = _norm_name(upstream_id)
    add(norm, 1.0, "exact")
    add(_norm_name(_alias_maker(upstream_id)), 0.95, "maker-alias")

    # decoration stripping on the full id and its trailing segment
    segments = upstream_id.split("/")
    for variant in _strip_decorations(segments[-1]):
        if len(segments) > 1:
            add(_norm_name("/".join(segments[:-1] + [variant])), 0.85, "decoration")
        add(_norm_name(_alias_maker("/".join(segments[:-1] + [variant]))), 0.85, "decoration")
        add(_norm_name(variant), 0.7, "decoration-segment")

    # community/vendor prefix stripping (community/<user>/<model>, <vendor>/<model>)
    for drop in (1, 2):
        if len(segments) > drop:
            tail = "/".join(segments[drop:])
            add(_norm_name(tail), 0.6, f"prefix{drop}")
            add(_norm_name(_alias_maker(tail)), 0.6, f"prefix{drop}")
            tail_segments = tail.split("/")
            for variant in _strip_decorations(tail_segments[-1]):
                if len(tail_segments) > 1:
                    add(_norm_name("/".join(tail_segments[:-1] + [variant])), 0.6, f"prefix{drop}-decoration")
                add(_norm_name(variant), 0.55, f"prefix{drop}-decoration-segment")
    return out


def _segment_key(segment: str) -> tuple:
    """(alpha-tokens, version-tokens, size-tokens) of a normalized segment."""
    alpha: list[str] = []
    version: list[str] = []
    size: list[str] = []
    for token in _norm_name(segment).split("-"):
        if not token:
            continue
        if _SIZE_TOKEN.match(token):
            size.append(token)
        elif any(ch.isdigit() for ch in token):
            version.append(token)
        else:
            alpha.append(token)
    return tuple(alpha), tuple(version), tuple(size)


def _size_rank(size_tokens: tuple[str, ...]) -> float:
    """Sort key for size-decorated siblings: prefer the biggest parameter count."""
    best = 0.0
    for token in size_tokens:
        m = re.search(r"(\d+)", token)
        if m:
            best = max(best, float(m.group(1)))
    return best


def _boundary_contains(haystack: str, needle: str) -> bool:
    """True when needle occurs in haystack on '-' or '/' boundaries.

    Equality, a leading segment, a trailing segment, or a middle segment
    all count; a mid-token occurrence (beam in sunbeam) does not.
    """
    if not needle or needle not in haystack:
        return False
    if haystack == needle:
        return True
    if haystack.startswith(needle + "-") or haystack.startswith(needle + "/"):
        return True
    if haystack.endswith("-" + needle) or haystack.endswith("/" + needle):
        return True
    return ("-" + needle + "-") in haystack or ("/" + needle + "/") in haystack


class ModelGrepIndex:
    """Lookup structures over modelgrep entries for candidate matching."""

    def __init__(self, entries: list[dict]) -> None:
        self._by_id: dict[str, dict] = {}
        self._by_segment: dict[str, list[dict]] = {}
        self._by_dashless_id: dict[str, list[dict]] = {}
        self._by_dashless_segment: dict[str, list[dict]] = {}
        self._by_key: dict[tuple, list[dict]] = {}
        self._entry_forms: list[tuple[dict, str, str]] = []
        for entry in entries:
            mg_id = str(entry.get("id") or "")
            if not mg_id:
                continue
            norm_id = _norm_name(mg_id)
            self._by_id[norm_id] = entry
            segment = norm_id.split("/")[-1]
            self._by_segment.setdefault(segment, []).append(entry)
            self._by_dashless_id.setdefault(_dashless(norm_id), []).append(entry)
            self._by_dashless_segment.setdefault(_dashless(segment), []).append(entry)
            self._by_key.setdefault(_segment_key(segment), []).append(entry)
            self._entry_forms.append((entry, segment, norm_id))

    def _by_full_id(self, alias: str) -> dict | None:
        return self._by_id.get(alias)

    def _by_bare_segment(self, alias: str) -> dict | None:
        """Unique-segment match: bare aliases (community-relayed names) must
        resolve unambiguously or not at all."""
        hits = self._by_segment.get(alias.split("/")[-1]) or []
        return hits[0] if len(hits) == 1 else None

    def match(self, upstream_id: str) -> tuple[dict | None, str, float]:
        """Match one upstream id -> (entry, stage, confidence).

        entry is None when nothing matches within the guarded rules (the
        caller gates the candidate out). Version/variant/size equality is
        enforced in the family stage, so glm-5.3 can never match glm-5.2.
        The dashless-equality stage runs after the whole alias loop, so
        it can never override an exact, decoration, or prefix hit, and
        before family, so a true equality beats a family resemblance.
        The substring fallback runs last, after every strict stage, and
        matches bidirectionally on token boundaries — so a -flash relay
        can match a -flash-lite entry when that is the unique substring
        hit. See the module comment above for the rationale.
        """
        for alias, confidence, stage in _candidate_aliases(upstream_id):
            hit = self._by_full_id(alias) if "/" in alias else None
            if hit is None:
                hit = self._by_bare_segment(alias)
            if hit is not None:
                return hit, stage, confidence
        # Dashless equality: same model spelled with different word
        # boundaries or casing (Nemotron3.5Lightning -> the
        # nemotron-3.5-lightning entry). Unique-hit-only, with maker
        # disambiguation for segment hits; ambiguity gates out.
        dash, dash_ambiguous = self._dashless_match(upstream_id)
        if dash is not None:
            return dash, "dashless", 0.9
        # structured family resolution: exact (alpha, version, size) equality,
        # with the bare-generation -> size-decorated sibling allowance
        key = _segment_key(upstream_id.split("/")[-1])
        hits = self._by_key.get(key) or []
        hits = self._disambiguate_by_maker(hits, upstream_id)
        if len(hits) == 1:
            return hits[0], "family", 0.75
        if not hits and not key[2]:
            siblings = self._disambiguate_by_maker(self._entries_with_size(key), upstream_id)
            if len(siblings) == 1:
                return siblings[0], "family-size-sibling", 0.5
            if len(siblings) > 1:
                # deterministic: prefer the largest parameter count
                best = max(siblings, key=lambda e: _size_rank(_segment_key(str(e.get("id") or "").split("/")[-1])[2]))
                return best, "family-size-sibling-multi", 0.45
        # Bidirectional-substring fallback, last: the entry's bare segment
        # contains the candidate's (vendor-prefixed relays), or the
        # candidate's contains the entry's, on token boundaries. Unique
        # hits only — ambiguity still gates out.
        sub, sub_ambiguous = self._substring_match(upstream_id)
        if sub is not None:
            return sub, "substring", 0.4
        return None, ("ambiguous" if len(hits) > 1 or dash_ambiguous or sub_ambiguous else "unmatched"), 0.0

    def _dashless_match(self, upstream_id: str) -> tuple[dict | None, bool]:
        """Dashless equality on the candidate's alias forms.

        Each form is compared with dashes removed, against both the
        entry's dashless full id (when the form carries a path) and its
        dashless bare segment. Full-id hits must be unique; segment hits
        may be narrowed by maker, otherwise ambiguity gates out.
        Forms are the alias loop's aliases plus decoration-stripped
        variants of the normalized bare segment — stripping after
        normalization, so a colon-suffixed :free relay strips correctly
        too (the alias loop strips the raw segment, where :free is not
        a -free suffix). Returns (entry, ambiguous).
        """
        forms: list[str] = []
        seen: set[str] = set()
        for alias, _confidence, _stage in _candidate_aliases(upstream_id):
            if alias not in seen:
                seen.add(alias)
                forms.append(alias)
        bare = _norm_name(upstream_id.split("/")[-1])
        for variant in _strip_decorations(bare):
            if variant not in seen:
                seen.add(variant)
                forms.append(variant)
        ambiguous = False
        for form in forms:
            if "/" in form:
                hits = self._by_dashless_id.get(_dashless(form)) or []
                if len(hits) == 1:
                    return hits[0], False
                if len(hits) > 1:
                    ambiguous = True
            seg_hits = self._by_dashless_segment.get(_dashless(form.split("/")[-1])) or []
            if seg_hits:
                narrowed = self._disambiguate_by_maker(seg_hits, upstream_id)
                if len(narrowed) == 1:
                    return narrowed[0], False
                ambiguous = True
        return None, ambiguous

    def _substring_match(self, upstream_id: str) -> tuple[dict | None, bool]:
        """Bidirectional token-boundary substring match on the bare segment.

        Variants are the normalized bare segment plus its decoration-stripped
        forms (stripping after normalization, so colon-suffixed :free relays
        strip correctly too). A variant matches an entry when either side
        contains the other on a '-' or '/' boundary, and the shorter side
        is at least 4 chars, so 1-3 char fragments cannot claim a model.
        Returns (entry, ambiguous): ambiguous is True when some variant hit
        several entries that maker disambiguation could not narrow to one.
        """
        variants: list[str] = []
        seen: set[str] = set()
        bare = _norm_name(upstream_id.split("/")[-1])
        for variant in _strip_decorations(bare):
            if variant and variant not in seen and len(variant) >= 4:
                seen.add(variant)
                variants.append(variant)
        ambiguous = False
        for variant in variants:
            hits: list[dict] = []
            for entry, segment, full_id in self._entry_forms:
                if len(segment) < 4:
                    continue
                if (
                    _boundary_contains(segment, variant)
                    or _boundary_contains(variant, segment)
                    or _boundary_contains(full_id, variant)
                ):
                    hits.append(entry)
            if len(hits) == 1:
                return hits[0], False
            if len(hits) > 1:
                narrowed = self._disambiguate_by_maker(hits, upstream_id)
                if len(narrowed) == 1:
                    return narrowed[0], False
                ambiguous = True
        return None, ambiguous

    @staticmethod
    def _maker_of(entry: dict) -> str:
        return str(entry.get("maker") or (str(entry.get("id") or "").split("/")[0]))

    @staticmethod
    def _candidate_maker(upstream_id: str) -> str | None:
        parts = upstream_id.split("/")
        if len(parts) < 2:
            return None
        return _MAKER_ALIASES.get(parts[0], parts[0])

    def _disambiguate_by_maker(self, hits: list[dict], upstream_id: str) -> list[dict]:
        """Prefer hits whose maker matches the candidate's, when it has one."""
        if len(hits) <= 1:
            return hits
        maker = self._candidate_maker(upstream_id)
        if maker is None:
            return hits
        by_maker = [e for e in hits if self._maker_of(e) == maker]
        return by_maker or hits

    def _entries_with_size(self, key: tuple) -> list[dict]:
        """Entries sharing alpha+version but carrying size decorations."""
        out: list[dict] = []
        for k, entries in self._by_key.items():
            if k[0] == key[0] and k[1] == key[1] and k[2]:
                out += entries
        return out

FAILURE_CLASS_AUTH = "auth"
FAILURE_CLASS_RATE_LIMIT = "rate_limit"
FAILURE_CLASS_TIMEOUT = "timeout"
FAILURE_CLASS_CONNECTION = "connection"
FAILURE_CLASS_ERROR = "error"
# Provider errors smuggled through HTTP 200 message content (credits gate,
# relayed upstream errors). Deterministic per model+account — one observation
# is conclusive — so the demotion proof fires on the first one.
FAILURE_CLASS_SOFT = "soft"

# 429 = busy-but-working: mild penalty, fast recovery. Everything else is a
# full failure. Auth additionally dead-marks the group until a success.
_FAILURE_WEIGHTS = {
    FAILURE_CLASS_AUTH: 1.0,
    FAILURE_CLASS_RATE_LIMIT: 0.25,
    FAILURE_CLASS_TIMEOUT: 1.0,
    FAILURE_CLASS_CONNECTION: 1.0,
    FAILURE_CLASS_ERROR: 1.0,
    FAILURE_CLASS_SOFT: 1.0,
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


# Pollinations (and some community relays) return hard failures as HTTP 200
# with the error text as the assistant message content, so the callback
# pipeline reports a "success" and nothing ever demotes the model. The stats
# logger sniffs these markers and records the event as a failure instead.
#
# Single-factor markers are exact phrases that cannot plausibly appear in a
# legitimate answer, so they alone are conclusive. The two-factor rule below
# covers everything else: an explicit all-zero usage block (real completions
# bill tokens) plus any broad error-lexicon word in the content.
_SOFT_FAILURE_MARKERS = (
    "doesn't have enough credits",  # pollinations account credit gate
    "does not have enough credits",  # straight-apostrophe variant
    "insufficient credits",
    "quota exceeded",
    "please top up",
)
_SOFT_FAILURE_PREFIXES = (
    "[error:",  # relayed upstream errors, e.g. "[Error: Z.ai returned 403: ..."
    "[exception:",
)
# Broad error vocabulary for the two-factor rule. Any ONE of these words in
# the content satisfies the lexical factor — they appear in practically every
# provider error stub, but a legitimate answer carrying an error word is
# harmless because the structural factor (zero usage) must also fire.
_ERROR_LEXICON = (
    "error",
    "exception",
    "credit",
    "quota",
    "top up",
    "top-up",
    "try again",
    "unavailable",
    "api key",
    "account",
    "rate limit",
    "ratelimit",
    "invalid",
    "denied",
    "expired",
    "exceeded",
    "forbidden",
    "billing",
    "payment",
    "subscription",
    "temporarily",
    "upstream",
    "returned 4",
    "returned 5",
    "http 4",
    "http 5",
)


def _anthropic_content_text(content: object) -> str:
    """Text from anthropic-shaped content blocks (objects, dicts, or strings)."""
    parts: list[str] = []
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
    return "\n".join(p for p in parts if p)


def extract_response_text(response_obj: object) -> str:
    """Best-effort assistant text from a litellm response object ("" if none).

    Handles both shapes seen at the proxy boundary: OpenAI-style
    ``choices[].message.content`` and anthropic-style ``content`` blocks (the
    /v1/messages route hands post-translation objects to hooks).
    """
    try:
        if isinstance(response_obj, dict):
            # plain-dict responses (the /v1/messages route hands translated
            # anthropic dicts to hooks) — getattr misses dict keys entirely
            content = response_obj.get("content")
            if content is not None:
                text = _anthropic_content_text(content)
                if text:
                    return text
            for choice in response_obj.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message") or choice.get("delta") or {}
                if isinstance(message, dict):
                    text = _anthropic_content_text(message.get("content"))
                    if text:
                        return text
            return ""
        content = getattr(response_obj, "content", None)
        if content is not None:
            text = _anthropic_content_text(content)
            if text:
                return text
        parts: list[str] = []
        for choice in getattr(response_obj, "choices", None) or []:
            message = getattr(choice, "message", None) or getattr(choice, "delta", None)
            content = getattr(message, "content", None) if message is not None else None
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, str):
                        parts.append(part)
                    elif isinstance(part, dict) and isinstance(part.get("text"), str):
                        parts.append(part["text"])
        return "\n".join(p for p in parts if p)
    except Exception:  # noqa: BLE001 — sniffing must never break logging
        return ""


def is_soft_failure_content(text: str | None) -> bool:
    """Detect provider errors smuggled through as successful message content."""
    if not text:
        return False
    normalized = text.strip().lower().replace("’", "'").replace("‘", "'")
    if normalized.startswith(_SOFT_FAILURE_PREFIXES):
        return True
    return any(marker in normalized for marker in _SOFT_FAILURE_MARKERS)


def _usage_values(usage: object) -> list[float]:
    """Numeric usage fields from a Usage object or dict ([] when absent)."""
    values: list[float] = []
    if usage is None:
        return values
    if isinstance(usage, dict):
        for value in usage.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append(float(value))
        return values
    for attr in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
        value = getattr(usage, attr, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return values


def explicit_zero_usage(response_obj: object) -> bool:
    """True when the response carries a usage block that is present and all-zero.

    The distinguishing gate signature: providers short-circuit before
    generation, so the stub reports zero tokens. Usage that is ABSENT (some
    providers legitimately omit it) does not count.
    """
    usage = None
    if isinstance(response_obj, dict):
        usage = response_obj.get("usage")
    else:
        usage = getattr(response_obj, "usage", None)
    values = _usage_values(usage)
    if not values:
        return False
    return all(v == 0.0 for v in values)


def has_error_lexicon(text: str | None) -> bool:
    """Broad lexical hint of provider-error content (the 2nd factor)."""
    if not text:
        return False
    lowered = text.lower()
    return any(word in lowered for word in _ERROR_LEXICON)


def is_soft_failure_response(text: str | None, response_obj: object) -> bool:
    """Two-factor soft-failure check over content text plus response metadata.

    Fires on: a single-factor exact marker, OR the structural anomaly
    (explicit all-zero usage — real completions bill tokens) combined with
    any broad error-lexicon word in the content. The two-factor rule needs
    the full response, so it applies to non-streaming responses and to the
    success-event log (demotion); streaming interception stays text-only
    because usage arrives after the content has already been yielded.
    """
    if is_soft_failure_content(text):
        return True
    if not text:
        return False
    return explicit_zero_usage(response_obj) and has_error_lexicon(text)


@dataclass
class DerivedStats:
    """Decayed aggregates for one group."""

    success_rate: float = 1.0  # decayed successes / (successes + weighted failures)
    hard_rate: float = 1.0  # success rate over HARD failures only (429s excluded)
    successes: float = 0.0  # decayed success mass in the window
    failures: float = 0.0  # decayed weighted failure mass (429s count 0.25)
    soft_failures: int = 0  # in-window count of soft (200-with-error-content) failures
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
        soft_failures = 0
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
                if failure_class == FAILURE_CLASS_SOFT:
                    soft_failures += 1
        denom = successes + failures
        hard_denom = successes + hard_failures
        last_age = (now - self.last_obs_ts) if self.last_obs_ts is not None else float("inf")
        return DerivedStats(
            success_rate=(successes / denom) if denom > 0 else 1.0,
            hard_rate=(successes / hard_denom) if hard_denom > 0 else 1.0,
            successes=successes,
            failures=failures,
            soft_failures=soft_failures,
            n_obs=n_obs,
            ttft_mean=(ttft_weighted_sum / ttft_weight) if ttft_weight > 0 else 0.0,
            ttft_n=ttft_n,
            dead=self.dead,
            demoted=self.demoted,
            last_obs_age=last_age,
            last_obs_was_failure=self.last_obs_was_failure,
        )


def default_stats_path() -> str | None:
    """Durable stats path for this deployment, or None for in-memory only.

    Explicit env wins; otherwise the code-server container's persistent
    /config volume is used when present. Anywhere else (local dev, tests)
    the default is in-memory, so nothing is written to the repo by accident.
    """
    env_path = os.environ.get("MODEL_PICKER_STATS_PATH", "").strip()
    if env_path:
        return env_path
    if os.path.isdir("/config"):
        return DEFAULT_STATS_PATH
    return None


class StatsRegistry:
    """Per-group rolling stats shared by the plugin and the stats logger.

    Optionally durable: when ``path`` is set (explicitly, or via
    ``default_stats_path()`` for the shared registry), every recorded event
    is flushed to a JSON file atomically (temp file + os.replace), and the
    file is reloaded on construction. Persistence is fail-soft — a bad path
    or corrupt file logs a warning and falls back to in-memory stats, never
    breaking routing. The file holds only per-model aggregate event data
    (timestamps, success/failure class, TTFT); no prompts, responses, or
    credentials.
    """

    def __init__(
        self,
        half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS,
        path: str | None = None,
    ) -> None:
        self.half_life_seconds = half_life_seconds
        self.path = path
        self._groups: dict[str, GroupStats] = {}
        # Upstream-proven context windows, per group: a catalog window is
        # a claim, and catalogs lie (minimax-m3.1-flash claims 1,048,576
        # while NIM serves it at 262,144). A context_length 400 proves the
        # real limit, so it is recorded here and used as the fit filter's
        # effective window from then on — the lie costs one failed
        # request per model, not every oversized request forever.
        self._learned_windows: dict[str, int] = {}
        if path:
            self._load()

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                payload = json.load(f)
            groups = payload.get("groups") if isinstance(payload, dict) else None
            if not isinstance(groups, dict):
                return
            for name, data in groups.items():
                if not isinstance(name, str) or not isinstance(data, dict):
                    continue
                stats = GroupStats(self.half_life_seconds)
                events = data.get("events") or []
                for event in events:
                    if not isinstance(event, list) or len(event) != 4:
                        continue
                    ts, ok, ttft, failure_class = event
                    if not isinstance(ts, (int, float)) or not isinstance(ok, bool):
                        continue
                    stats._events.append(
                        (
                            float(ts),
                            ok,
                            float(ttft) if isinstance(ttft, (int, float)) else None,
                            str(failure_class) if isinstance(failure_class, str) else None,
                        )
                    )
                stats.dead = bool(data.get("dead", False))
                stats.demoted = bool(data.get("demoted", False))
                last_ts = data.get("last_obs_ts")
                stats.last_obs_ts = float(last_ts) if isinstance(last_ts, (int, float)) else None
                stats.last_obs_was_failure = bool(data.get("last_obs_was_failure", False))
                self._groups[name] = stats
            learned = payload.get("learned_windows") if isinstance(payload, dict) else None
            if isinstance(learned, dict):
                for name, limit in learned.items():
                    if isinstance(name, str) and isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
                        self._learned_windows[name] = limit
        except FileNotFoundError:
            pass
        except Exception as e:  # noqa: BLE001 — corrupt stats must never break routing
            logger.warning("model_picker: stats file %s unreadable (%s); starting fresh", self.path, e)

    def _save(self) -> None:
        if not self.path:
            return
        try:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            payload = {
                "version": 1,
                "learned_windows": dict(self._learned_windows),
                "groups": {
                    name: {
                        "events": [
                            [ts, ok, ttft, failure_class] for ts, ok, ttft, failure_class in stats._events
                        ],
                        "dead": stats.dead,
                        "demoted": stats.demoted,
                        "last_obs_ts": stats.last_obs_ts,
                        "last_obs_was_failure": stats.last_obs_was_failure,
                    }
                    for name, stats in self._groups.items()
                },
            }
            tmp_path = f"{self.path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            os.replace(tmp_path, self.path)
        except Exception as e:  # noqa: BLE001 — persistence must never break routing
            logger.warning("model_picker: could not save stats to %s (%s)", self.path, e)

    def group(self, name: str) -> GroupStats:
        stats = self._groups.get(name)
        if stats is None:
            stats = GroupStats(self.half_life_seconds)
            self._groups[name] = stats
        return stats

    def record_success(self, name: str, ttft_seconds: float | None = None, now: float | None = None) -> None:
        if not name:
            return
        self.group(name).record_success(time.time() if now is None else now, ttft_seconds)
        self._save()

    def record_failure(self, name: str, failure_class: str, now: float | None = None) -> None:
        if not name:
            return
        self.group(name).record_failure(time.time() if now is None else now, failure_class)
        self._save()

    def record_context_limit(self, name: str, limit: int) -> None:
        """Record an upstream-proven context window for a group.

        The minimum wins: if a provider ever reports a smaller limit,
        that is the binding constraint for fit filtering.
        """
        if not name or not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            return
        previous = self._learned_windows.get(name)
        if previous is None or limit < previous:
            self._learned_windows[name] = limit
            self._save()

    def learned_window(self, name: str) -> int | None:
        return self._learned_windows.get(name)

    def effective_window(self, candidate: "ModelCandidate") -> int:
        """Window the fit filter trusts: the smaller of catalog and learned.

        A learned window never widens a catalog window — upstream proved
        the smaller number, and a catalog claim above it is exactly the
        lie that 400s oversized requests.
        """
        windows = [w for w in (candidate.context_length, self._learned_windows.get(candidate.name)) if w]
        return min(windows) if windows else 0

    def derived(self, name: str, now: float | None = None) -> DerivedStats:
        return self.group(name).derived(time.time() if now is None else now)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

TIER_DEFAULT = "default"
# Capability-first rubric; now used only by the ultra-think pool (the
# think pool uses TIER_DEFAULT).
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


def extract_context_limit(exc: BaseException | None) -> int | None:
    """Upstream context limit carried by a context_length failure, if any.

    NVIDIA's 400 for an over-window request reads just "Invalid request"
    to LiteLLM, so it maps to a generic BadRequestError — but the mapped
    error keeps the provider body's ``details`` (``{"type":
    "context_length", "limit": 262144, "actual": 265267}``). Walk the
    exception chain and any body/response payloads for that shape; fall
    back to a ``context_length ... limit N`` pattern in the message text.
    Returns None for unrelated errors and for context errors that carry
    no usable limit.
    """
    import re as _re

    seen: set[int] = set()
    queue: list[object] = [exc]
    while queue:
        current = queue.pop(0)
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        for attr in ("body", "response"):
            payload = getattr(current, attr, None)
            limit = _context_limit_from_payload(payload)
            if limit is not None:
                return limit
        text = str(current)
        match = _re.search(
            r"context_length[^0-9]{0,40}?limit['\"]?\s*[:=]\s*(\d+)", text, _re.IGNORECASE
        )
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                pass
        for attr in ("__cause__", "__context__"):
            nxt = getattr(current, attr, None)
            if nxt is not None:
                queue.append(nxt)
    return None


def _context_limit_from_payload(payload: object) -> int | None:
    import json as _json

    if isinstance(payload, str):
        try:
            payload = _json.loads(payload)
        except Exception:
            return None
    if not isinstance(payload, dict):
        return None
    details = payload.get("details")
    if isinstance(details, dict) and details.get("type") in (
        "context_length",
        "context_length_exceeded",
    ):
        limit = details.get("limit")
        if isinstance(limit, int) and not isinstance(limit, bool) and limit > 0:
            return limit
    return None


def _countable_chars(value: object) -> int:
    """Chars that count toward a prompt-size estimate, recursively.

    Anthropic-shaped messages nest the bulk of a coding session inside
    tool_result blocks (``{"type": "tool_result", "content": [{"type":
    "text", "text": ...}]}``) — a counter that only reads top-level
    ``text`` parts sees ~7k tokens of a 265k-token request and the fit
    filter passes a model whose real window the request already exceeds.
    Count every string under a message's content, recursing into nested
    content lists/dicts (tool results, tool inputs). Image blocks are
    skipped: their base64 ``source``/``data`` is not prompt text.
    """
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(_countable_chars(item) for item in value)
    if isinstance(value, dict):
        if value.get("type") in ("image", "image_url"):
            return 0
        return sum(
            _countable_chars(item)
            for key, item in value.items()
            if key not in ("source", "data", "type", "tool_use_id")
        )
    return 0


def estimate_tokens(messages: list[dict]) -> int:
    """Cheap chars/4 token estimate over OpenAI- or Anthropic-shaped messages."""
    total_chars = 0
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        total_chars += _countable_chars(msg.get("content"))
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
    tracks the previous class per group. The demotion proofs apply to ALL
    candidates — metric-backed ones rank on published health until our own
    tracked evidence proves them bad (workspace-ryi: pollinations returns
    hard failures as HTTP 200 content, so tracked soft failures are the only
    signal that a published-healthy model is actually gated).
    """
    failure_proof = (
        stats.n_obs >= cfg.min_obs
        and not stats.dead
        and stats.hard_rate < best_metric_score - cfg.demote_margin
    )
    latency_proof = stats.ttft_n >= cfg.min_obs and stats.ttft_mean > cfg.demote_ttft_seconds
    # A soft failure (provider error inside a 200 response) is deterministic
    # per model+account, not a transient blip: one observation is conclusive.
    soft_proof = stats.soft_failures > 0
    if stats.dead:
        return _CLASS_KNOWN, 0.0, "auth"
    if soft_proof:
        score = wilson_lower_bound(stats.success_rate, max(stats.n_obs, 1))
        return _CLASS_KNOWN, score, "soft"
    if failure_proof or latency_proof:
        score = wilson_lower_bound(stats.success_rate, max(stats.n_obs, 1))
        return _CLASS_KNOWN, score, "failures" if failure_proof else "latency"

    if not candidate.metricless:
        return _CLASS_METRIC, candidate.wilson_score, ""

    if stats.n_obs <= 0:
        # Never tried. Untested groups start at the neutral prior (0.5 by
        # default) — no benefit of the doubt — so known-healthier models
        # outrank them in the health sort; they still pass the default
        # floor and can win on capability once the cohort reaches them.
        # Deprioritized providers (llm7: no published metrics, groups that
        # trip daily token quotas) start at the same prior but as METRIC,
        # so they lose the favored block and health-tiebreaks to other
        # untried models, and compete on tracked evidence from the first
        # observation.
        if candidate.provider in cfg.deprioritized_providers:
            return _CLASS_METRIC, cfg.untried_prior_score, ""
        return _CLASS_FAVORED, cfg.untried_prior_score, ""

    # Tried: rank on OUR OWN tracked health (429-weighted, decayed) instead of
    # a static placeholder, so sustained rate-limiting demotes without
    # waiting for a hard-failure proof.
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

    # Context fit: only enforced where the context length is actually known;
    # metric-less groups with unknown context bypass fit. The window
    # used is the effective one — the smaller of the catalog claim and
    # any upstream-proven learned limit — because a catalog claim above
    # the real window is exactly what 400s an oversized request.
    # If fit empties the pool, keep all: an oversized request is still
    # better served by the best-ranked (largest-window, healthiest)
    # candidate than by passing the tier pool through to the router's
    # arbitrary selection. This mirrors the recency guard below.
    pool: list[tuple[ModelCandidate, DerivedStats]] = []
    fit_dropped: list[tuple[ModelCandidate, DerivedStats]] = []
    for c in candidates:
        if not c.available:
            continue
        # Free-only: the picker only selects free models. Parsers admit
        # only free candidates, and this rank-time filter is the backstop
        # for stale snapshots, the (paid) fallback snapshot, and future
        # providers — a non-free candidate can never be picked, even if
        # it somehow reaches the snapshot.
        if not c.free:
            continue
        entry = (c, stats_registry.derived(c.name, now))
        window = stats_registry.effective_window(c)
        if window and estimate > window:
            fit_dropped.append(entry)
            continue
        pool.append(entry)
    if not pool and fit_dropped:
        pool = fit_dropped

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
    # compete on evidence alongside metric-backed ones. In the ultra-think
    # rubric the sort is context-first and rank_class already resolves ties.
    latency_demoted_names: set[str] = set()
    for r in ranked:
        if r.rank_class == _CLASS_KNOWN:
            d = dstats_by_name[r.candidate.name]
            if d.ttft_n >= cfg.min_obs and d.ttft_mean > cfg.demote_ttft_seconds:
                latency_demoted_names.add(r.candidate.name)

    # Shared health blocks, used by both tiers: a model that has
    # *demonstrated* strong health beats an unmeasured one, and an
    # unmeasured one still beats a model known to be weak; demoted models
    # sort last. An untried model's nominal health is the neutral prior
    # (0.5), so health alone already puts known-strong models ahead of it;
    # the block still does real work below that — it keeps untried models
    # above known-weak ones, whose tracked or published health can sit
    # just above the prior.
    def block_for(r: RankedCandidate) -> int:
        if r.rank_class == _CLASS_KNOWN:
            return 3
        if r.rank_class == _CLASS_FAVORED:
            return 1
        if r.health_score >= cfg.strong_health_threshold:
            return 0
        return 2

    def effective_score(r: RankedCandidate) -> float:
        return r.health_score - (1.0 if r.candidate.name in latency_demoted_names else 0.0)

    def class_order(r: RankedCandidate) -> int:
        # Tiebreak only, used by the default tier: on equal health, an
        # untried (FAVORED) model outranks a neutral-prior (METRIC) one, so
        # deprioritized providers (llm7) still lose ties to other untried
        # models now that both start at the same 0.5 prior. KNOWN never
        # reaches the cohort.
        return {_CLASS_FAVORED: 0, _CLASS_METRIC: 1, _CLASS_KNOWN: 2}[r.rank_class]

    if tier == TIER_THINK:
        # Ultra-think only (the think pool now uses the default rubric):
        # Context first, then modelgrep benchmark (capability), then the
        # health blocks, then health, then name. So a higher-benchmark
        # untried model still beats a lower-benchmark known-strong one
        # (exploration by capability), but on equal context *and* equal
        # benchmark, demonstrated good health beats being unmeasured —
        # equally capable models are decided by evidence, not novelty.
        # Demoted models still sort last within their context/benchmark.
        ranked.sort(
            key=lambda r: (
                -r.candidate.context_length,
                -r.candidate.benchmark_score,
                block_for(r),
                -effective_score(r),
                r.candidate.name,
            )
        )
    else:  # TIER_DEFAULT: health-filtered capability pick. The default tier
        # no longer always picks the healthiest model. It filters first —
        # hard health floor, then the top N% healthiest — and picks the most
        # capable model (highest benchmark, then largest context) from the
        # survivors, with health breaking ties. The think pool uses this
        # rubric too (it maps to TIER_DEFAULT). Health here is the effective
        # score (the latency floor already applied), so slow models are
        # filtered on their penalized health. Benchmark outranks context
        # everywhere capability is compared in this tier — the capability
        # pick, the top-% cutoff's tiebreak, and the tail order — while
        # ultra-think keeps its own context-first order.
        #
        # Demoted (KNOWN-class) models never enter the cohort: demotion is a
        # proven-bad signal, stronger than the health number, and letting a
        # demoted-but-capable model jump the queue would regress the
        # demotion proofs. If every candidate is demoted, the old block order
        # below is kept as a last resort. If the floor empties the cohort,
        # the floor is ignored for this request (mirroring the fit-empty
        # fallback) and the top-% + capability steps still run on the full
        # cohort. The cohort leads the returned list in capability order
        # and the rest follow in the old block order, so anything iterating
        # past the pick still sees every eligible candidate.
        def default_sort_key(r: RankedCandidate):
            return (
                block_for(r),
                -effective_score(r),
                -r.candidate.benchmark_score,
                -r.candidate.context_length,
                r.candidate.name,
            )

        eligible = [r for r in ranked if r.rank_class != _CLASS_KNOWN]
        if eligible:
            floor = _clamp(cfg.min_health, 0.0, 1.0, DEFAULT_MIN_HEALTH)
            cohort = [r for r in eligible if effective_score(r) >= floor]
            if not cohort:
                logger.debug(
                    "model_picker: health floor %.3f emptied the default pool; ignoring floor for this request",
                    floor,
                )
                cohort = eligible
            pct = _clamp(cfg.health_top_percent, 1.0, 100.0, DEFAULT_HEALTH_TOP_PERCENT)
            cohort.sort(
                key=lambda r: (
                    -effective_score(r),
                    class_order(r),
                    -r.candidate.benchmark_score,
                    -r.candidate.context_length,
                    r.candidate.name,
                )
            )
            keep = max(1, math.ceil(len(cohort) * pct / 100.0))
            cohort = cohort[:keep]
            cohort.sort(
                key=lambda r: (
                    -r.candidate.benchmark_score,
                    -r.candidate.context_length,
                    -effective_score(r),
                    class_order(r),
                    r.candidate.name,
                )
            )
            cohort_names = {r.candidate.name for r in cohort}
            rest = sorted(
                (r for r in ranked if r.candidate.name not in cohort_names),
                key=default_sort_key,
            )
            ranked = cohort + rest
        else:
            ranked.sort(key=default_sort_key)
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


async def fetch_provider_models(url: str, api_key_env: str) -> dict | list:
    """Raw /v1/models payload from a provider (parsed by the caller)."""
    return await _fetch_json(url, os.environ.get(api_key_env))


# ---------------------------------------------------------------------------
# Snapshot manager (TTL cache, single-flight, stale-serve, fallback)
# ---------------------------------------------------------------------------


@dataclass
class CatalogSnapshot:
    candidates: list[ModelCandidate]
    created_at: float = field(default_factory=time.time)
    stale: bool = False  # served from cache after a refresh failure


class CatalogManager:
    """TTL-cached catalog with single-flight refresh and stale/fallback serve.

    Every provider is catalog-driven: pollinations, NIM and LLM7
    models are discovered from their /v1/models listings at refresh time and
    served through the per-provider wildcard model_list entries. A provider
    whose listing fails mid-refresh keeps its previously-known candidates
    (stale-serve); a fully cold failure serves the fallback snapshot.
    """

    def __init__(self, cfg: PickerConfig | None = None) -> None:
        self.cfg = cfg or PickerConfig()
        self._snapshot: CatalogSnapshot | None = None
        self._lock = asyncio.Lock()
        self._last_good: dict[str, list[ModelCandidate]] = {}
        self._modelgrep_entries: list[dict] | None = None
        self._modelgrep_fetched_at: float = 0.0

    async def _refresh_modelgrep(self) -> None:
        """Refresh the modelgrep benchmark catalog (own, slower TTL; fail-soft).

        Sets _modelgrep_entries only on a successful fetch — a failure keeps
        the last-known data (gating continues on it), and a cold failure
        leaves None so enrichment/gating is skipped entirely.
        """
        if not self.cfg.benchmarks_enabled:
            return
        if self._modelgrep_entries is not None and (time.time() - self._modelgrep_fetched_at) < self.cfg.benchmark_ttl_seconds:
            return
        try:
            entries = await fetch_modelgrep_catalog(self.cfg.modelgrep_url)
            if entries:
                self._modelgrep_entries = entries
                self._modelgrep_fetched_at = time.time()
            else:
                logger.warning("model_picker: modelgrep returned no entries; keeping last known")
        except Exception as e:  # noqa: BLE001 — benchmark data must never break routing
            logger.warning("model_picker: modelgrep refresh failed (%s); using last known", e)

    def _enrich_and_gate(self, candidates: list[ModelCandidate]) -> list[ModelCandidate]:
        """Join benchmarks from modelgrep and drop unmatched candidates.

        The gate applies only when modelgrep data exists (fresh or last
        known); a cold, never-fetched state keeps the pool ungated so a
        modelgrep outage cannot empty the pool outright.
        """
        if self._modelgrep_entries is None:
            logger.warning("model_picker: no modelgrep data; benchmark gating skipped")
            return candidates
        index = ModelGrepIndex(self._modelgrep_entries)
        kept: list[ModelCandidate] = []
        dropped: list[str] = []
        stage_counts: dict[str, int] = {}
        for c in candidates:
            upstream_id = c.name.split("/", 1)[1] if "/" in c.name else c.name
            entry, stage, confidence = index.match(upstream_id)
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
            if entry is None:
                dropped.append(c.name)
                continue
            c.modelgrep_id = str(entry.get("id") or "")
            c.benchmark_score, c.benchmarked = modelgrep_benchmark_score(entry)
            # fill unknown context windows from modelgrep: the router's
            # context compaction needs a real window, and the fit filter can
            # only protect requests when the window is known
            if not c.context_length:
                mg_ctx = entry.get("context_length")
                if isinstance(mg_ctx, int) and not isinstance(mg_ctx, bool) and mg_ctx > 0:
                    c.context_length = mg_ctx
            kept.append(c)
        summary = " ".join(f"{stage}={n}" for stage, n in sorted(stage_counts.items()))
        logger.info(
            "model_picker: modelgrep gate kept %d/%d candidates (%s); dropped: %s",
            len(kept),
            len(candidates),
            summary,
            dropped[:12],
        )
        return kept

    def _fallback_snapshot(self) -> CatalogSnapshot:
        candidates = [
            ModelCandidate(
                name=f"pollinations/{self.cfg.fallback_model}",
                provider="pollinations",
                context_length=0,
                metricless=False,
                success_rate=1.0,
                requests=0,
                source="prior",
            )
        ]
        return CatalogSnapshot(candidates=candidates, stale=True)

    async def _fetch_provider(
        self,
        provider_key: str,
        fetch,
        parse,
    ) -> list[ModelCandidate]:
        """Fetch+parse one provider's catalog, tolerating its failure.

        A failed or empty refresh keeps the provider's last-known candidates
        (stale-serve per provider) instead of taking down the whole snapshot.
        """
        try:
            candidates = parse(await fetch())
            if candidates:
                self._last_good[provider_key] = candidates
            return candidates or self._last_good.get(provider_key, [])
        except Exception as e:  # noqa: BLE001 — one provider must not sink the snapshot
            logger.warning("model_picker: %s catalog refresh failed (%s); using last known", provider_key, e)
            return self._last_good.get(provider_key, [])

    async def get_snapshot(self) -> CatalogSnapshot:
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
                pollinations = await self._fetch_provider(
                    "pollinations",
                    lambda: _fetch_json(self.cfg.pollinations_url, os.environ.get("POLLINATION_API_KEY")),
                    parse_pollinations_models,
                )
                nim = await self._fetch_provider(
                    "nvidia_nim",
                    lambda: fetch_provider_models(NIM_MODELS_URL, "NIM_API_KEY"),
                    parse_nim_models,
                )
                llm7 = await self._fetch_provider(
                    "llm7",
                    lambda: fetch_provider_models(LLM7_MODELS_URL, "LLM7_API_KEY"),
                    parse_llm7_models,
                )
                await self._refresh_modelgrep()
                candidates = pollinations + nim + llm7
                candidates = self._enrich_and_gate(candidates)
                if not candidates:
                    raise RuntimeError("provider catalogs returned no eligible models")
                self._snapshot = CatalogSnapshot(candidates=candidates)
                return self._snapshot
            except Exception as e:  # noqa: BLE001 — never fail routing on catalog trouble
                logger.warning("model_picker: catalog refresh failed (%s); serving stale/fallback", e)
                if snap is not None:
                    snap.stale = True
                    return snap
                self._snapshot = self._fallback_snapshot()
                return self._snapshot

    def peek_candidate_names(self) -> set[str] | None:
        """Candidate names from the cached snapshot, without refreshing.

        None when the manager is cold (no snapshot yet). Used by the stats
        logger to reconcile group names against the picker's candidates.
        """
        snap = self._snapshot
        if snap is None:
            return None
        return {c.name for c in snap.candidates}

    def peek_candidate(self, name: str) -> "ModelCandidate | None":
        """One candidate from the cached snapshot by name (None if cold/absent)."""
        snap = self._snapshot
        if snap is None:
            return None
        for c in snap.candidates:
            if c.name == name:
                return c
        return None


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
        _shared_stats = StatsRegistry(path=default_stats_path())
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
