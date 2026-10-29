"""Tests for the model picker (beads workspace-c8o).

Loads the plugin modules the same way litellm's get_instance_fn does
(spec_from_file_location next to the config), so the sys.modules-guarded
sibling loader is exercised too.
"""

import asyncio
import importlib.util
import json
import os
import sys
import time
import types
from datetime import datetime
from pathlib import Path

import litellm
import pytest
import yaml

import litellm
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
LITE_LLM_DIR = REPO_ROOT / "lite-llm"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mp():
    """The model_picker library + plugin module pair, loaded production-style."""
    plugin = _load_module("model_picker_plugin_test", LITE_LLM_DIR / "model_picker_plugin.py")
    lib = sys.modules["model_picker"]
    return lib, plugin


@pytest.fixture()
def env_enabled(monkeypatch):
    monkeypatch.setenv("MODEL_PICKER_ENABLED", "true")


@pytest.fixture()
def fresh(mp):
    """Fresh config/stats/manager + a plugin wired to them (test isolation)."""
    lib, plugin = mp
    cfg = lib.PickerConfig()
    cfg.ttl_seconds = 300.0
    stats = lib.StatsRegistry()
    manager = lib.CatalogManager(cfg)
    test_plugin = plugin.ModelPickerPlugin(manager=manager, stats=stats, config=cfg)
    return lib, test_plugin, cfg, stats, manager


def pollinations_fixture() -> dict:
    return json.loads((FIXTURES / "pollinations_models.json").read_text())


def make_context(lib, candidate_models, metadata=None, messages=None):
    from litellm.types.router import RoutingContext

    msgs = messages if messages is not None else [{"role": "user", "content": "hello"}]
    return RoutingContext(
        raw_messages=msgs,
        structured_messages=msgs,
        candidate_models=list(candidate_models),
        metadata=metadata if metadata is not None else {},
    )


def snapshot_with(lib, candidates, stale=False):
    return lib.CatalogSnapshot(candidates=list(candidates), stale=stale)


def candidates_from_fixture(lib):
    return lib.parse_pollinations_models(pollinations_fixture())


def free_plugin_pool(lib):
    """Small free-only pool for plugin/manager tests (the real fixture's
    models are all paid, so it now parses to nothing)."""
    return [
        metric_candidate(lib, "pollinations/openai/gpt-6-luna", 0.9997, 87885, ctx=1048576),
        metric_candidate(lib, "pollinations/z-ai/glm-5.3", 0.99, 100, ctx=1048576),
        metric_candidate(lib, "pollinations/deepseek/deepseek-v4-flash", 0.99, 100, ctx=1048576),
        metric_candidate(lib, "pollinations/community/vendouple/deepseek-v4-pro", 0.99, 100, ctx=1048576),
        metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885, ctx=400000),
    ]


def metric_candidate(lib, name, success, requests, ctx=100000):
    return lib.ModelCandidate(
        name=name,
        provider="pollinations",
        context_length=ctx,
        metricless=False,
        success_rate=success,
        requests=requests,
        source="pollinations_api",
        free=True,
    )


def favored_candidate(lib, name, provider="nvidia_nim", ctx=0):
    return lib.ModelCandidate(name=name, provider=provider, context_length=ctx, metricless=True, free=True)


# ---------------------------------------------------------------------------
# Catalog parsing / filtering
# ---------------------------------------------------------------------------


class TestCatalogParsing:
    def test_fixture_paid_models_excluded(self, mp):
        lib, _ = mp
        names = {c.name for c in candidates_from_fixture(lib)}
        # Every non-down model in the fixture carries a nonzero pollen rate,
        # so the free-only parser admits none of them; the one rate-less
        # model (ling-3.1-flash) is down and excluded on health instead.
        assert "pollinations/openai/gpt-5.4-nano" not in names
        assert "pollinations/openai/gpt-oss-20b" not in names
        assert "pollinations/z-ai/glm-5.3" not in names
        assert "pollinations/community/vendouple/deepseek-v4-pro" not in names
        assert "pollinations/community/vendouple/glm-5.3-flash" not in names
        assert "pollinations/community/sharktide/inferenceport-ai-lightning-text-v2" not in names

    def test_zero_pollen_rate_marked_free(self, mp):
        lib, _ = mp
        by_name = {c.name: c for c in candidates_from_fixture(lib)}
        # models with nonzero pollen rates are charged, and now dropped
        assert "pollinations/openai/gpt-5.4-nano" not in by_name
        assert "pollinations/community/vendouple/deepseek-v4-pro" not in by_name
        payload = {
            "data": [
                {
                    "id": "openai/free-model",
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                    "supported_endpoints": ["/v1/chat/completions"],
                    "health": {"status": "healthy", "success_rate": 100, "requests": 10},
                    "pricing": {"currency": "pollen"},
                },
                {
                    "id": "openai/zero-model",
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                    "supported_endpoints": ["/v1/chat/completions"],
                    "health": {"status": "healthy", "success_rate": 100, "requests": 10},
                    "pricing": {"currency": "pollen", "promptTextTokens": "0", "completionTextTokens": "0.0"},
                },
                {
                    "id": "openai/no-pricing-model",
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                    "supported_endpoints": ["/v1/chat/completions"],
                    "health": {"status": "healthy", "success_rate": 100, "requests": 10},
                },
            ]
        }
        parsed = {c.name: c for c in lib.parse_pollinations_models(payload)}
        assert parsed["pollinations/openai/free-model"].free is True
        assert parsed["pollinations/openai/zero-model"].free is True
        assert parsed["pollinations/openai/no-pricing-model"].free is True
        # a nonzero pollen rate drops the model entirely, not just flags it
        paid_payload = {
            "data": [
                {
                    "id": "openai/paid-model",
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                    "supported_endpoints": ["/v1/chat/completions"],
                    "health": {"status": "healthy", "success_rate": 100, "requests": 10},
                    "pricing": {"currency": "pollen", "promptTextTokens": "0.00000015"},
                }
            ]
        }
        assert lib.parse_pollinations_models(paid_payload) == []

    def test_paid_only_excluded(self, mp):
        lib, _ = mp
        names = {c.name for c in candidates_from_fixture(lib)}
        assert "pollinations/poolside/laguna-s-2.1" not in names
        assert "pollinations/stepfun/step-5-preview" not in names
        # even a community model flagged paid_only is excluded
        payload = {
            "data": [
                {
                    "id": "community/someone/paid",
                    "community": True,
                    "paid_only": True,
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                    "supported_endpoints": ["/v1/chat/completions"],
                    "health": {"status": "healthy", "success_rate": 100, "requests": 10},
                }
            ]
        }
        assert lib.parse_pollinations_models(payload) == []

    def test_audio_only_models_excluded(self, mp):
        lib, _ = mp
        names = {c.name for c in candidates_from_fixture(lib)}
        # whisper is audio->text (no text input): not a chat model
        assert "pollinations/openai/whisper-large-v3" not in names
        # the modality filter admits text-capable models that also serve audio,
        # and excludes audio-only ones
        payload = {
            "data": [
                {
                    "id": "community/someone/audio-chat",
                    "community": True,
                    "input_modalities": ["text", "audio"],
                    "output_modalities": ["text", "audio"],
                    "supported_endpoints": ["/v1/chat/completions"],
                    "health": {"status": "healthy", "success_rate": 100, "requests": 10},
                },
                {
                    "id": "community/someone/whisper",
                    "community": True,
                    "input_modalities": ["audio"],
                    "output_modalities": ["text"],
                    "supported_endpoints": ["/v1/chat/completions"],
                    "health": {"status": "healthy", "success_rate": 100, "requests": 10},
                },
            ]
        }
        parsed = {c.name for c in lib.parse_pollinations_models(payload)}
        assert "pollinations/community/someone/audio-chat" in parsed
        assert "pollinations/community/someone/whisper" not in parsed

    def test_down_models_excluded(self, mp):
        lib, _ = mp
        names = {c.name for c in candidates_from_fixture(lib)}
        assert "pollinations/community/samueltargino0567-ux/Gt3" not in names
        assert "pollinations/inclusionai/ling-3.1-flash" not in names

    def test_degraded_and_unknown_kept(self, mp):
        lib, _ = mp
        # degraded health is still a candidate when the model is free; the
        # fixture's degraded model is paid, so it no longer parses at all
        payload = {
            "data": [
                {
                    "id": "community/someone/degraded-free",
                    "community": True,
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                    "supported_endpoints": ["/v1/chat/completions"],
                    "health": {"status": "degraded", "success_rate": 90, "requests": 10},
                    "pricing": {"currency": "pollen"},
                }
            ]
        }
        parsed = {c.name: c for c in lib.parse_pollinations_models(payload)}
        assert parsed["pollinations/community/someone/degraded-free"].success_rate == pytest.approx(0.9)
        # unknown health / zero requests -> zero published score, still a candidate
        payload = {
            "data": [
                {
                    "id": "community/someone/unproven",
                    "community": True,
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                    "supported_endpoints": ["/v1/chat/completions"],
                    "health": {"status": "unknown", "requests": 0},
                }
            ]
        }
        parsed = lib.parse_pollinations_models(payload)
        assert parsed[0].success_rate == 0.0
        assert parsed[0].requests == 0

    def test_wilson_bounds(self, mp):
        lib, _ = mp
        # huge volume at 99.97% stays ~published; tiny perfect sample bounds low
        assert lib.wilson_lower_bound(0.9997, 87885) > 0.999
        assert lib.wilson_lower_bound(1.0, 3) < 0.8
        assert lib.wilson_lower_bound(1.0, 0) == 0.0


# ---------------------------------------------------------------------------
# Soft-failure detection (errors smuggled through HTTP 200 content)
# ---------------------------------------------------------------------------


def _response_with_content(content):
    """Minimal stand-in for a litellm ModelResponse."""

    class _Msg:
        def __init__(self, content):
            self.content = content

    class _Choice:
        def __init__(self, content):
            self.message = _Msg(content)

    class _Resp:
        def __init__(self, content):
            self.choices = [_Choice(content)]

    return _Resp(content)


class TestSoftFailureDetection:
    def test_credits_marker_detected(self, mp):
        lib, _ = mp
        credits = (
            "The account behind this API key doesn't have enough credits. "
            "Please top up or complete a quest, then try again."
        )
        assert lib.is_soft_failure_content(credits)
        # curly-apostrophe variant from JSON transport
        assert lib.is_soft_failure_content(credits.replace("'", "’"))
        assert lib.is_soft_failure_content("  The account behind this API key does not have enough credits. ")

    def test_relayed_error_prefix_detected(self, mp):
        lib, _ = mp
        assert lib.is_soft_failure_content("\n\n[Error: Z.ai returned 403: {\"code\":\"USER_KEY_UNAUTHORIZED\"}]")
        assert lib.is_soft_failure_content("[error: something broke]")

    def test_normal_content_not_flagged(self, mp):
        lib, _ = mp
        assert not lib.is_soft_failure_content("")
        assert not lib.is_soft_failure_content(None)
        assert not lib.is_soft_failure_content("Hello! How can I assist you today?")
        # a model merely discussing credits mid-response is not an error
        assert not lib.is_soft_failure_content("I don't have enough context to answer that, sorry!")
        assert not lib.is_soft_failure_content("To top up your credits, visit the billing page.")

    def test_extract_response_text_shapes(self, mp):
        lib, _ = mp
        assert lib.extract_response_text(_response_with_content("hello")) == "hello"
        assert lib.extract_response_text(_response_with_content(["a", {"text": "b"}])) == "a\nb"
        assert lib.extract_response_text(None) == ""
        assert lib.extract_response_text(object()) == ""

    def test_extended_single_factor_markers(self, mp):
        lib, _ = mp
        for phrase in ("Insufficient credits for this request.", "Daily quota exceeded", "Please top up your balance"):
            assert lib.is_soft_failure_content(phrase), phrase
        assert lib.is_soft_failure_content("[Exception: upstream 500]")
        assert lib.is_soft_failure_content("[Error: Z.ai returned 403]")

    def test_two_factor_zero_usage_plus_lexicon(self, mp):
        lib, _ = mp
        gated = {"usage": {"input_tokens": 0, "output_tokens": 0}, "content": [{"type": "text", "text": "Your request was rate limited by upstream"}]}
        assert lib.is_soft_failure_response(lib.extract_response_text(gated), gated)
        # zero usage but clean text -> legitimate short answer, NOT a failure
        clean = {"usage": {"input_tokens": 0, "output_tokens": 0}, "content": [{"type": "text", "text": "Hello!"}]}
        assert not lib.is_soft_failure_response(lib.extract_response_text(clean), clean)
        # error text but real (nonzero) usage -> the model genuinely ran
        real = {"usage": {"input_tokens": 40, "output_tokens": 8}, "content": [{"type": "text", "text": "The request hit an error and here is why..."}]}
        assert not lib.is_soft_failure_response(lib.extract_response_text(real), real)
        # absent usage -> not structural (some providers omit it legitimately)
        absent = {"content": [{"type": "text", "text": "an error occurred upstream"}]}
        assert not lib.is_soft_failure_response(lib.extract_response_text(absent), absent)

    def test_two_factor_model_response_object(self, mp):
        lib, _ = mp
        gated = litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": "upstream returned 429, try again"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 0, "completion_tokens": 0},
        )
        assert lib.is_soft_failure_response(lib.extract_response_text(gated), gated)
        real = litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": "you asked about api key errors"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 31, "completion_tokens": 9},
        )
        assert not lib.is_soft_failure_response(lib.extract_response_text(real), real)

    def test_stats_logger_demotes_on_two_factor_rule(self, mp):
        """A novel error phrasing with the zero-usage signature still demotes."""
        lib, plugin = mp
        stats = lib.StatsRegistry()
        logger = plugin.ModelPickerStatsLogger(stats=stats)
        gated = {
            "id": "resp_x",
            "type": "message",
            "content": [{"type": "text", "text": "Upstream capacity limit reached, billing required"}],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        asyncio.run(logger.async_log_success_event(
            {"litellm_metadata": {"model_group": "pollinations/community/x"}}, gated, None, None
        ))
        d = stats.derived("pollinations/community/x")
        assert d.n_obs == 1 and d.soft_failures == 1

    def test_stats_logger_records_soft_failure(self, mp):
        lib, plugin = mp
        stats = lib.StatsRegistry()
        cfg = lib.PickerConfig()
        logger = plugin.ModelPickerStatsLogger(stats=stats)
        group = "pollinations/openai/gpt-5.4-nano"
        group_kwargs = {"litellm_metadata": {"model_group": group}}
        credits = "The account behind this API key doesn't have enough credits. Please top up."
        asyncio.run(logger.async_log_success_event(group_kwargs, _response_with_content(credits), None, None))
        derived = stats.derived(group)
        assert derived.n_obs == 1
        assert derived.success_rate == 0.0  # recorded as a failure, not a success
        # repeated soft failures feed the demotion proof like any hard failure
        for _ in range(cfg.min_obs - 1):
            asyncio.run(logger.async_log_success_event(group_kwargs, _response_with_content(credits), None, None))
        # the now-broken group ranks below a healthy metric-backed candidate
        gated = lib.ModelCandidate(name=group, provider="pollinations", metricless=True, free=True)
        healthy = lib.ModelCandidate(
            name="pollinations/openai/healthy", provider="pollinations", metricless=False, success_rate=0.9997, requests=87885, free=True
        )
        now = time.time() + cfg.recency_window_seconds + 1
        ranked = lib.rank_candidates([gated, healthy], lib.TIER_DEFAULT, stats, cfg, now=now)
        assert [r.candidate.name for r in ranked] == ["pollinations/openai/healthy", group]
        # normal content still records a success (and TTFT)
        stats2 = lib.StatsRegistry()
        logger2 = plugin.ModelPickerStatsLogger(stats=stats2)
        start = datetime.now()
        asyncio.run(logger2.async_log_success_event(group_kwargs, _response_with_content("Hi!"), start, start))
        assert stats2.derived(group).n_obs == 1
        assert stats2.derived(group).success_rate == 1.0

    def test_published_healthy_model_demoted_by_tracked_soft_failures(self, fresh):
        lib, _, cfg, stats, _ = fresh
        # a published-perfect catalog model whose picks all soft-fail for us
        gated = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 1.0, 87885)
        healthy = metric_candidate(lib, "pollinations/openai/other", 0.99, 5000)
        now = time.time()
        for _ in range(cfg.min_obs):
            stats.record_failure("pollinations/openai/gpt-5.4-nano", lib.FAILURE_CLASS_ERROR, now=now)
        after_guard = now + cfg.recency_window_seconds + 1
        ranked = lib.rank_candidates([gated, healthy], lib.TIER_DEFAULT, stats, cfg, now=after_guard)
        # published wilson 1.0 no longer shields it: our tracked evidence demotes
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/other",
            "pollinations/openai/gpt-5.4-nano",
        ]


# ---------------------------------------------------------------------------
# Modelgrep enrichment: matching, benchmark composite, gating, ranking
# ---------------------------------------------------------------------------


def _mg_entry(mg_id, maker=None, context_length=None, **aa_scores):
    """One modelgrep entry with an artificial_analysis block."""
    return {
        "id": mg_id,
        "maker": maker or mg_id.split("/")[0],
        "context_length": context_length,
        "benchmarks": {"artificial_analysis": aa_scores or {}},
    }


class TestModelgrepEnrichment:
    @staticmethod
    def _index(entries):
        return lib_modelgrep_index(entries)

    def test_exact_and_normalization_match(self, mp):
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("openai/gpt-5.4-nano", coding_pct=60)])
        entry, stage, conf = idx.match("openai/gpt_5.4.nano")  # separators normalize
        assert entry["id"] == "openai/gpt-5.4-nano"
        assert stage == "exact" and conf == 1.0

    def test_community_prefix_and_decoration_stripping(self, mp):
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("z-ai/glm-5.3-flash")])
        entry, stage, _ = idx.match("community/morriszdweck/glm-5.3-flash-free")
        assert entry["id"] == "z-ai/glm-5.3-flash"

    def test_maker_aliasing(self, mp):
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("deepseek/deepseek-v4.1-flash")])
        entry, _, _ = idx.match("deepseek-ai/deepseek-v4.1-flash")
        assert entry["id"] == "deepseek/deepseek-v4.1-flash"

    def test_version_guard_rejects_close_versions(self, mp):
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("z-ai/glm-5.2")])
        entry, stage, _ = idx.match("z-ai/glm-5.3")
        assert entry is None  # glm-5.3 must never match glm-5.2

    def test_variant_guard_relaxed_by_substring_fallback(self, mp):
        # Deliberate consequence of bidirectional substring matching: a
        # -flash relay now matches a -flash-lite entry when that is the
        # unique substring hit (candidate segment contained in the entry
        # segment). The version guard still holds: glm-5.3 never matches
        # glm-5.2, because neither contains the other.
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("z-ai/glm-5.3-flash-lite")])
        entry, stage, _ = idx.match("z-ai/glm-5.3-flash")
        assert entry["id"] == "z-ai/glm-5.3-flash-lite"
        assert stage == "substring"

    def test_substring_matches_vendor_prefixed_relay(self, mp):
        # The reported case: the vercel- prefix broke every strict stage
        # even though the base model entry exists.
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("nvidia/nemotron-3.5-lightning", coding_pct=34)])
        entry, stage, _ = idx.match("YoannDev90/vercel-nemotron-3.5-lightning:free")
        assert entry["id"] == "nvidia/nemotron-3.5-lightning"
        assert stage == "substring"

    def test_substring_matches_entry_containing_candidate(self, mp):
        # Vice versa: the candidate's segment contained in the entry's.
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("z-ai/glm-5.3-flash")])
        entry, stage, _ = idx.match("community/user/glm-5.3")
        assert entry["id"] == "z-ai/glm-5.3-flash"
        assert stage == "substring"

    def test_substring_ambiguous_rejected(self, mp):
        # A fragment matching several entries still gates out.
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("meta/muse-spark-1.3"), _mg_entry("meta/muse-glimmer-30b")])
        entry, _, _ = idx.match("community/user/muse")
        assert entry is None

    def test_substring_requires_boundary_and_min_length(self, mp):
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("acme/sunbeam-x"), _mg_entry("acme/x-d3-pro")])
        assert idx.match("community/user/beam")[0] is None  # mid-token, not a boundary
        assert idx.match("community/user/d3")[0] is None  # under the 4-char minimum

    def test_substring_invents_no_entry(self, mp):
        # The CloudCompile ultra relay still gates out: no ultra entry
        # exists for any stage, strict or substring, to match.
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("nvidia/nemotron-3.5-lightning")])
        entry, _, _ = idx.match("CloudCompile/nvidia-nemotron-3-ultra-550b-a55b:free")
        assert entry is None

    def test_dashless_matches_camelcase_concatenation(self, mp):
        # Word boundaries differ only in separators/casing: the dashed
        # forms never align, but the dashless forms are identical.
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("nvidia/nemotron-3.5-lightning", coding_pct=34)])
        entry, stage, conf = idx.match("Nemotron3.5Lightning")
        assert entry["id"] == "nvidia/nemotron-3.5-lightning"
        assert stage == "dashless" and conf == 0.9

    def test_dashless_matches_concatenated_decorated_relay(self, mp):
        # Fully concatenated, plus a colon-suffixed :free relay suffix:
        # the stripped normalized bare segment is what dashless-matches.
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("nvidia/nemotron-3.5-lightning", coding_pct=34)])
        entry, stage, _ = idx.match("Nemotron3.5Lightning:free")
        assert entry["id"] == "nvidia/nemotron-3.5-lightning"
        assert stage == "dashless"
        entry, stage, _ = idx.match("nemotron35lightning")
        assert entry["id"] == "nvidia/nemotron-3.5-lightning"
        assert stage == "dashless"

    def test_dashless_ambiguous_collision_gates_out(self, mp):
        # The version-boundary collapse dashless introduces (3-1 vs 31)
        # must gate out when two entries collide, never pick one.
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("acme/llama-3-1-8b"), _mg_entry("other/llama-31-8b")])
        entry, stage, _ = idx.match("llama318b")
        assert entry is None
        assert stage == "ambiguous"

    def test_dashless_never_overrides_strict_stages(self, mp):
        # The alias loop runs first: an exact hit wins even when the
        # dashless segment index is ambiguous for the same candidate.
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("acme/foo-bar"), _mg_entry("other/foobar")])
        entry, stage, _ = idx.match("foo-bar")
        assert entry["id"] == "acme/foo-bar"
        assert stage == "exact"

    def test_gate_keeps_dashless_matched_candidate(self, fresh):
        lib, _, cfg, stats, manager = fresh
        manager._modelgrep_entries = [
            _mg_entry("nvidia/nemotron-3.5-lightning", coding_pct=34, agentic_pct=51, context_length=1000000),
        ]
        candidates = [
            lib.ModelCandidate(name="pollinations/Nemotron3.5Lightning",
                               provider="pollinations", metricless=False, success_rate=1.0, requests=50,
                               context_length=1000000, free=True),
        ]
        kept = manager._enrich_and_gate(candidates)
        assert [c.name for c in kept] == ["pollinations/Nemotron3.5Lightning"]
        assert kept[0].modelgrep_id == "nvidia/nemotron-3.5-lightning"
        assert kept[0].benchmarked is True

    def test_gate_keeps_substring_matched_relay(self, fresh):
        lib, _, cfg, stats, manager = fresh
        manager._modelgrep_entries = [
            _mg_entry("nvidia/nemotron-3.5-lightning", coding_pct=34, agentic_pct=51, context_length=1000000),
        ]
        candidates = [
            lib.ModelCandidate(name="pollinations/community/YoannDev90/vercel-nemotron-3.5-lightning:free",
                               provider="pollinations", metricless=False, success_rate=1.0, requests=50,
                               context_length=1000000, free=True),
        ]
        kept = manager._enrich_and_gate(candidates)
        assert [c.name for c in kept] == ["pollinations/community/YoannDev90/vercel-nemotron-3.5-lightning:free"]
        assert kept[0].modelgrep_id == "nvidia/nemotron-3.5-lightning"
        assert kept[0].benchmarked is True

    def test_size_sibling_resolution(self, mp):
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("nvidia/nemotron-3-ultra-550b-a55b")])
        entry, stage, conf = idx.match("nvidia/nemotron-3-ultra")
        assert entry["id"] == "nvidia/nemotron-3-ultra-550b-a55b"
        assert stage == "family-size-sibling" and conf <= 0.5

    def test_ambiguous_bare_segment_rejected(self, mp):
        lib, _ = mp
        idx = lib.ModelGrepIndex([_mg_entry("z-ai/glm-5.3-flash"), _mg_entry("acme/glm-5.3-flash")])
        entry, _, _ = idx.match("community/user/glm-5.3-flash")
        assert entry is None  # two makers own this segment -> gate out

    def test_benchmark_composite_pct_preferred_and_scales(self, mp):
        lib, _ = mp
        score, ok = lib.modelgrep_benchmark_score(
            {"benchmarks": {"artificial_analysis": {"coding_pct": 60, "agentic": 38.4, "terminalbench_pct": 95}}}
        )
        assert ok
        assert score == pytest.approx((0.60 + 0.384 + 0.95) / 3, abs=1e-3)

    def test_benchmark_composite_raw_fallbacks_and_partial(self, mp):
        lib, _ = mp
        score, ok = lib.modelgrep_benchmark_score(
            {"benchmarks": {"artificial_analysis": {"coding": 68.8, "tau2": 0.99, "terminalbench": 0.51}}}
        )
        assert ok
        assert score == pytest.approx((0.688 + 0.99 + 0.51) / 3, abs=1e-3)
        partial, ok2 = lib.modelgrep_benchmark_score(
            {"benchmarks": {"artificial_analysis": {"terminalbench": 0.4}}}
        )
        assert ok2 and partial == pytest.approx(0.4)
        none_score, none_ok = lib.modelgrep_benchmark_score({"benchmarks": {"artificial_analysis": {}}})
        assert none_ok is False and none_score == 0.0

    def test_gate_drops_unmatched_and_enriches_matched(self, fresh):
        lib, _, cfg, stats, manager = fresh
        manager._modelgrep_entries = [
            _mg_entry("openai/gpt-5.4-nano", coding_pct=80, agentic_pct=70, terminalbench_pct=60),
            _mg_entry("z-ai/glm-5.3-flash"),
        ]
        candidates = [
            lib.ModelCandidate(name="pollinations/openai/gpt-5.4-nano", provider="pollinations", metricless=False, success_rate=0.9997, requests=87885),
            lib.ModelCandidate(name="pollinations/community/user/mystery-model", provider="pollinations", metricless=False, success_rate=0.99, requests=50),
        ]
        kept = manager._enrich_and_gate(candidates)
        assert [c.name for c in kept] == ["pollinations/openai/gpt-5.4-nano"]
        assert kept[0].benchmarked is True
        assert kept[0].benchmark_score == pytest.approx((0.80 + 0.70 + 0.60) / 3)
        assert kept[0].modelgrep_id == "openai/gpt-5.4-nano"

    def test_modelgrep_fills_unknown_context_windows(self, fresh):
        """NIM publishes no context windows; modelgrep does. Unknown (0)
        windows are filled from the matched entry so the fit filter and the
        router's compaction budget have real data. Known windows win."""
        lib, _, cfg, stats, manager = fresh
        manager._modelgrep_entries = [
            _mg_entry("z-ai/glm-5.3", context_length=1048576),
            _mg_entry("openai/gpt-5.4-nano", context_length=400000),
        ]
        candidates = [
            lib.ModelCandidate(name="nvidia_nim/z-ai/glm-5.3", provider="nvidia_nim", metricless=True, context_length=0),
            lib.ModelCandidate(name="pollinations/openai/gpt-5.4-nano", provider="pollinations", metricless=False,
                               success_rate=0.9997, requests=87885, context_length=128000),
        ]
        kept = manager._enrich_and_gate(candidates)
        by_name = {c.name: c for c in kept}
        assert by_name["nvidia_nim/z-ai/glm-5.3"].context_length == 1048576  # filled
        assert by_name["pollinations/openai/gpt-5.4-nano"].context_length == 128000  # provider truth kept

    def test_unknown_context_models_fit_filter_with_enriched_windows(self, fresh):
        """With real windows, the fit filter protects requests: a 400k-token
        estimate fits the 1M window and is kept; a 16k window is filtered out."""
        lib, _, cfg, stats, _ = fresh
        big_ctx = lib.ModelCandidate(name="nvidia_nim/z-ai/glm-5.3", provider="nvidia_nim", metricless=True, free=True,
                                      context_length=1048576)
        small_ctx = lib.ModelCandidate(name="nvidia_nim/small/model", provider="nvidia_nim", metricless=True,
                                        context_length=16384)
        ranked = lib.rank_candidates([big_ctx, small_ctx], lib.TIER_DEFAULT, stats, cfg, estimate=400000)
        names = [r.candidate.name for r in ranked]
        assert "nvidia_nim/small/model" not in names
        assert "nvidia_nim/z-ai/glm-5.3" in names

    def test_gate_fail_open_without_modelgrep_data(self, fresh):
        lib, _, cfg, stats, manager = fresh
        assert manager._modelgrep_entries is None
        candidates = [lib.ModelCandidate(name="pollinations/anything", provider="pollinations", metricless=True)]
        kept = manager._enrich_and_gate(candidates)
        assert kept == candidates  # cold modelgrep never gates

    def test_benchmarks_break_availability_context_ties(self, fresh):
        lib, _, cfg, stats, _ = fresh
        weak_bench = lib.ModelCandidate(
            name="pollinations/weak-bench", provider="pollinations", metricless=False, free=True,
            success_rate=0.9997, requests=87885, context_length=1048576, benchmark_score=0.2, benchmarked=True,
        )
        strong_bench = lib.ModelCandidate(
            name="pollinations/strong-bench", provider="pollinations", metricless=False, free=True,
            success_rate=0.9997, requests=87885, context_length=1048576, benchmark_score=0.8, benchmarked=True,
        )
        ranked = lib.rank_candidates([weak_bench, strong_bench], lib.TIER_DEFAULT, stats, cfg)
        assert ranked[0].candidate.name == "pollinations/strong-bench"
        # think tier too (same health/class/context -> benchmark decides)
        ranked = lib.rank_candidates([weak_bench, strong_bench], lib.TIER_THINK, stats, cfg)
        assert ranked[0].candidate.name == "pollinations/strong-bench"


def lib_modelgrep_index(entries):
    lib = sys.modules["model_picker"]
    return lib.ModelGrepIndex(entries)


# ---------------------------------------------------------------------------
# Soft-failure retry (the client never sees provider error content)
# ---------------------------------------------------------------------------


class TestSoftFailureRetry:
    @staticmethod
    def _make_logger(lib, plugin, pool=("pollinations/community/x", "pollinations/community/y")):
        """Logger wired to a warm catalog snapshot (no network in _candidate_cap)."""
        manager = lib.CatalogManager()
        manager._snapshot = lib.CatalogSnapshot(
            candidates=[
                lib.ModelCandidate(name=n, provider="pollinations", metricless=False, success_rate=0.99, requests=100)
                for n in pool
            ]
        )
        return plugin.ModelPickerStatsLogger(stats=lib.StatsRegistry(), manager=manager)

    @staticmethod
    def _anthropic_events(*texts):
        """Anthropic SSE event dicts: message_start, then one delta per text."""
        events = [
            {"type": "message_start", "message": {"type": "message_start", "role": "assistant", "model": "m"}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        ]
        for t in texts:
            events.append({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}})
        events.append({"type": "content_block_stop", "index": 0})
        return events

    @staticmethod
    def _fake_router_acompletion(monkeypatch, logger, responses):
        calls = {"n": 0, "kwargs": []}

        async def fake_router_acompletion(retry_data):
            calls["n"] += 1
            calls["kwargs"].append(retry_data)
            return responses[min(calls["n"] - 1, len(responses) - 1)]

        monkeypatch.setattr(logger, "_router_acompletion", fake_router_acompletion)
        return calls

    def test_streaming_retry_swallows_error_and_synthesizes_answer(self, mp, monkeypatch):
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        credits = "The account behind this API key doesn't have enough credits. Please top up."
        events = self._anthropic_events("Could not process", credits)
        good_resp = litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 3, "completion_tokens": 2},
        )
        calls = self._fake_router_acompletion(monkeypatch, logger, [good_resp])

        async def stream():
            for e in events:
                yield e

        request_data = {
            "model": "lite-llm/complexity",
            "messages": [{"role": "user", "content": "hi"}],
            "litellm_metadata": {"model_group": "pollinations/community/x"},
        }

        async def run():
            out = []
            async for chunk in logger.async_post_call_streaming_iterator_hook(None, stream(), request_data):
                out.append(chunk)
            return out

        out = asyncio.run(run())
        # the gated model was intercepted and excluded
        assert calls["n"] == 1
        assert "pollinations/community/x" in request_data["litellm_metadata"]["model_picker_exclude"]
        # the retry data was non-streaming
        assert calls["kwargs"][0]["stream"] is False
        # the client never sees the credits text...
        flat = "".join(plugin._event_text(c) for c in out)
        assert "enough credits" not in flat
        # ...but does see the retry's answer, followed by proper stream closure
        assert "Hello!" in flat
        types = [e.get("type") for c in out for e in plugin._chunk_events(c)]
        assert types[-2:] == ["message_delta", "message_stop"]
        # the failed model was recorded as a soft failure (demotes on first)
        derived = logger.stats.derived("pollinations/community/x")
        assert derived.soft_failures == 1
        # one soft failure is conclusive: the gated model ranks below healthy peers
        gated = lib.ModelCandidate(name="pollinations/community/x", provider="pollinations", metricless=True)
        healthy = metric_candidate(lib, "pollinations/openai/healthy", 0.9997, 87885)
        cfg = lib.PickerConfig()
        now = time.time() + cfg.recency_window_seconds + 1
        ranked = lib.rank_candidates([gated, healthy], lib.TIER_DEFAULT, logger.stats, cfg, now=now)
        assert ranked[0].candidate.name == "pollinations/openai/healthy"

    def test_streaming_clean_response_passes_through_untouched(self, mp, monkeypatch):
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        calls = self._fake_router_acompletion(monkeypatch, logger, [])
        events = self._anthropic_events("Just a normal reply, mentions credits in passing.")

        async def stream():
            for e in events:
                yield e

        async def run():
            out = []
            async for chunk in logger.async_post_call_streaming_iterator_hook(
                None, stream(), {"model": "m", "messages": [], "litellm_metadata": {"model_group": "z-ai/glm-5.3"}}
            ):
                out.append(chunk)
            return out

        out = asyncio.run(run())
        assert out == events  # byte-identical pass-through, no retry
        assert calls["n"] == 0

    def test_streaming_all_retries_fail_yields_fallback_notice(self, mp, monkeypatch):
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        credits = "The account behind this API key doesn't have enough credits. Please top up."
        bad = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": credits}, "finish_reason": "stop"}])
        calls = self._fake_router_acompletion(
            monkeypatch, logger, [bad] * (len(("pollinations/community/x", "pollinations/community/y")) + plugin._RETRY_WALK_SLACK)
        )
        events = self._anthropic_events(credits)

        async def stream():
            for e in events:
                yield e

        async def run():
            out = []
            async for chunk in logger.async_post_call_streaming_iterator_hook(
                None, stream(), {"model": "m", "messages": [{"role": "user", "content": "hi"}], "litellm_metadata": {}}
            ):
                out.append(chunk)
            return out

        out = asyncio.run(run())
        flat = "".join(plugin._event_text(c) for c in out)
        assert "enough credits" not in flat
        # the walk is bounded by the candidate pool (2 candidates + slack),
        # and the notice reports the true attempt count and last failure
        expected_attempts = len(("pollinations/community/x", "pollinations/community/y")) + plugin._RETRY_WALK_SLACK
        assert f"{expected_attempts} attempts" in flat
        assert "provider error in response content" in flat
        assert calls["n"] == expected_attempts - 1

    def test_retry_data_routes_through_entry_model(self, mp):
        """The router rewrites data['model'] to the resolved deployment; retries
        must re-enter the original tier entry so the picker can advance."""
        lib, plugin = mp
        logger = plugin.ModelPickerStatsLogger(stats=lib.StatsRegistry())
        request_data = {
            "model": "pollinations/openai/gpt-5.4-nano",  # resolved by the router
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 300,
            "litellm_metadata": {"model_group": "lite-llm/complexity"},
        }
        retry = logger._retry_data(request_data)
        assert retry["model"] == "lite-llm/complexity"
        assert retry["stream"] is False
        # direct (non-tier) calls keep their own model
        direct = logger._retry_data({"model": "pollinations/openai/gpt-5.4-nano", "messages": [{"role": "user", "content": "hi"}]})
        assert direct["model"] == "pollinations/openai/gpt-5.4-nano"

    def test_streaming_hard_failure_continues_the_walk(self, mp, monkeypatch):
        """One provider erroring hard must not end the retry walk."""
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        credits = "The account behind this API key doesn't have enough credits. Please top up."
        events = self._anthropic_events(credits)

        async def stream():
            for e in events:
                yield e

        calls = {"n": 0}

        async def flaky_then_good(retry_data):
            calls["n"] += 1
            if calls["n"] == 1:
                raise litellm.Timeout("Request timed out", model="m")
            return litellm.ModelResponse(
                choices=[{"message": {"role": "assistant", "content": "Recovered!"}, "finish_reason": "stop"}]
            )

        monkeypatch.setattr(logger, "_router_acompletion", flaky_then_good)
        out = []

        async def run():
            async for chunk in logger.async_post_call_streaming_iterator_hook(
                None, stream(), {"model": "m", "messages": [{"role": "user", "content": "hi"}], "litellm_metadata": {}}
            ):
                out.append(chunk)

        asyncio.run(run())
        flat = "".join(plugin._event_text(c) for c in out)
        assert "enough credits" not in flat
        assert "Recovered!" in flat
        assert calls["n"] == 2

    def test_non_streaming_soft_failure_replaced_by_retry(self, mp, monkeypatch):
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        credits = "The account behind this API key doesn't have enough credits. Please top up."
        bad = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": credits}, "finish_reason": "stop"}])
        good = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}])
        calls = self._fake_router_acompletion(monkeypatch, logger, [good])
        result = asyncio.run(
            logger.async_post_call_success_hook(
                None,
                {"model": "lite-llm/complexity", "messages": [{"role": "user", "content": "hi"}], "litellm_metadata": {"model_group": "pollinations/community/x"}},
                bad,
            )
        )
        assert result is good
        assert calls["n"] == 1

    def test_in_band_error_event_before_content_retries(self, mp, monkeypatch):
        """litellm's Anthropic adapter converts mid-stream exceptions into
        in-band error events; the hook must drop them (never yield) and retry
        pre-content, so the client never sees an error frame."""
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        good = litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": "Recovered from in-band error"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 3, "completion_tokens": 4},
        )
        calls = self._fake_router_acompletion(monkeypatch, logger, [good])

        async def error_stream():
            yield {"type": "message_start", "message": {"type": "message", "role": "assistant", "model": "m"}}
            yield {"type": "error", "error": {"type": "api_error", "message": "Timeout on reading data from socket"}}

        out = []

        async def run():
            async for chunk in logger.async_post_call_streaming_iterator_hook(
                None, error_stream(), {"model": "lite-llm/complexity", "messages": [{"role": "user", "content": "hi"}], "litellm_metadata": {"model_group": "lite-llm/complexity"}}
            ):
                out.append(chunk)

        asyncio.run(run())
        events = [e for c in out for e in plugin._chunk_events(c)]
        types = [e.get("type") for e in events]
        flat = "".join(plugin._event_text(c) for c in out)
        assert "error" not in types  # the in-band error never reached the client
        assert "Recovered from in-band error" in flat
        assert calls["n"] == 1
        assert types[-2:] == ["message_delta", "message_stop"]

    def test_in_band_error_event_after_content_retries(self, mp, monkeypatch):
        """In-band error after partial content: the error frame is stripped, the
        failed model is demoted and excluded, and the walk retries with a
        different model — the retry's answer continues the stream so a
        truncated answer never ends the turn as if it were complete."""
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        good = litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": "Recovered from in-band error"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 3, "completion_tokens": 4},
        )
        calls = self._fake_router_acompletion(monkeypatch, logger, [good])

        async def error_stream():
            yield {"type": "message_start", "message": {"type": "message", "role": "assistant", "model": "m"}}
            yield {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
            yield {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "partial answer "}}
            yield {"type": "error", "error": {"type": "api_error", "message": "Timeout on reading data from socket"}}

        request_data = {
            "model": "lite-llm/complexity",
            "messages": [{"role": "user", "content": "hi"}],
            "litellm_metadata": {"model_group": "pollinations/community/x"},
        }
        out = []

        async def run():
            async for chunk in logger.async_post_call_streaming_iterator_hook(None, error_stream(), request_data):
                out.append(chunk)

        asyncio.run(run())
        events = [e for c in out for e in plugin._chunk_events(c)]
        types = [e.get("type") for e in events]
        flat = "".join(plugin._event_text(c) for c in out)
        assert "error" not in types  # the in-band error never reached the client
        assert "Timeout on reading data from socket" not in flat
        assert flat.startswith("partial answer ")  # already delivered, kept
        assert "Recovered from in-band error" in flat  # the retry's answer continues the stream
        assert types.count("content_block_start") == 1  # continued in the same block
        assert calls["n"] == 1  # retried with a different model
        assert "pollinations/community/x" in request_data["litellm_metadata"]["model_picker_exclude"]
        assert logger.stats.derived("pollinations/community/x").n_obs >= 1  # demoted
        assert types[-2:] == ["message_delta", "message_stop"]

    def test_in_band_error_sse_frame_string_detected(self, mp):
        lib, plugin = mp
        assert plugin._is_in_band_error('event: error\ndata: {"type":"error","error":{"message":"boom"}}\n\n')
        assert plugin._is_in_band_error({"type": "error", "error": {"message": "boom"}})
        assert plugin._is_in_band_error({"error": {"message": "boom"}})
        assert not plugin._is_in_band_error({"type": "content_block_delta", "delta": {"text": "fine"}})
        assert not plugin._is_in_band_error('data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"ok"}}\n\n')

    def test_in_band_error_failure_recorded(self, mp):
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)

        async def error_stream():
            yield {"type": "message_start", "message": {"type": "message", "role": "assistant", "model": "m"}}
            yield {"type": "error", "error": {"type": "api_error", "message": "upstream drop"}}

        async def run():
            async for _ in logger.async_post_call_streaming_iterator_hook(
                None, error_stream(), {"model": "m", "messages": [{"role": "user", "content": "hi"}], "litellm_metadata": {"model_group": "pollinations/x"}}
            ):
                pass

        asyncio.run(run())
        d = logger.stats.derived("pollinations/x")
        assert d.n_obs >= 1  # the stall demotes the group

    def test_midstream_failure_before_content_retries(self, mp, monkeypatch):
        """Upstream stream dying before any text was yielded: the walk retries
        and the client receives a complete, clean answer (message_start + full
        block), never seeing the failure."""
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        good = litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": "Recovered mid-stream"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 3, "completion_tokens": 4},
        )
        calls = self._fake_router_acompletion(monkeypatch, logger, [good])

        async def dying_stream():
            yield {"type": "message_start", "message": {"type": "message_start", "role": "assistant", "model": "m"}}
            raise RuntimeError("connection reset by peer")

        out = []

        async def run():
            async for chunk in logger.async_post_call_streaming_iterator_hook(
                None, dying_stream(), {"model": "lite-llm/complexity", "messages": [{"role": "user", "content": "hi"}], "litellm_metadata": {"model_group": "lite-llm/complexity"}}
            ):
                out.append(chunk)

        asyncio.run(run())
        events = [e for c in out for e in plugin._chunk_events(c)]
        types = [e.get("type") for e in events]
        flat = "".join(plugin._event_text(c) for c in out)
        assert "Recovered mid-stream" in flat
        assert calls["n"] == 1
        # a complete stream shape: start -> block -> delta -> stop -> delta -> stop
        assert types[0] == "message_start"
        assert types[-2:] == ["message_delta", "message_stop"]
        assert "content_block_start" in types and "content_block_stop" in types

    def test_midstream_failure_after_content_retries(self, mp, monkeypatch):
        """Upstream stream dying after partial content: the failed model is
        demoted and excluded, and the walk retries with a different model;
        the retry's answer continues the stream after the partial instead of
        letting a truncated answer end the turn."""
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        good = litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": "Recovered mid-stream"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 3, "completion_tokens": 4},
        )
        calls = self._fake_router_acompletion(monkeypatch, logger, [good])

        async def dying_stream():
            yield {"type": "message_start", "message": {"type": "message_start", "role": "assistant", "model": "m"}}
            yield {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
            yield {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "partial answer "}}
            raise RuntimeError("connection reset by peer")

        request_data = {
            "model": "lite-llm/complexity",
            "messages": [{"role": "user", "content": "hi"}],
            "litellm_metadata": {"model_group": "pollinations/community/x"},
        }
        out = []

        async def run():
            async for chunk in logger.async_post_call_streaming_iterator_hook(None, dying_stream(), request_data):
                out.append(chunk)

        asyncio.run(run())
        events = [e for c in out for e in plugin._chunk_events(c)]
        types = [e.get("type") for e in events]
        flat = "".join(plugin._event_text(c) for c in out)
        assert flat.startswith("partial answer ")  # already delivered, kept
        assert "Recovered mid-stream" in flat  # the retry's answer continues the stream
        assert "connection reset" not in flat
        assert types.count("content_block_start") == 1  # continued in the same block
        assert calls["n"] == 1  # retried with a different model
        assert "pollinations/community/x" in request_data["litellm_metadata"]["model_picker_exclude"]
        assert logger.stats.derived("pollinations/community/x").n_obs >= 1  # demoted
        # clean closure, no error frame material
        assert types[-2:] == ["message_delta", "message_stop"]
        assert "error" not in flat.lower()

    def test_midstream_failure_after_content_walk_exhausted_appends_notice(self, mp, monkeypatch):
        """Post-content failure with every retry failing too: the fallback
        notice is appended after the partial so the client knows the answer is
        incomplete; the turn still closes cleanly."""
        lib, plugin = mp
        logger = self._make_logger(lib, plugin)
        credits = "The account behind this API key doesn't have enough credits. Please top up."
        bad = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": credits}, "finish_reason": "stop"}])
        calls = self._fake_router_acompletion(
            monkeypatch, logger, [bad] * (len(("pollinations/community/x", "pollinations/community/y")) + plugin._RETRY_WALK_SLACK)
        )

        async def dying_stream():
            yield {"type": "message_start", "message": {"type": "message_start", "role": "assistant", "model": "m"}}
            yield {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
            yield {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "partial answer "}}
            raise RuntimeError("connection reset by peer")

        out = []

        async def run():
            async for chunk in logger.async_post_call_streaming_iterator_hook(
                None, dying_stream(), {"model": "lite-llm/complexity", "messages": [{"role": "user", "content": "hi"}], "litellm_metadata": {}}
            ):
                out.append(chunk)

        asyncio.run(run())
        events = [e for c in out for e in plugin._chunk_events(c)]
        types = [e.get("type") for e in events]
        flat = "".join(plugin._event_text(c) for c in out)
        assert flat.startswith("partial answer ")  # already delivered, kept
        assert "[model_picker]" in flat  # the notice follows the partial
        assert "connection reset" not in flat
        assert calls["n"] >= 1  # the walk did try other models
        assert types[-2:] == ["message_delta", "message_stop"]

    def test_picker_honors_exclude_metadata(self, fresh, env_enabled, monkeypatch):
        lib, test_plugin, cfg, stats, manager = fresh

        async def fake_snapshot(ml=None):
            return snapshot_with(lib, free_plugin_pool(lib))

        monkeypatch.setattr(manager, "get_snapshot", fake_snapshot)
        metadata = {
            "litellm_call_id": "call-x",
            "model_picker_exclude": ["pollinations/community/vendouple/deepseek-v4-pro"],
        }
        context = make_context(lib, ["lite-llm/default"], metadata=metadata)
        result = asyncio.run(test_plugin.run(context))
        assert result.candidate_models[0] != "pollinations/community/vendouple/deepseek-v4-pro"


# ---------------------------------------------------------------------------
# Thinking-only retry (a turn that would end on thinking alone is retried)
# ---------------------------------------------------------------------------


class TestThinkingOnlyRetry:
    """A completed response that is thinking-only on a turn-ending stop
    reason must retry with the model excluded — but ONLY then: thinking
    mid-stream, thinking beside text/tool calls, and thinking-only on a
    turn-continuing stop reason must all pass through untouched."""

    @staticmethod
    def _thinking_stream(stop_reason="end_turn"):
        """Realistic anthropic stream: thinking block, then the close."""
        return [
            {"type": "message_start", "message": {"type": "message", "role": "assistant", "model": "m"}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "First, call functions.Bash"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": {"output_tokens": 10}},
            {"type": "message_stop"},
        ]

    @staticmethod
    def _anthropic_response(blocks, stop_reason="end_turn"):
        response = {"id": "msg_test", "type": "message", "role": "assistant", "model": "m", "content": blocks}
        if stop_reason is not None:
            response["stop_reason"] = stop_reason
        return response

    def test_detector_anthropic_shapes(self, mp):
        lib, plugin = mp
        thinking = {"type": "thinking", "thinking": "plan"}
        text = {"type": "text", "text": "answer"}
        empty_text = {"type": "text", "text": ""}
        tool_use = {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {}}
        redacted = {"type": "redacted_thinking", "data": "opaque"}
        assert plugin._response_is_thinking_only(self._anthropic_response([thinking]))
        assert plugin._response_is_thinking_only(self._anthropic_response([thinking, empty_text]))
        assert plugin._response_is_thinking_only(self._anthropic_response([redacted]))
        assert plugin._response_is_thinking_only(self._anthropic_response([thinking], stop_reason="max_tokens"))
        assert plugin._response_is_thinking_only(self._anthropic_response([thinking], stop_reason=None))
        assert not plugin._response_is_thinking_only(self._anthropic_response([thinking, text]))
        assert not plugin._response_is_thinking_only(self._anthropic_response([thinking, tool_use]))
        assert not plugin._response_is_thinking_only(self._anthropic_response([text]))
        assert not plugin._response_is_thinking_only(self._anthropic_response([]))
        # a turn-continuing stop reason never fires, even with nothing actionable
        assert not plugin._response_is_thinking_only(self._anthropic_response([thinking], stop_reason="tool_use"))
        assert not plugin._response_is_thinking_only(self._anthropic_response([thinking], stop_reason="refusal"))

    def test_detector_openai_shapes(self, mp):
        lib, plugin = mp

        def msg(reasoning=None, content=None, tool_calls=None):
            return types.SimpleNamespace(reasoning_content=reasoning, content=content, tool_calls=tool_calls)

        def resp(message, finish):
            return types.SimpleNamespace(
                model="pollinations/community/x",
                choices=[types.SimpleNamespace(message=message, finish_reason=finish)],
            )

        assert plugin._response_is_thinking_only(resp(msg(reasoning="plan"), "stop"))
        assert plugin._response_is_thinking_only(resp(msg(reasoning="plan"), "length"))
        assert not plugin._response_is_thinking_only(resp(msg(reasoning="plan", content="hi"), "stop"))
        assert not plugin._response_is_thinking_only(
            resp(msg(reasoning="plan", tool_calls=[{"id": "1", "function": {"name": "Bash"}}]), "tool_calls")
        )
        assert not plugin._response_is_thinking_only(resp(msg(), "stop"))
        # dict-shaped OpenAI responses behave the same
        assert plugin._response_is_thinking_only(
            {"choices": [{"message": {"role": "assistant", "content": None, "reasoning_content": "plan"}, "finish_reason": "stop"}]}
        )
        assert not plugin._response_is_thinking_only(
            {"choices": [{"message": {"role": "assistant", "content": None, "reasoning_content": "plan"}, "finish_reason": "tool_calls"}]}
        )
        assert not plugin._response_is_thinking_only({"choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}]})

    def test_streaming_thinking_only_retries_with_exclusion(self, mp, monkeypatch):
        lib, plugin = mp
        logger = TestSoftFailureRetry._make_logger(lib, plugin)
        good = litellm.ModelResponse(
            choices=[{"message": {"role": "assistant", "content": "Here is the listing:"}, "finish_reason": "stop"}],
            usage={"prompt_tokens": 3, "completion_tokens": 4},
        )
        calls = TestSoftFailureRetry._fake_router_acompletion(monkeypatch, logger, [good])
        events = self._thinking_stream()
        request_data = {
            "model": "lite-llm/complexity",
            "messages": [{"role": "user", "content": "hi"}],
            "litellm_metadata": {"model_group": "pollinations/community/x"},
        }

        async def stream():
            for e in events:
                yield e

        async def run():
            out = []
            async for chunk in logger.async_post_call_streaming_iterator_hook(None, stream(), request_data):
                out.append(chunk)
            return out

        out = asyncio.run(run())
        assert calls["n"] == 1
        assert "pollinations/community/x" in request_data["litellm_metadata"]["model_picker_exclude"]
        flat = "".join(plugin._event_text(c) for c in out)
        assert "Here is the listing:" in flat  # the retry's answer reaches the client
        assert "First, call functions.Bash" in flat  # already-delivered thinking stays
        types_seen = [e.get("type") for c in out for e in plugin._chunk_events(c)]
        assert types_seen.count("message_delta") == 1  # the original end_turn close was dropped
        assert types_seen.count("message_stop") == 1
        assert types_seen[-2:] == ["message_delta", "message_stop"]
        # ERROR, not SOFT: one thinking-only turn must not instantly demote
        derived = logger.stats.derived("pollinations/community/x")
        assert derived.n_obs >= 1
        assert derived.soft_failures == 0

    def test_streaming_thinking_with_text_passes_through(self, mp, monkeypatch):
        lib, plugin = mp
        logger = TestSoftFailureRetry._make_logger(lib, plugin)
        calls = TestSoftFailureRetry._fake_router_acompletion(monkeypatch, logger, [])
        events = [
            {"type": "message_start", "message": {"type": "message", "role": "assistant", "model": "m"}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "plan"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "answer"}},
            {"type": "content_block_stop", "index": 1},
            {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 5}},
            {"type": "message_stop"},
        ]

        async def stream():
            for e in events:
                yield e

        async def run():
            out = []
            async for chunk in logger.async_post_call_streaming_iterator_hook(None, stream(), {"model": "m", "messages": []}):
                out.append(chunk)
            return out

        assert asyncio.run(run()) == events
        assert calls["n"] == 0

    def test_streaming_thinking_only_on_tool_use_reason_passes_through(self, mp, monkeypatch):
        lib, plugin = mp
        logger = TestSoftFailureRetry._make_logger(lib, plugin)
        calls = TestSoftFailureRetry._fake_router_acompletion(monkeypatch, logger, [])
        events = self._thinking_stream(stop_reason="tool_use")

        async def stream():
            for e in events:
                yield e

        async def run():
            out = []
            async for chunk in logger.async_post_call_streaming_iterator_hook(None, stream(), {"model": "m", "messages": []}):
                out.append(chunk)
            return out

        assert asyncio.run(run()) == events
        assert calls["n"] == 0

    def test_streaming_thinking_with_tool_use_passes_through(self, mp, monkeypatch):
        lib, plugin = mp
        logger = TestSoftFailureRetry._make_logger(lib, plugin)
        calls = TestSoftFailureRetry._fake_router_acompletion(monkeypatch, logger, [])
        events = [
            {"type": "message_start", "message": {"type": "message", "role": "assistant", "model": "m"}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "plan"}},
            {"type": "content_block_stop", "index": 0},
            {"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {}}},
            {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{}"}},
            {"type": "content_block_stop", "index": 1},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None}, "usage": {"output_tokens": 5}},
            {"type": "message_stop"},
        ]

        async def stream():
            for e in events:
                yield e

        async def run():
            out = []
            async for chunk in logger.async_post_call_streaming_iterator_hook(None, stream(), {"model": "m", "messages": []}):
                out.append(chunk)
            return out

        assert asyncio.run(run()) == events
        assert calls["n"] == 0

    def test_non_streaming_thinking_only_swapped_for_retry(self, mp, monkeypatch):
        lib, plugin = mp
        logger = TestSoftFailureRetry._make_logger(lib, plugin)
        good = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}])
        calls = TestSoftFailureRetry._fake_router_acompletion(monkeypatch, logger, [good])
        data = {
            "model": "lite-llm/complexity",
            "messages": [{"role": "user", "content": "hi"}],
            "litellm_metadata": {"model_group": "pollinations/community/x"},
        }
        result = asyncio.run(
            logger.async_post_call_success_hook(
                None, data, self._anthropic_response([{"type": "thinking", "thinking": "plan"}])
            )
        )
        assert calls["n"] == 1
        assert "pollinations/community/x" in data["litellm_metadata"]["model_picker_exclude"]
        assert result["content"] == [{"type": "text", "text": "OK"}]
        # and a normal text response is untouched
        text_resp = self._anthropic_response([{"type": "text", "text": "fine"}])
        assert asyncio.run(logger.async_post_call_success_hook(None, data, text_resp)) is text_resp

    def test_success_logger_records_thinking_only_as_error_not_success(self, mp):
        lib, plugin = mp
        logger = TestSoftFailureRetry._make_logger(lib, plugin)
        kwargs = {"litellm_metadata": {"model_group": "pollinations/community/x"}}
        now = datetime.now()
        asyncio.run(
            logger.async_log_success_event(
                kwargs, self._anthropic_response([{"type": "thinking", "thinking": "plan"}]), now, now
            )
        )
        derived = logger.stats.derived("pollinations/community/x")
        assert derived.n_obs == 1
        assert derived.soft_failures == 0
        assert derived.last_obs_was_failure is True
        assert derived.failures == pytest.approx(1.0)

    def test_walk_continues_past_thinking_only_retry(self, mp, monkeypatch):
        lib, plugin = mp
        logger = TestSoftFailureRetry._make_logger(lib, plugin)
        thinking_y = types.SimpleNamespace(
            model="pollinations/community/y",
            choices=[
                types.SimpleNamespace(
                    message=types.SimpleNamespace(reasoning_content="plan", content=None, tool_calls=None),
                    finish_reason="stop",
                )
            ],
        )
        good = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "Recovered"}, "finish_reason": "stop"}])
        calls = TestSoftFailureRetry._fake_router_acompletion(monkeypatch, logger, [thinking_y, good])
        request_data = {
            "model": "lite-llm/complexity",
            "messages": [{"role": "user", "content": "hi"}],
            "litellm_metadata": {"model_group": "pollinations/community/x"},
        }
        result, summary = asyncio.run(
            logger._retry_until_clean(
                request_data,
                "pollinations/community/x",
                first_failure_class=lib.FAILURE_CLASS_ERROR,
                first_failure_label="thinking-only response",
            )
        )
        assert result is good
        assert calls["n"] == 2
        excluded = request_data["litellm_metadata"]["model_picker_exclude"]
        assert "pollinations/community/x" in excluded
        assert "pollinations/community/y" in excluded
        assert logger.stats.derived("pollinations/community/x").soft_failures == 0
        assert logger.stats.derived("pollinations/community/y").soft_failures == 0


# ---------------------------------------------------------------------------
# Anthropically-shaped retries (the /v1/messages walk fix, litellm5.log)
# ---------------------------------------------------------------------------


class TestAnthropicRetryEntry:
    """The walk must re-dispatch /v1/messages bodies through the anthropic
    entry: those bodies stay anthropic-shaped (top-level system,
    tool_use/tool_result content blocks) all the way to the hooks, and
    acompletion ships the blocks to OpenAI-format providers, which 400 every
    candidate ("Invalid user message") — burning and demoting the whole pool
    on a payload no provider ever accepted."""

    def test_is_anthropic_request_detection(self, mp):
        lib, plugin = mp
        assert plugin._is_anthropic_request({"system": "Be helpful.", "messages": [{"role": "user", "content": "hi"}]})
        assert plugin._is_anthropic_request(
            {"messages": [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}]}
        )
        assert plugin._is_anthropic_request(
            {"messages": [{"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "f", "input": {}}]}]}
        )
        assert plugin._is_anthropic_request(
            {"messages": [], "tools": [{"name": "f", "description": "d", "input_schema": {}}]}
        )
        # text-only bodies are valid in BOTH formats — they stay on the openai entry
        assert not plugin._is_anthropic_request({"messages": [{"role": "user", "content": "hi"}]})
        assert not plugin._is_anthropic_request({"messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]})
        assert not plugin._is_anthropic_request({"messages": [], "tools": [{"type": "function", "function": {"name": "f"}}]})
        assert not plugin._is_anthropic_request("not a dict")

    def test_retry_entry_dispatches_by_shape(self, mp):
        lib, plugin = mp
        calls = []

        class FakeRouter:
            async def acompletion(self, **kwargs):
                calls.append(("acompletion", kwargs))
                return "openai-response"

            async def anthropic_messages(self, **kwargs):
                calls.append(("anthropic_messages", kwargs))
                return "anthropic-response"

        router = FakeRouter()
        anthropic_body = {"model": "m", "system": "s", "messages": [{"role": "user", "content": "hi"}]}
        assert asyncio.run(plugin.ModelPickerStatsLogger._retry_entry_call(router, anthropic_body)) == "anthropic-response"
        assert calls[0][0] == "anthropic_messages"
        openai_body = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
        assert asyncio.run(plugin.ModelPickerStatsLogger._retry_entry_call(router, openai_body)) == "openai-response"
        assert calls[1][0] == "acompletion"

    def test_retry_entry_fallbacks(self, mp, monkeypatch):
        lib, plugin = mp

        class OpenAIOnlyRouter:
            async def acompletion(self, **kwargs):
                return "degraded"

        out = asyncio.run(
            plugin.ModelPickerStatsLogger._retry_entry_call(OpenAIOnlyRouter(), {"model": "m", "system": "s", "messages": []})
        )
        assert out == "degraded"  # no anthropic entry on this build: degrade, never crash

        async def fake_anthropic(**kwargs):
            return "module-anthropic"

        async def fake_openai(**kwargs):
            return "module-openai"

        monkeypatch.setattr(litellm, "anthropic_messages", fake_anthropic, raising=False)
        monkeypatch.setattr(litellm, "acompletion", fake_openai, raising=False)
        assert (
            asyncio.run(plugin.ModelPickerStatsLogger._retry_entry_call(None, {"model": "m", "system": "s", "messages": []}))
            == "module-anthropic"
        )
        assert asyncio.run(plugin.ModelPickerStatsLogger._retry_entry_call(None, {"model": "m", "messages": []})) == "module-openai"

    def test_retry_data_carries_anthropic_fields(self, mp):
        lib, plugin = mp
        logger = plugin.ModelPickerStatsLogger(stats=lib.StatsRegistry())
        request_data = {
            "model": "lite-llm/complexity",
            "messages": [{"role": "user", "content": "hi"}],
            "system": "You are Claude Code.",  # top-level on /v1/messages
            "stop_sequences": ["\n\n"],
            "thinking": {"type": "enabled", "budget_tokens": 1024},
            "max_tokens": 32000,
            "litellm_metadata": {"model_group": "lite-llm/complexity"},
        }
        retry = logger._retry_data(request_data)
        assert retry["system"] == "You are Claude Code."  # was silently dropped
        assert retry["stop_sequences"] == ["\n\n"]
        assert retry["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        assert retry["stream"] is False
        assert retry["model"] == "lite-llm/complexity"

    def test_midstream_failure_anthropic_request_retries_through_anthropic_entry(self, mp, monkeypatch):
        """The 1.5.96 live failure (litellm5.log): an anthropic request's
        mid-stream cutoff walked into acompletion retries that 400'd on every
        candidate. The walk must re-dispatch through the router's
        anthropic_messages entry, keeping the system prompt, and synthesize
        the retry's answer into the stream."""
        lib, plugin = mp
        logger = TestSoftFailureRetry._make_logger(lib, plugin)
        router_calls = []

        async def fake_anthropic_messages(**kwargs):
            router_calls.append(kwargs)
            return {
                "id": "msg_retry",
                "role": "assistant",
                "content": [{"type": "text", "text": "Recovered answer"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 11, "output_tokens": 7},
            }

        import litellm.proxy.proxy_server as proxy_server_module

        monkeypatch.setattr(
            proxy_server_module,
            "llm_router",
            types.SimpleNamespace(anthropic_messages=fake_anthropic_messages),
        )

        async def dying_stream():
            yield {"type": "message_start", "message": {"type": "message", "role": "assistant", "model": "m"}}
            yield {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}
            yield {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "partial "}}
            raise RuntimeError("connection reset by peer")

        request_data = {
            "model": "lite-llm/complexity",
            "system": "You are Claude Code.",
            "messages": [
                {"role": "user", "content": "run the tests"},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "tu1", "name": "bash", "input": {"command": "pytest"}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu1", "content": "3 passed"}]},
            ],
            "litellm_metadata": {"model_group": "lite-llm/complexity"},
        }
        out = []

        async def run():
            async for chunk in logger.async_post_call_streaming_iterator_hook(None, dying_stream(), request_data):
                out.append(chunk)

        asyncio.run(run())
        # the retry went through the ANTHROPIC entry with the payload intact
        assert len(router_calls) == 1
        assert router_calls[0]["system"] == "You are Claude Code."
        assert router_calls[0]["stream"] is False
        assert router_calls[0]["model"] == "lite-llm/complexity"
        assert router_calls[0]["messages"] == request_data["messages"]
        # the client got the partial plus the retry's answer, closed cleanly
        events = [e for c in out for e in plugin._chunk_events(c)]
        types_seen = [e.get("type") for e in events]
        flat = "".join(plugin._event_text(c) for c in out)
        assert flat.startswith("partial ")
        assert "Recovered answer" in flat
        assert "error" not in types_seen
        assert types_seen[-2:] == ["message_delta", "message_stop"]
        # usage and stop reason carried in anthropic vocabulary
        closing = [e for e in events if e.get("type") == "message_delta"][0]
        assert closing["delta"]["stop_reason"] == "end_turn"
        assert closing["usage"] == {"input_tokens": 11, "output_tokens": 7}
        # the failed model was recorded (demoted)
        assert logger.stats.derived("lite-llm/complexity").n_obs >= 1

    def test_anthropic_retry_tool_use_synthesized(self, mp):
        lib, plugin = mp
        retry_resp = {
            "content": [
                {"type": "text", "text": "Running the tests"},
                {"type": "tool_use", "id": "tu_9", "name": "bash", "input": {"command": "pytest"}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 5, "output_tokens": 6},
        }
        events = plugin.ModelPickerStatsLogger._synthesize_tail_events(retry_resp, None, 0)
        types_seen = [e.get("type") for e in events]
        tool_start = [e for e in events if e.get("type") == "content_block_start" and e["content_block"]["type"] == "tool_use"]
        assert len(tool_start) == 1
        assert tool_start[0]["content_block"]["name"] == "bash"
        assert tool_start[0]["content_block"]["id"] == "tu_9"
        delta = [e for e in events if e.get("type") == "content_block_delta" and e["delta"]["type"] == "input_json_delta"]
        assert json.loads(delta[0]["delta"]["partial_json"]) == {"command": "pytest"}
        closing = [e for e in events if e.get("type") == "message_delta"][0]
        assert closing["delta"]["stop_reason"] == "tool_use"
        assert closing["usage"] == {"input_tokens": 5, "output_tokens": 6}
        assert types_seen[-1] == "message_stop"

    def test_openai_retry_tool_calls_synthesized(self, mp):
        lib, plugin = mp
        retry_resp = litellm.ModelResponse(
            choices=[
                {
                    "message": {
                        "role": "assistant",
                        "content": "Calling the tool",
                        "tool_calls": [{"id": "tc1", "function": {"name": "bash", "arguments": "{\"command\": \"ls\"}"}}],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            usage={"prompt_tokens": 2, "completion_tokens": 3},
        )
        events = plugin.ModelPickerStatsLogger._synthesize_tail_events(retry_resp, None, 0)
        tool_start = [e for e in events if e.get("type") == "content_block_start" and e["content_block"]["type"] == "tool_use"]
        assert tool_start[0]["content_block"]["name"] == "bash"
        delta = [e for e in events if e.get("type") == "content_block_delta" and e["delta"]["type"] == "input_json_delta"]
        assert json.loads(delta[0]["delta"]["partial_json"]) == {"command": "ls"}
        closing = [e for e in events if e.get("type") == "message_delta"][0]
        assert closing["delta"]["stop_reason"] == "tool_use"
        assert closing["usage"] == {"input_tokens": 2, "output_tokens": 3}

    def test_finish_reason_vocabulary_mapping(self, mp):
        lib, plugin = mp
        openai_stop = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "x"}, "finish_reason": "stop"}])
        assert plugin._finish_reason(openai_stop) == "end_turn"  # not the openai 'stop'
        openai_length = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "x"}, "finish_reason": "length"}])
        assert plugin._finish_reason(openai_length) == "max_tokens"
        openai_tools = litellm.ModelResponse(choices=[{"message": {"role": "assistant", "content": "x"}, "finish_reason": "tool_calls"}])
        assert plugin._finish_reason(openai_tools) == "end_turn"  # no synthesized blocks: never claim tool_use
        assert plugin._finish_reason(openai_tools, has_tool_uses=True) == "tool_use"
        assert plugin._finish_reason({"stop_reason": "max_tokens"}) == "max_tokens"
        assert plugin._finish_reason(None) == "end_turn"

    def test_non_streaming_anthropic_swap_carries_tools(self, mp):
        lib, plugin = mp
        retry_resp = {
            "content": [{"type": "tool_use", "id": "tu1", "name": "bash", "input": {"command": "ls"}}],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        out = plugin.ModelPickerStatsLogger._as_anthropic_dict({"id": "msg1", "model": "m"}, retry_resp, "")
        assert out["content"] == [{"type": "tool_use", "id": "tu1", "name": "bash", "input": {"command": "ls"}}]
        assert out["stop_reason"] == "tool_use"
        notice = plugin.ModelPickerStatsLogger._as_anthropic_dict({"id": "msg1", "model": "m"}, None, "notice text")
        assert notice["content"] == [{"type": "text", "text": "notice text"}]
        assert notice["stop_reason"] == "end_turn"


# ---------------------------------------------------------------------------
# Rubric ranking
# ---------------------------------------------------------------------------


class TestRubricRanking:
    def test_default_tier_strong_first_then_untried_then_health(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored_big = favored_candidate(lib, "z-ai/glm-5.3", ctx=1048576)
        favored_small = favored_candidate(lib, "nvidia/nemotron-3-super", provider="nvidia_nim", ctx=262144)
        strong_metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        weak_metric = metric_candidate(lib, "pollinations/openai/gpt-oss-20b", 0.9, 1000)
        ranked = lib.rank_candidates(
            [weak_metric, favored_small, strong_metric, favored_big], lib.TIER_DEFAULT, stats, cfg
        )
        order = [r.candidate.name for r in ranked]
        # Default tier now prefers known-strong health over untried models:
        # both metric models clear the strong threshold (Wilson ~1.0 and
        # ~0.88), so they rank by health first, then the untried models by
        # context. (Think tiers still favor untried first; see
        # test_think_tier_context_first_with_class_ties.)
        assert order == [
            "pollinations/openai/gpt-5.4-nano",
            "pollinations/openai/gpt-oss-20b",
            "z-ai/glm-5.3",
            "nvidia/nemotron-3-super",
        ]

    def test_llm7_untried_below_healthy_metric_backed(self, fresh):
        lib, _, cfg, stats, _ = fresh
        llm7_fast = favored_candidate(lib, "fast", provider="llm7")
        llm7_default = favored_candidate(lib, "default", provider="llm7")
        healthy = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        ranked = lib.rank_candidates([llm7_fast, healthy, llm7_default], lib.TIER_DEFAULT, stats, cfg)
        # try pollinations before llm7 even though the llm7 groups are untried
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/gpt-5.4-nano",
            "default",
            "fast",
        ]

    def test_untried_nim_still_favored_above_llm7(self, fresh):
        lib, _, cfg, stats, _ = fresh
        nim = favored_candidate(lib, "z-ai/glm-5.3", provider="nvidia_nim")
        llm7_fast = favored_candidate(lib, "fast", provider="llm7")
        ranked = lib.rank_candidates([llm7_fast, nim], lib.TIER_DEFAULT, stats, cfg)
        # only llm7 loses the untried benefit-of-the-doubt; NIM keeps it
        assert [r.candidate.name for r in ranked] == ["z-ai/glm-5.3", "fast"]

    def test_ultra_think_tier_context_first_with_class_ties(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored_1m = favored_candidate(lib, "z-ai/glm-5.3", ctx=1048576)
        metric_1m = metric_candidate(lib, "pollinations/openai/gpt-6-luna", 0.9997, 87885, ctx=1048576)
        metric_small = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885, ctx=400000)
        ranked = lib.rank_candidates([metric_small, metric_1m, favored_1m], lib.TIER_THINK, stats, cfg)
        order = [r.candidate.name for r in ranked]
        # 1M models first; on equal context and equal benchmark (both 0.0
        # here), demonstrated strong health beats being unmeasured.
        assert order == [
            "pollinations/openai/gpt-6-luna",
            "z-ai/glm-5.3",
            "pollinations/openai/gpt-5.4-nano",
        ]
        # But a higher benchmark still beats the health block: capability
        # is prioritized immediately after context.
        favored_1m.benchmark_score = 0.9
        metric_1m.benchmark_score = 0.5
        ranked = lib.rank_candidates([metric_1m, favored_1m], lib.TIER_THINK, stats, cfg)
        assert ranked[0].candidate.name == "z-ai/glm-5.3"

    def test_failure_demotion_after_min_obs(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored = favored_candidate(lib, "z-ai/glm-5.3")
        strong_metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        now = time.time()
        for _ in range(cfg.min_obs):
            stats.record_failure("z-ai/glm-5.3", lib.FAILURE_CLASS_TIMEOUT, now=now)
        # evaluate past the recency window so the guard doesn't mask ordering
        after_guard = now + cfg.recency_window_seconds + 1
        ranked = lib.rank_candidates([favored, strong_metric], lib.TIER_DEFAULT, stats, cfg, now=after_guard)
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/gpt-5.4-nano",
            "z-ai/glm-5.3",
        ]
        # the same window evidence re-demotes on the next evaluation
        ranked2 = lib.rank_candidates([favored, strong_metric], lib.TIER_DEFAULT, stats, cfg, now=after_guard)
        assert ranked2[0].candidate.name == "pollinations/openai/gpt-5.4-nano"
        # once the failure window ages out entirely, the group is promoted back
        # to untried (no longer KNOWN) — but the default tier still prefers
        # the known-strong metric model over an untried one, so promotion
        # restores eligibility, not the top spot.
        ranked3 = lib.rank_candidates(
            [favored, strong_metric], lib.TIER_DEFAULT, stats, cfg, now=now + 5 * cfg.half_life_seconds
        )
        assert [r.candidate.name for r in ranked3] == [
            "pollinations/openai/gpt-5.4-nano",
            "z-ai/glm-5.3",
        ]

    def test_perfect_small_sample_ranks_on_tracked_evidence(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored = favored_candidate(lib, "z-ai/glm-5.3")
        strong_metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        weak_metric = metric_candidate(lib, "pollinations/openai/gpt-oss-20b", 0.75, 20)
        now = time.time()
        for _ in range(cfg.min_obs * 3):
            stats.record_success("z-ai/glm-5.3", ttft_seconds=1.0, now=now)
        ranked = lib.rank_candidates(
            [weak_metric, strong_metric, favored], lib.TIER_DEFAULT, stats, cfg, now=now + 1
        )
        # a small perfect sample competes on our tracked evidence: above weak
        # published metrics, below a huge-volume published near-perfect one
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/gpt-5.4-nano",
            "z-ai/glm-5.3",
            "pollinations/openai/gpt-oss-20b",
        ]

    def test_auth_error_demotes_immediately(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored = favored_candidate(lib, "z-ai/glm-5.3")
        metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        stats.record_failure("z-ai/glm-5.3", lib.FAILURE_CLASS_AUTH)
        ranked = lib.rank_candidates([favored, metric], lib.TIER_DEFAULT, stats, cfg)
        assert ranked[0].candidate.name == "pollinations/openai/gpt-5.4-nano"

    def test_latency_demotion_and_floor(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored_slow = favored_candidate(lib, "z-ai/glm-5.3", ctx=1048576)
        metric_fast = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885, ctx=400000)
        now = time.time()
        for _ in range(cfg.min_obs):
            stats.record_success("z-ai/glm-5.3", ttft_seconds=cfg.demote_ttft_seconds * 4, now=now)
        ranked = lib.rank_candidates([favored_slow, metric_fast], lib.TIER_DEFAULT, stats, cfg)
        # latency proof fired -> class floor below metric-backed in default tier
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/gpt-5.4-nano",
            "z-ai/glm-5.3",
        ]

    def test_latency_floor_lifts_via_decay(self, fresh):
        lib, _, cfg, stats, _ = fresh
        # A latency-demoted model with a PERFECT success record vs a
        # mediocre metric-backed model: the floor holds it below while active,
        # and once the stale TTFT events age out of the window it competes on
        # evidence and wins.
        favored_slow = favored_candidate(lib, "z-ai/glm-5.3", ctx=1048576)
        mediocre_metric = metric_candidate(lib, "pollinations/degraded/model", 0.75, 20, ctx=1048576)
        base = time.time()
        for _ in range(cfg.min_obs):
            stats.record_success("z-ai/glm-5.3", ttft_seconds=cfg.demote_ttft_seconds * 4, now=base)
        ranked = lib.rank_candidates(
            [favored_slow, mediocre_metric], lib.TIER_DEFAULT, stats, cfg, now=base + 1
        )
        assert [r.candidate.name for r in ranked] == [
            "pollinations/degraded/model",
            "z-ai/glm-5.3",
        ]
        # long after the slow window: events pruned, ttft_n=0, floor lifted —
        # demotion stays sticky but the model ranks by its evidence (perfect
        # record) and overtakes the mediocre metric-backed model.
        ranked_after = lib.rank_candidates(
            [favored_slow, mediocre_metric], lib.TIER_DEFAULT, stats, cfg, now=base + 5 * cfg.half_life_seconds
        )
        assert [r.candidate.name for r in ranked_after] == [
            "z-ai/glm-5.3",
            "pollinations/degraded/model",
        ]

    def test_recency_guard_skip_and_restore(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored = favored_candidate(lib, "z-ai/glm-5.3")
        metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        now = time.time()
        stats.record_failure("z-ai/glm-5.3", lib.FAILURE_CLASS_TIMEOUT, now=now)
        ranked = lib.rank_candidates([favored, metric], lib.TIER_DEFAULT, stats, cfg, now=now + 5)
        assert ranked[0].candidate.name == "pollinations/openai/gpt-5.4-nano"
        # a success restores eligibility immediately (no longer guard-skipped);
        # the mixed 1-failure/1-success window scores 0.5, so the strong
        # published metric still outranks it on evidence
        stats.record_success("z-ai/glm-5.3", ttft_seconds=1.0, now=now + 6)
        ranked = lib.rank_candidates([favored, metric], lib.TIER_DEFAULT, stats, cfg, now=now + 7)
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/gpt-5.4-nano",
            "z-ai/glm-5.3",
        ]

    def test_recency_guard_expires(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored = favored_candidate(lib, "z-ai/glm-5.3")
        metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        now = time.time()
        stats.record_failure("z-ai/glm-5.3", lib.FAILURE_CLASS_TIMEOUT, now=now)
        ranked = lib.rank_candidates([favored, metric], lib.TIER_DEFAULT, stats, cfg, now=now + cfg.recency_window_seconds + 1)
        # the guard expires (candidate eligible again, no longer skipped) but
        # the all-failure window scores low, so the strong metric stays first
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/gpt-5.4-nano",
            "z-ai/glm-5.3",
        ]

    def test_recency_guard_all_guarded_falls_back(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored = favored_candidate(lib, "z-ai/glm-5.3")
        metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        now = time.time()
        stats.record_failure("z-ai/glm-5.3", lib.FAILURE_CLASS_TIMEOUT, now=now)
        stats.record_failure("pollinations/openai/gpt-5.4-nano", lib.FAILURE_CLASS_TIMEOUT, now=now)
        ranked = lib.rank_candidates([favored, metric], lib.TIER_DEFAULT, stats, cfg, now=now + 5)
        # nothing unguarded -> keep ranking rather than returning nothing
        assert len(ranked) == 2

    def test_attempt_exclusion(self, fresh):
        lib, _, cfg, stats, _ = fresh
        favored = favored_candidate(lib, "z-ai/glm-5.3")
        metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        ranked = lib.rank_candidates(
            [favored, metric], lib.TIER_DEFAULT, stats, cfg, exclude=frozenset({"z-ai/glm-5.3"})
        )
        assert [r.candidate.name for r in ranked] == ["pollinations/openai/gpt-5.4-nano"]
        # excluding everything falls back to the full ranked list
        ranked_all = lib.rank_candidates(
            [favored, metric],
            lib.TIER_DEFAULT,
            stats,
            cfg,
            exclude=frozenset({"z-ai/glm-5.3", "pollinations/openai/gpt-5.4-nano"}),
        )
        assert len(ranked_all) == 2

    def test_context_fit_filters_known_context_only(self, fresh):
        lib, _, cfg, stats, _ = fresh
        huge_request = 500000
        small_metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885, ctx=400000)
        big_metric = metric_candidate(lib, "pollinations/openai/gpt-6-luna", 0.999, 1000, ctx=1048576)
        unknown_ctx_favored = favored_candidate(lib, "nvidia/nemotron-3-super", provider="nvidia_nim", ctx=0)
        ranked = lib.rank_candidates(
            [small_metric, big_metric, unknown_ctx_favored],
            lib.TIER_DEFAULT,
            stats,
            cfg,
            estimate=huge_request,
        )
        names = [r.candidate.name for r in ranked]
        assert "pollinations/openai/gpt-5.4-nano" not in names  # known 400k < 500k estimate
        assert "pollinations/openai/gpt-6-luna" in names
        assert "nvidia/nemotron-3-super" in names  # unknown context bypasses fit

    def test_existence_check_marks_removed_models(self, fresh):
        """Catalog-driven candidates are born from the listing; the manager's
        per-provider stale-serve replaces the old existence-check mechanism."""
        lib, _, cfg, stats, _ = fresh
        gone = favored_candidate(lib, "old-model", provider="nvidia_nim")
        gone.available = False
        present = favored_candidate(lib, "z-ai/glm-5.3", provider="nvidia_nim")
        ranked = lib.rank_candidates([gone, present], lib.TIER_DEFAULT, stats, cfg)
        assert [r.candidate.name for r in ranked] == ["z-ai/glm-5.3"]

    def test_sustained_rate_limits_demote_and_recover(self, fresh):
        lib, _, cfg, stats, _ = fresh
        llm7 = favored_candidate(lib, "fast", provider="llm7")
        strong_metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        mediocre_metric = metric_candidate(lib, "pollinations/degraded/model", 0.75, 20)
        now = time.time()
        for _ in range(cfg.min_obs + 3):
            stats.record_failure("fast", lib.FAILURE_CLASS_RATE_LIMIT, now=now)
        derived = stats.derived("fast", now=now + 1)
        # evidence score depressed...
        assert derived.success_rate < 1.0
        # ...but rate limits never fire the hard demotion proof (busy-but-working)
        assert derived.demoted is False
        # a sustained 429 streak (daily token quota) sinks the tracked score
        # below healthy AND mediocre metric-backed candidates
        after_guard = now + cfg.recency_window_seconds + 1
        ranked = lib.rank_candidates(
            [llm7, strong_metric, mediocre_metric], lib.TIER_DEFAULT, stats, cfg, now=after_guard
        )
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/gpt-5.4-nano",
            "pollinations/degraded/model",
            "fast",
        ]
        # real successes promote it back above the mediocre candidate
        for _ in range(10):
            stats.record_success("fast", ttft_seconds=1.0, now=now + 2)
        ranked = lib.rank_candidates(
            [llm7, strong_metric, mediocre_metric], lib.TIER_DEFAULT, stats, cfg, now=now + 3
        )
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/gpt-5.4-nano",
            "fast",
            "pollinations/degraded/model",
        ]

    def test_single_rate_limit_failure_lands_midpack(self, fresh):
        lib, _, cfg, stats, _ = fresh
        llm7 = favored_candidate(lib, "fast", provider="llm7")
        strong_metric = metric_candidate(lib, "pollinations/openai/gpt-5.4-nano", 0.9997, 87885)
        zero_evidence = metric_candidate(lib, "pollinations/unknown/model", 1.0, 0)
        now = time.time()
        stats.record_failure("fast", lib.FAILURE_CLASS_RATE_LIMIT, now=now)
        # one transient 429 must not bury the group at zero: Laplace smoothing
        # puts it below healthy evidence but above zero-evidence candidates
        after_guard = now + cfg.recency_window_seconds + 1
        ranked = lib.rank_candidates(
            [llm7, strong_metric, zero_evidence], lib.TIER_DEFAULT, stats, cfg, now=after_guard
        )
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/gpt-5.4-nano",
            "fast",
            "pollinations/unknown/model",
        ]


# ---------------------------------------------------------------------------
# Provider catalog parsing (NIM, Ollama, LLM7)
# ---------------------------------------------------------------------------


class TestProviderCatalogs:
    def test_nim_models_parsed_with_nonchat_filtered(self, mp):
        lib, _ = mp
        payload = {
            "data": [
                {"id": "z-ai/glm-5.3"},
                {"id": "nvidia/nemotron-3-ultra-550b-a55b"},
                {"id": "nvidia/nemotron-3-embed-1b"},
                {"id": "nvidia/nv-embedqa-mistral-7b-v2"},
                {"id": "meta/llama-3.2-11b-vision-instruct"},
                {"id": "nvidia/llama-3.1-nemoguard-8b-content-safety"},
                {"id": "nvidia/nemotron-parse"},
                {"id": "nvidia/riva-translate-4b-instruct"},
                {"id": "snowflake/arctic-embed-l"},
            ]
        }
        candidates = lib.parse_nim_models(payload)
        names = {c.name for c in candidates}
        assert names == {"nvidia_nim/z-ai/glm-5.3", "nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b"}
        for c in candidates:
            assert c.provider == "nvidia_nim"
            assert c.metricless is True

    def test_llm7_models_parsed_with_type_endpoint_context(self, mp):
        lib, _ = mp
        payload = {
            "data": [
                {"id": "DeepSeek-V4.1-Flash", "model_type": "chat", "schema_endpoints": ["openai"],
                 "context_window": {"tokens": 400000},
                 "availability": {"old": 94.51, "mid": 96.3, "recent": 91.67},
                 "availability_last_hour_percent": 100.0,
                 "pricing": {"input": 0.3, "output": 1.2, "currency": "USD"}},
                {"id": "Some-Vision", "model_type": "image", "schema_endpoints": ["openai"]},
                {"id": "AnthropicOnly", "model_type": "chat", "schema_endpoints": ["anthropic"]},
                {"id": "NoMeta", "model_type": "chat"},
            ]
        }
        by_name = {c.name: c for c in lib.parse_llm7_models(payload)}
        # priced models are filtered out (free-only): only the unpriced one remains
        assert set(by_name) == {"llm7/NoMeta"}
        assert by_name["llm7/NoMeta"].context_length == 0
        assert by_name["llm7/NoMeta"].free is True

    def test_llm7_availability_telemetry_is_published_health(self, mp):
        lib, _ = mp
        payload = {
            "data": [
                {"id": "Healthy", "model_type": "chat", "schema_endpoints": ["openai"],
                 "availability_last_hour_percent": 100.0,
                 "availability": {"old": 100.0, "mid": 100.0, "recent": 100.0},
                 "pricing": {"input": 0, "output": 0}},
                {"id": "Flaky", "model_type": "chat", "schema_endpoints": ["openai"],
                 "availability_last_hour_percent": 83.33,
                 "availability": {"old": 95.0, "mid": 90.0, "recent": 85.0},
                 "pricing": {"input": 0, "output": 0}},
                {"id": "Untelemeted", "model_type": "chat", "schema_endpoints": ["openai"]},
                {"id": "Priced", "model_type": "chat", "schema_endpoints": ["openai"],
                 "availability_last_hour_percent": 100.0,
                 "pricing": {"input": 0.02, "output": 0.04}},
            ]
        }
        by_name = {c.name: c for c in lib.parse_llm7_models(payload)}
        assert "llm7/Priced" not in by_name  # free-only filter
        healthy = by_name["llm7/Healthy"]
        flaky = by_name["llm7/Flaky"]
        untelem = by_name["llm7/Untelemeted"]
        # telemetred models are metric-backed on the published health...
        assert healthy.metricless is False
        assert healthy.success_rate == 1.0
        assert healthy.requests > 0
        assert flaky.metricless is False
        assert 0.83 < flaky.success_rate < 0.90  # last-hour dominant blend
        # ...while untelemetred ones keep the metric-less favorite treatment
        assert untelem.metricless is True
        # flaky published health ranks below the healthy published health
        stats, cfg = lib.StatsRegistry(), lib.PickerConfig()
        ranked = lib.rank_candidates([flaky, healthy], lib.TIER_DEFAULT, stats, cfg)
        assert ranked[0].candidate.name == "llm7/Healthy"

    def test_llm7_free_only_filter(self, mp):
        """Free-only, like pollinations: metered models never become candidates,
        even when that leaves the pool empty (currently the case upstream)."""
        lib, _ = mp
        payload = {
            "data": [
                {"id": "Priced", "model_type": "chat", "schema_endpoints": ["openai"],
                 "pricing": {"input": 0.02, "output": 0.04, "currency": "USD"}},
                {"id": "Free", "model_type": "chat", "schema_endpoints": ["openai"],
                 "pricing": {"input": 0, "output": 0, "currency": "USD"}},
                {"id": "NoPrice", "model_type": "chat", "schema_endpoints": ["openai"]},
            ]
        }
        by_name = {c.name: c for c in lib.parse_llm7_models(payload)}
        assert set(by_name) == {"llm7/Free", "llm7/NoPrice"}
        assert all(c.free for c in by_name.values())

    def test_provider_failure_keeps_last_known_candidates(self, fresh, monkeypatch):
        """One provider's failed refresh must not sink the others' candidates."""
        lib, _, cfg, stats, manager = fresh
        good = [lib.ModelCandidate(name="nvidia_nim/z-ai/glm-5.3", provider="nvidia_nim", metricless=True)]

        async def good_fetch(url, key_env):
            if key_env != "NIM_API_KEY":
                return {"data": []}
            return {"data": [{"id": "z-ai/glm-5.3"}]}

        async def bad_fetch(cfg):
            raise RuntimeError("down")

        async def empty_modelgrep(url):
            return []

        monkeypatch.setattr("model_picker.fetch_modelgrep_catalog", empty_modelgrep)
        async def bad_raw(url, api_key):
            raise RuntimeError("pollinations down")

        monkeypatch.setattr("model_picker._fetch_json", bad_raw)
        monkeypatch.setattr("model_picker.fetch_provider_models", good_fetch)
        # first refresh: pollinations fails, NIM succeeds
        snap1 = asyncio.run(manager.get_snapshot())
        assert [c.name for c in snap1.candidates] == ["nvidia_nim/z-ai/glm-5.3"]
        # second refresh: NIM now fails too -> its last-known candidates persist
        cfg.ttl_seconds = 0.05
        time.sleep(0.06)
        monkeypatch.setattr("model_picker.fetch_provider_models", bad_fetch)
        snap2 = asyncio.run(manager.get_snapshot())
        assert [c.name for c in snap2.candidates] == ["nvidia_nim/z-ai/glm-5.3"]
        # per-provider stale-serve is transparent: the snapshot is freshly
        # built around each provider's last-known candidates
        assert snap2.stale is False


# ---------------------------------------------------------------------------
# Plugin behavior (env gate, tier routing, retries)
# ---------------------------------------------------------------------------


class TestPlugin:
    def test_env_gate_passes_through(self, fresh, monkeypatch):
        lib, test_plugin, cfg, stats, manager = fresh
        monkeypatch.setenv("MODEL_PICKER_ENABLED", "")
        context = make_context(lib, ["lite-llm/default"])
        result = asyncio.run(test_plugin.run(context))
        assert result.candidate_models == ["lite-llm/default"]

    @pytest.mark.parametrize("enabled_value", ["true", "1", "YES", "on"])
    def test_env_gate_truthy_values(self, fresh, monkeypatch, enabled_value):
        lib, test_plugin, cfg, stats, manager = fresh
        monkeypatch.setenv("MODEL_PICKER_ENABLED", enabled_value)
        assert lib.picker_enabled()

    def test_unknown_pool_passes_through(self, fresh, env_enabled):
        lib, test_plugin, cfg, stats, manager = fresh
        context = make_context(lib, ["lite-llm/webSearch"])
        result = asyncio.run(test_plugin.run(context))
        assert result.candidate_models == ["lite-llm/webSearch"]

    @staticmethod
    def _fake_snapshot(monkeypatch, lib, manager):
        async def fake_snapshot(ml=None):
            return snapshot_with(lib, free_plugin_pool(lib))

        monkeypatch.setattr(manager, "get_snapshot", fake_snapshot)

    def test_plugin_rewrites_default_tier(self, fresh, env_enabled, monkeypatch):
        lib, test_plugin, cfg, stats, manager = fresh
        self._fake_snapshot(monkeypatch, lib, manager)
        context = make_context(lib, ["lite-llm/default"], metadata={"existing": 1})
        result = asyncio.run(test_plugin.run(context))
        assert len(result.candidate_models) == 1
        assert result.candidate_models[0].startswith("pollinations/")
        # pick recorded in the shared metadata bucket for retry exclusion
        assert result.metadata["model_picker_picks"] == [result.candidate_models[0]]

    def test_plugin_rewrites_ultra_think_tier_by_context(self, fresh, env_enabled, monkeypatch):
        lib, test_plugin, cfg, stats, manager = fresh
        self._fake_snapshot(monkeypatch, lib, manager)
        context = make_context(lib, ["lite-llm/ultra-think"])
        result = asyncio.run(test_plugin.run(context))
        # the 1M-context catalog models outrank 400k gpt-5.4-nano in the ultra-think rubric
        assert result.candidate_models[0] in (
            "pollinations/openai/gpt-6-luna",
            "pollinations/z-ai/glm-5.3",
            "pollinations/deepseek/deepseek-v4-flash",
            "pollinations/community/vendouple/deepseek-v4-pro",
        )

    def test_tier_detection(self, mp):
        lib, plugin = mp
        assert plugin.detect_tier(["lite-llm/default"]) == lib.TIER_DEFAULT
        # COMPLEX (think) uses the default rubric; only REASONING
        # (ultra-think) keeps the capability-first rubric.
        assert plugin.detect_tier(["lite-llm/think"]) == lib.TIER_DEFAULT
        assert plugin.detect_tier(["lite-llm/ultra-think"]) == lib.TIER_THINK
        assert plugin.detect_tier(["lite-llm/webSearch"]) is None

    def test_plugin_think_pool_picks_default_rubric_winner(self, fresh, env_enabled, monkeypatch):
        lib, test_plugin, cfg, stats, manager = fresh
        strong = metric_candidate(lib, "pollinations/openai/healthy", 0.9997, 87885, ctx=400000)
        untried = favored_candidate(lib, "nvidia_nim/z-ai/glm-5.3", ctx=1048576)
        untried.benchmark_score, untried.benchmarked = 0.9, True

        async def fake_snapshot(ml=None):
            return snapshot_with(lib, [strong, untried])

        monkeypatch.setattr(manager, "get_snapshot", fake_snapshot)
        context = make_context(lib, ["lite-llm/think"])
        result = asyncio.run(test_plugin.run(context))
        # Default rubric: known-strong health first, regardless of the
        # untried model's larger context and higher benchmark. Under the
        # old capability-first think rubric the untried model would win.
        assert result.candidate_models == ["pollinations/openai/healthy"]

    def test_plugin_excludes_prior_picks_on_retry(self, fresh, env_enabled, monkeypatch):
        lib, test_plugin, cfg, stats, manager = fresh
        self._fake_snapshot(monkeypatch, lib, manager)
        # litellm_call_id is the shared channel across retry attempts (the
        # metadata dict itself is pydantic-copied per RoutingContext)
        metadata = {"litellm_call_id": "call-1"}
        first = make_context(lib, ["lite-llm/default"], metadata=metadata)
        asyncio.run(test_plugin.run(first))
        first_pick = first.candidate_models[0]
        second = make_context(lib, ["lite-llm/default"], metadata=metadata)
        asyncio.run(test_plugin.run(second))
        assert second.candidate_models[0] != first_pick
        # a different request (different call id) starts fresh at the top pick
        third = make_context(lib, ["lite-llm/default"], metadata={"litellm_call_id": "call-2"})
        asyncio.run(test_plugin.run(third))
        assert third.candidate_models[0] == first_pick

    def test_prior_pick_registry_bounds_and_expiry(self, mp):
        lib, _ = mp
        registry = lib.PriorPickRegistry(max_entries=2, ttl_seconds=10)
        now = 1000.0
        registry.add("a", "m1", now=now)
        registry.add("b", "m2", now=now + 1)
        registry.add("c", "m3", now=now + 2)  # evicts oldest ("a")
        assert registry.get("a", now=now + 3) == []
        assert registry.get("b", now=now + 3) == ["m2"]
        assert registry.get("c", now=now + 3) == ["m3"]
        # ttl expiry
        assert registry.get("c", now=now + 2 + 11) == []

    def test_plugin_never_breaks_routing(self, fresh, env_enabled, monkeypatch):
        lib, test_plugin, cfg, stats, manager = fresh

        def boom(ml=None):
            raise RuntimeError("catalog exploded")

        monkeypatch.setattr(manager, "get_snapshot", boom)
        context = make_context(lib, ["lite-llm/default"])
        result = asyncio.run(test_plugin.run(context))
        assert result.candidate_models == ["lite-llm/default"]

    def test_no_call_id_keys_registry_on_conversation(self, fresh, env_enabled, monkeypatch):
        """litellm does not surface litellm_call_id to routing plugins, so the
        pick history falls back to a conversation-derived key — which still
        excludes prior picks across the router's in-request retries."""
        lib, test_plugin, cfg, stats, manager = fresh
        registry = lib.PriorPickRegistry()
        test_plugin._prior_picks = registry
        self._fake_snapshot(monkeypatch, lib, manager)
        context = make_context(lib, ["lite-llm/default"], metadata={})
        first = asyncio.run(test_plugin.run(context))
        assert first.candidate_models and first.candidate_models[0].startswith("pollinations/")
        assert len(registry._by_call) == 1
        # the same conversation (the retry) is excluded from its prior pick
        second = asyncio.run(test_plugin.run(make_context(lib, ["lite-llm/default"], metadata={})))
        assert second.candidate_models[0] != first.candidate_models[0]


    def test_event_group_reconciles_wildcard_names(self, mp, fresh):
        """Wildcard-served picks record under pollinations/<id>, not the bare id."""
        lib, plugin = mp
        _, _, cfg, stats, manager = fresh
        catalog = lib.CatalogSnapshot(
            candidates=[
                metric_candidate(lib, "pollinations/community/x", 0.99, 100),
                favored_candidate(lib, "z-ai/glm-5.3", provider="nvidia_nim"),
                metric_candidate(lib, "pollinations/z-ai/glm-5.3", 0.99, 100),
            ]
        )
        manager._snapshot = catalog
        stats_logger = plugin.ModelPickerStatsLogger(stats=stats, manager=manager)
        # wildcard-served: bare catalog id gains the pollinations/ prefix
        assert stats_logger._event_group({"litellm_metadata": {"deployment_model_name": "community/x"}}) == (
            "pollinations/community/x"
        )
        # static group names match a candidate directly -> untouched, even when
        # a pollinations catalog model shares the suffix
        assert stats_logger._event_group({"litellm_metadata": {"deployment_model_name": "z-ai/glm-5.3"}}) == "z-ai/glm-5.3"
        # already-prefixed names pass through
        assert stats_logger._event_group({"litellm_metadata": {"deployment_model_name": "pollinations/community/x"}}) == (
            "pollinations/community/x"
        )
        # unknown names pass through untouched
        assert stats_logger._event_group({"litellm_metadata": {"deployment_model_name": "fast"}}) == "fast"

    def test_unmapped_model_info_fallback_uses_catalog_context(self, mp, fresh):
        """Discovered models absent from litellm's map get fallback info built
        from the catalog's published context window (or a conservative default)."""
        lib, plugin = mp
        _, _, cfg, stats, manager = fresh
        # warm snapshot with a known-context candidate and an unknown one
        manager._snapshot = lib.CatalogSnapshot(
            candidates=[
                lib.ModelCandidate(name="pollinations/openai/gpt-6-luna", provider="pollinations",
                                   context_length=1050000, metricless=False, success_rate=0.99, requests=100),
                lib.ModelCandidate(name="nvidia_nim/01-ai/yi-large", provider="nvidia_nim",
                                   context_length=0, metricless=True),
            ]
        )
        # known context: budget = context minus the output reserve
        known = plugin._unmapped_model_info_fallback(
            {"model_name": "pollinations/openai/gpt-6-luna", "model_info": None}, manager=manager
        )
        assert known["max_input_tokens"] == 1050000 - plugin._FALLBACK_MAX_OUTPUT_TOKENS
        assert known["litellm_provider"] == "pollinations"
        # unknown context: conservative default; user model_info wins over the default
        unknown = plugin._unmapped_model_info_fallback({"model_name": "nvidia_nim/01-ai/yi-large"}, manager=manager)
        assert unknown["max_input_tokens"] == plugin._FALLBACK_MAX_INPUT_TOKENS
        tuned = plugin._unmapped_model_info_fallback(
            {"model_name": "nvidia_nim/01-ai/yi-large", "model_info": {"max_input_tokens": 65536}}, manager=manager
        )
        assert tuned["max_input_tokens"] == 65536
        # cold manager / non-dict deployment: still a sane default
        cold = plugin._unmapped_model_info_fallback({"model_name": "nvidia_nim/whatever"})
        assert cold["max_input_tokens"] == plugin._FALLBACK_MAX_INPUT_TOKENS
        assert plugin._unmapped_model_info_fallback(None)["max_input_tokens"] == plugin._FALLBACK_MAX_INPUT_TOKENS

    def test_unmapped_model_info_patch_installed(self, mp):
        lib, plugin = mp
        from litellm.router import Router

        assert getattr(Router.get_router_model_info, "__name__", "") == "get_router_model_info"
        # the patch wraps the original behind a marker attribute
        assert getattr(Router.get_router_model_info, "_model_picker_patch", None) is not None

    def test_event_group_cold_manager_passes_through(self, mp, fresh):
        lib, plugin = mp
        _, _, cfg, stats, manager = fresh
        stats_logger = plugin.ModelPickerStatsLogger(stats=stats, manager=manager)
        assert manager.peek_candidate_names() is None
        assert stats_logger._event_group({"litellm_metadata": {"deployment_model_name": "community/x"}}) == "community/x"


# ---------------------------------------------------------------------------
# Catalog manager (TTL, stale-serve, fallback)
# ---------------------------------------------------------------------------


class TestCatalogManager:
    @staticmethod
    def _mock_other_providers(monkeypatch, fail=False):
        """Mock the NIM/Ollama/LLM7 and modelgrep fetches (empty or failing)."""

        async def empty_fetch(url, key_env):
            if fail:
                raise RuntimeError(f"{key_env} down")
            return {"data": []}

        monkeypatch.setattr("model_picker.fetch_provider_models", empty_fetch)

        async def empty_modelgrep(url):
            if fail:
                raise RuntimeError("modelgrep down")
            return []

        monkeypatch.setattr("model_picker.fetch_modelgrep_catalog", empty_modelgrep)

    def test_fresh_snapshot_reused_within_ttl(self, fresh, monkeypatch):
        lib, _, cfg, stats, manager = fresh
        calls = {"n": 0}

        async def fake_fetch(cfg):
            calls["n"] += 1
            return candidates_from_fixture(lib)

        async def fake_raw_fetch(url, api_key):
            calls["n"] += 1
            return json.loads((FIXTURES / "pollinations_models.json").read_text())

        monkeypatch.setattr("model_picker._fetch_json", fake_raw_fetch)
        self._mock_other_providers(monkeypatch)
        snap1 = asyncio.run(manager.get_snapshot())
        snap2 = asyncio.run(manager.get_snapshot())
        assert calls["n"] == 1
        assert snap1 is snap2

    def test_stale_served_on_refresh_failure(self, fresh, monkeypatch):
        lib, _, cfg, stats, manager = fresh
        cfg.ttl_seconds = 0.05

        async def good_fetch(cfg):
            return candidates_from_fixture(lib)

        async def bad_fetch(cfg):
            raise RuntimeError("pollinations down")

        async def good_raw(url, api_key):
            return {
                "data": [
                    {
                        "id": "openai/gpt-6-luna",
                        "input_modalities": ["text"],
                        "output_modalities": ["text"],
                        "supported_endpoints": ["/v1/chat/completions"],
                        "health": {"status": "healthy", "success_rate": 99.97, "requests": 87885},
                        "pricing": {"currency": "pollen"},
                    }
                ]
            }

        monkeypatch.setattr("model_picker._fetch_json", good_raw)
        self._mock_other_providers(monkeypatch)
        snap1 = asyncio.run(manager.get_snapshot())
        time.sleep(0.06)
        async def bad_raw(url, api_key):
            raise RuntimeError("pollinations down")

        monkeypatch.setattr("model_picker._fetch_json", bad_raw)
        snap2 = asyncio.run(manager.get_snapshot())
        # pollinations failed -> its last-known candidates serve transparently
        # in a fresh snapshot (stale marks whole-refresh failures only)
        assert snap2.stale is False
        assert snap2.candidates == snap1.candidates

    def test_fallback_snapshot_when_cold_and_down(self, fresh, monkeypatch):
        lib, _, cfg, stats, manager = fresh

        async def bad_fetch(cfg):
            raise RuntimeError("down")

        async def bad_raw(url, api_key):
            raise RuntimeError("pollinations down")

        monkeypatch.setattr("model_picker._fetch_json", bad_raw)
        self._mock_other_providers(monkeypatch)
        snap = asyncio.run(manager.get_snapshot())
        assert snap.stale is True
        names = {c.name for c in snap.candidates}
        assert f"pollinations/{cfg.fallback_model}" in names


# ---------------------------------------------------------------------------
# Config drift (default frozen; picker deltas)
# ---------------------------------------------------------------------------


class TestConfigDeltas:
    @staticmethod
    def _configs():
        default = yaml.safe_load((LITE_LLM_DIR / "lite-llm-default.yaml").read_text())
        picker = yaml.safe_load((LITE_LLM_DIR / "lite-llm-picker.yaml").read_text())
        return default, picker

    @staticmethod
    def _group_names(cfg):
        return [m["model_name"] for m in cfg["model_list"]]

    def test_default_config_has_no_picker_artifacts(self):
        default, _ = self._configs()
        assert "pollinations/*" not in self._group_names(default)
        for m in default["model_list"]:
            crc = (m.get("litellm_params") or {}).get("complexity_router_config") or {}
            assert "plugins" not in crc
        callbacks = default["litellm_settings"]["callbacks"]
        assert not any("model_picker" in c for c in callbacks)

    def test_picker_config_wildcard_and_plugin(self):
        _, picker = self._configs()
        assert "pollinations/*" in self._group_names(picker)
        wildcard = next(m for m in picker["model_list"] if m["model_name"] == "pollinations/*")
        assert wildcard["litellm_params"]["model"] == "openai/*"
        assert wildcard["litellm_params"]["api_base"] == "https://gen.pollinations.ai/v1"
        assert wildcard["model_info"]["allowed_fails"] >= 1000000
        crc = next(
            m["litellm_params"]["complexity_router_config"]
            for m in picker["model_list"]
            if m["model_name"] == "lite-llm/complexity"
        )
        assert crc["plugins"] == ["model_picker_plugin.picker"]

    def test_picker_config_fallback_net_for_nonretryable_errors(self):
        """Picker tiers carry a last-resort fallback net — not the primary
        path (retries + the picker walk are), but the only path for
        non-retryable errors: a context_length 400 is not retried by
        LiteLLM, never maps to ContextWindowExceededError when the
        provider message is a bare "Invalid request", and with no fallback
        entry surfaced to the client, which treats 400 as terminal (unlike
        408s, which it retries). The 2026-10-25 session died exactly this
        way. Lookup groups for a complexity-routed request start with the
        tier, so the net is keyed by tier (plus complexity itself); targets
        are concrete models because fallback attempts bypass the picker
        plugin and the tier groups' own deployments are placeholders."""
        default, picker = self._configs()
        picker_fb = {list(f)[0]: list(f.values())[0] for f in picker["router_settings"]["fallbacks"]}
        assert {"lite-llm/webSearch", "lite-llm/image"} <= set(picker_fb)
        net_groups = {"lite-llm/think", "lite-llm/ultra-think", "lite-llm/default", "lite-llm/complexity"}
        assert net_groups <= set(picker_fb)
        expected_chain = ["nvidia_nim/z-ai/glm-5.3", "nvidia_nim/stepfun-ai/step-5-preview"]
        for group in net_groups:
            assert picker_fb[group] == expected_chain
        # the default config still carries complexity-path fallbacks (the
        # beads side of this merge kept them); the picker net above is the
        # last-resort replacement for the picker tiers, not a copy of them.
        default_fb = {list(f)[0] for f in default["router_settings"]["fallbacks"]}
        assert net_groups <= default_fb
        # every picker fallback target resolves through a wildcard or a kept group
        wildcard_prefixes = ("nvidia_nim/", "llm7/", "pollinations/", "gemini-")
        for entry in picker["router_settings"]["fallbacks"]:
            for target in entry[list(entry)[0]]:
                assert target.startswith(wildcard_prefixes), target
        # the old static tier-group targets must not reappear as fallbacks:
        # the union of the pre-merge list and the current default config's
        # static targets (brought in by the beads side of this merge).
        removed_statics = {"minimax-m2.7", "z-ai/glm-5.3-flash", "nemotron-3-super:cloud",
                           "nemotron-3-ultra:cloud", "nvidia/nemotron-3-ultra-550b-a55b", "z-ai/glm-5.3",
                           "default", "fast", "nvidia/nemotron-3.5-lightning-30b-a3b",
                           "minimaxai/minimax-m3.1-flash"}
        for entry in picker["router_settings"]["fallbacks"]:
            assert not (set(entry[list(entry)[0]]) & removed_statics)

    def test_picker_config_retry_settings(self):
        default, picker = self._configs()
        # the hard-failure walk budget: each retry re-enters the picker, which
        # excludes the failed candidate
        assert picker["router_settings"]["num_retries"] == 64
        assert "retry_policy" not in picker["router_settings"]
        assert default["router_settings"]["retry_policy"]["TimeoutErrorRetries"] == 0

    def test_picker_config_parity_with_default(self):
        """Everything outside the documented deltas is identical.

        Picker-mode deltas: the provider wildcards replace the hand-maintained
        static provider groups (the picker discovers those catalogs live)."""
        default, picker = self._configs()
        added_wildcards = {"pollinations/*", "nvidia_nim/*", "llm7/*"}
        removed_statics = {
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "minimaxai/minimax-m3.1-flash",
            "nvidia/nemotron-3-ultra-550b-a55b",
            "z-ai/glm-5.3",
            "z-ai/glm-5.3-flash",
        }
        picker_groups = set(self._group_names(picker))
        assert added_wildcards <= picker_groups
        assert not (removed_statics & picker_groups)
        assert [g for g in self._group_names(default) if g not in removed_statics] == [
            g for g in self._group_names(picker) if g not in added_wildcards
        ]
        for key in ("search_tools",):
            assert default[key] == picker[key]
        for key in ("use_chat_completions_url_for_anthropic_messages", "modify_params", "drop_params"):
            assert default["litellm_settings"][key] == picker["litellm_settings"][key]
        assert (
            default["litellm_settings"]["websearch_interception_params"]
            == picker["litellm_settings"]["websearch_interception_params"]
        )
        # static group entries are byte-identical (modulo the added wildcard)
        def entries(cfg):
            return {m["model_name"]: m for m in cfg["model_list"]}

        d, p = entries(default), entries(picker)
        for name, entry in d.items():
            if name in removed_statics:
                assert name not in p  # replaced by the provider wildcards
                continue
            expected = entry
            if name == "lite-llm/complexity":
                # documented delta: the picker plugin is added to the complexity config
                import copy

                expected = copy.deepcopy(entry)
                expected["litellm_params"]["complexity_router_config"]["plugins"] = ["model_picker_plugin.picker"]
            assert p[name] == expected, f"static entry drifted: {name}"
        # router settings beyond the documented deltas
        assert default["router_settings"]["allowed_fails"] == picker["router_settings"]["allowed_fails"]


# ---------------------------------------------------------------------------
# Persistent attribution + default-tier known-strong ranking
# (model-picker-persistent-attribution-default-health)
# ---------------------------------------------------------------------------


class TestPersistentAttributionAndDefaultHealth:
    def test_default_favors_known_strong_then_untried_then_known_weak(self, mp):
        """Default tier: demonstrated health > untried > known-weak.

        Previously the untried (FAVORED) block ranked first, so an
        unmeasured NIM model beat a published-healthy pollinations model
        on every request — the log's GLM-5.3 loop.
        """
        lib, _plugin = mp
        cfg = lib.PickerConfig()
        stats = lib.StatsRegistry()
        untried = favored_candidate(lib, "nvidia_nim/z-ai/glm-5.3", ctx=100000)
        untried.benchmark_score = 0.66
        strong = metric_candidate(lib, "pollinations/openai/healthy", 0.9997, 87885, ctx=100000)
        weak = metric_candidate(lib, "pollinations/openai/weak", 0.20, 1000, ctx=100000)
        ranked = lib.rank_candidates(
            [untried, strong, weak], lib.TIER_DEFAULT, stats, cfg, now=time.time()
        )
        assert [r.candidate.name for r in ranked] == [
            "pollinations/openai/healthy",
            "nvidia_nim/z-ai/glm-5.3",
            "pollinations/openai/weak",
        ]

    def test_ultra_think_benchmark_then_known_health(self, mp):
        """Ultra-think: context, then benchmark, then health blocks.

        On equal context and equal benchmark, a model known to have good
        health beats an unmeasured one (equally capable, so evidence
        decides); a higher-benchmark unmeasured model still wins over a
        lower-benchmark known-strong one; and an unmeasured model still
        beats a known-weak one. Once the untried model has observations
        it competes on tracked health, not on being new.
        """
        lib, _plugin = mp
        cfg = lib.PickerConfig()
        stats = lib.StatsRegistry()
        untried = favored_candidate(lib, "nvidia_nim/z-ai/glm-5.3", ctx=100000)
        strong = metric_candidate(lib, "pollinations/openai/healthy", 0.9997, 87885, ctx=100000)
        weak = metric_candidate(lib, "pollinations/openai/weak", 0.20, 1000, ctx=100000)
        # Higher benchmark wins even though the other model is known-strong.
        untried.benchmark_score = 0.9
        strong.benchmark_score = 0.5
        ranked = lib.rank_candidates(
            [untried, strong], lib.TIER_THINK, stats, cfg, now=time.time()
        )
        assert ranked[0].candidate.name == "nvidia_nim/z-ai/glm-5.3"
        # Equal benchmark: known-strong health beats unmeasured.
        untried.benchmark_score = 0.5
        ranked = lib.rank_candidates(
            [untried, strong], lib.TIER_THINK, stats, cfg, now=time.time()
        )
        assert ranked[0].candidate.name == "pollinations/openai/healthy"
        # Equal benchmark: unmeasured still beats known-weak.
        ranked = lib.rank_candidates(
            [untried, weak], lib.TIER_THINK, stats, cfg, now=time.time()
        )
        assert ranked[0].candidate.name == "nvidia_nim/z-ai/glm-5.3"
        # Three successes: tracked health is high (0.8, strong block), but
        # the model now competes on evidence — the 0.999-healthy model
        # wins on equal benchmark.
        now = time.time()
        for _ in range(3):
            stats.record_success("nvidia_nim/z-ai/glm-5.3", 1.0, now=now)
        ranked = lib.rank_candidates(
            [untried, strong], lib.TIER_THINK, stats, cfg, now=now
        )
        assert ranked[0].candidate.name == "pollinations/openai/healthy"

    def test_failed_nim_model_no_longer_repicked_first_on_next_turn(self, mp):
        """The log scenario: GLM-5.3 times out three times, the next turn
        (fresh attempt_excluded) must not put it first in default."""
        lib, _plugin = mp
        cfg = lib.PickerConfig()
        stats = lib.StatsRegistry()
        now = time.time()
        for _ in range(3):
            stats.record_failure("nvidia_nim/z-ai/glm-5.3", lib.FAILURE_CLASS_TIMEOUT, now=now)
        untried = favored_candidate(lib, "nvidia_nim/z-ai/glm-5.3", ctx=100000)
        strong = metric_candidate(lib, "pollinations/openai/healthy", 0.9997, 87885, ctx=100000)
        # Past the 60s recency window, so this is the demotion, not the guard.
        ranked = lib.rank_candidates(
            [untried, strong], lib.TIER_DEFAULT, stats, cfg, now=now + 120
        )
        assert ranked[0].candidate.name == "pollinations/openai/healthy"
        assert ranked[-1].candidate.name == "nvidia_nim/z-ai/glm-5.3"

    def test_stats_survive_registry_restart(self, mp, tmp_path):
        """StatsRegistry with a path reloads its events in a new instance —
        a LiteLLM restart must not reset a model to untried."""
        lib, _plugin = mp
        path = str(tmp_path / "stats.json")
        first = lib.StatsRegistry(path=path)
        now = time.time()
        first.record_failure("nvidia_nim/z-ai/glm-5.3", lib.FAILURE_CLASS_TIMEOUT, now=now)
        first.record_success("pollinations/openai/healthy", 1.2, now=now)
        second = lib.StatsRegistry(path=path)
        assert second.derived("nvidia_nim/z-ai/glm-5.3", now=now).n_obs == 1
        assert second.derived("nvidia_nim/z-ai/glm-5.3", now=now).last_obs_was_failure
        assert second.derived("pollinations/openai/healthy", now=now).n_obs == 1
        # Corrupt file: fail-soft to empty stats, never raise.
        (tmp_path / "stats.json").write_text("{not json")
        third = lib.StatsRegistry(path=path)
        assert third.derived("nvidia_nim/z-ai/glm-5.3", now=now).n_obs == 0

    def test_event_group_ambiguous_bare_id_is_not_guessed(self, mp, fresh):
        """A bare id present under two providers must not be credited to
        pollinations, and a wildcard name must not be recorded at all."""
        lib, plugin = mp
        _lib, _test_plugin, _cfg, stats, manager = fresh
        manager._snapshot = lib.CatalogSnapshot(
            candidates=[
                metric_candidate(lib, "pollinations/z-ai/glm-5.3", 0.99, 100),
                favored_candidate(lib, "nvidia_nim/z-ai/glm-5.3", ctx=100000),
            ]
        )
        logger = plugin.ModelPickerStatsLogger(stats=stats, manager=manager)
        assert logger._event_group({"litellm_metadata": {"deployment_model_name": "z-ai/glm-5.3"}}) == ""
        assert logger._event_group({"litellm_metadata": {"deployment_model_name": "nvidia_nim/*"}}) == ""
        assert (
            logger._event_group({"litellm_metadata": {"deployment_model_name": "nvidia_nim/z-ai/glm-5.3"}})
            == "nvidia_nim/z-ai/glm-5.3"
        )

    def test_failed_group_uses_resolved_model_not_wildcard(self, mp, fresh):
        """Streaming-hook attribution: the resolved model from the stream's
        call details wins over the wildcard deployment name."""
        lib, plugin = mp
        _lib, _test_plugin, _cfg, stats, manager = fresh
        manager._snapshot = lib.CatalogSnapshot(
            candidates=[favored_candidate(lib, "nvidia_nim/z-ai/glm-5.3", ctx=100000)]
        )
        logger = plugin.ModelPickerStatsLogger(stats=stats, manager=manager)
        response = types.SimpleNamespace(
            logging_obj=types.SimpleNamespace(
                model_call_details={"model": "nvidia_nim/z-ai/glm-5.3"}
            )
        )
        request_data = {
            "model": "lite-llm/complexity",
            "messages": [{"role": "user", "content": "hi"}],
            "litellm_metadata": {"model_group": "nvidia_nim/*"},
        }
        assert logger._failed_group(request_data, response) == "nvidia_nim/z-ai/glm-5.3"


# ---------------------------------------------------------------------------
# Free-only selection
# ---------------------------------------------------------------------------


class TestFreeOnlySelection:
    def test_nim_models_are_free(self, mp):
        lib, _ = mp
        payload = {"data": [{"id": "z-ai/glm-5.3"}, {"id": "nvidia/embed-qa-4"}]}
        parsed = {c.name: c for c in lib.parse_nim_models(payload)}
        # chat model admitted and free; embedding family still filtered out
        assert parsed["nvidia_nim/z-ai/glm-5.3"].free is True
        assert "nvidia_nim/nvidia/embed-qa-4" not in parsed

    def test_rank_candidates_never_picks_a_paid_model(self, mp):
        lib, _ = mp
        cfg = lib.PickerConfig()
        stats = lib.StatsRegistry()
        paid = lib.ModelCandidate(
            name="pollinations/openai/paid",
            provider="pollinations",
            context_length=1000000,
            metricless=False,
            success_rate=1.0,
            requests=100000,
            free=False,
        )
        free = favored_candidate(lib, "nvidia_nim/z-ai/glm-5.3", ctx=100000)
        ranked = lib.rank_candidates([paid, free], lib.TIER_THINK, stats, cfg, now=time.time())
        assert [r.candidate.name for r in ranked] == ["nvidia_nim/z-ai/glm-5.3"]
        # a pool of only paid models ranks to nothing, never to the paid model
        assert lib.rank_candidates([paid], lib.TIER_DEFAULT, stats, cfg, now=time.time()) == []


class TestContextOverflow:
    """The 2026-10-25 session that died on a 400: minimax-m3.1-flash
    served ~70 turns, then the request's real size (265,267 tokens)
    exceeded its real window (262,144) while the picker believed the
    estimate was 7,329 and the window was 1,048,576. Both measurements
    were wrong in the direction that hides an overflow."""

    def test_estimate_counts_nested_tool_result_text(self, mp):
        lib, _ = mp
        # Anthropic-shaped messages: the bulk of a coding session lives
        # inside tool_result content blocks, nested one level deeper than
        # top-level text parts.
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "x" * 1000}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "t1",
                        "content": [{"type": "text", "text": "y" * 4000}],
                    }
                ],
            },
            # Image payloads are not prompt text and must not inflate it.
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "data": "z" * 10000},
                    }
                ],
            },
        ]
        assert lib.estimate_tokens(messages) == (1000 + 4000) // 4

    def test_estimate_counts_openai_string_content(self, mp):
        lib, _ = mp
        messages = [
            {"role": "system", "content": "s" * 400},
            {"role": "tool", "content": "t" * 1200},
        ]
        assert lib.estimate_tokens(messages) == (400 + 1200) // 4

    def test_extract_context_limit_from_provider_body(self, mp):
        lib, _ = mp

        class FakeBadRequest(Exception):
            def __init__(self):
                super().__init__("Invalid request")
                self.body = {
                    "message": "Invalid request",
                    "type": "Bad Request",
                    "code": 400,
                    "details": {"type": "context_length", "limit": 262144, "actual": 265267},
                }

        assert lib.extract_context_limit(FakeBadRequest()) == 262144
        # Unrelated errors carry no limit, even with a body.
        assert lib.extract_context_limit(ValueError("boom")) is None

        class Chained(Exception):
            pass

        chained = Chained("outer")
        chained.__cause__ = RuntimeError("context_length limit: 131072 exceeded")
        assert lib.extract_context_limit(chained) == 131072

    def test_learned_window_overrides_catalog_in_fit(self, mp):
        lib, _ = mp
        cfg = lib.PickerConfig()
        stats = lib.StatsRegistry()
        minimax = favored_candidate(lib, "nvidia_nim/minimaxai/minimax-m3.1-flash", ctx=1048576)
        other = favored_candidate(lib, "nvidia_nim/z-ai/glm-5.3", ctx=1048576)
        # Before learning, a 300k-token request fits both (catalog 1M).
        ranked = lib.rank_candidates(
            [minimax, other], lib.TIER_THINK, stats, cfg, estimate=300000, now=time.time()
        )
        assert len(ranked) == 2
        # After one context_length 400 proves minimax's real window, the
        # same request must not pick it — even though the catalog still
        # claims 1,048,576.
        stats.record_context_limit("nvidia_nim/minimaxai/minimax-m3.1-flash", 262144)
        ranked = lib.rank_candidates(
            [minimax, other], lib.TIER_THINK, stats, cfg, estimate=300000, now=time.time()
        )
        assert [r.candidate.name for r in ranked] == ["nvidia_nim/z-ai/glm-5.3"]
        # A smaller request still fits the learned window: the model is
        # not bricked, it is just excluded for oversized requests.
        ranked = lib.rank_candidates(
            [minimax, other], lib.TIER_THINK, stats, cfg, estimate=200000, now=time.time()
        )
        assert len(ranked) == 2

    def test_fit_empty_keeps_all_instead_of_passing_through(self, mp):
        lib, _ = mp
        cfg = lib.PickerConfig()
        stats = lib.StatsRegistry()
        minimax = favored_candidate(lib, "nvidia_nim/minimaxai/minimax-m3.1-flash", ctx=1048576)
        stats.record_context_limit("nvidia_nim/minimaxai/minimax-m3.1-flash", 262144)
        # Nothing fits a 2M-token request; ranking must still return the
        # candidate (best effort) rather than [] (which makes the plugin
        # pass the tier pool through to the router's arbitrary selection).
        ranked = lib.rank_candidates(
            [minimax], lib.TIER_THINK, stats, cfg, estimate=2000000, now=time.time()
        )
        assert [r.candidate.name for r in ranked] == ["nvidia_nim/minimaxai/minimax-m3.1-flash"]

    def test_learned_window_survives_registry_restart(self, mp, tmp_path):
        lib, _ = mp
        path = str(tmp_path / "stats.json")
        first = lib.StatsRegistry(path=path)
        first.record_context_limit("nvidia_nim/minimaxai/minimax-m3.1-flash", 262144)
        second = lib.StatsRegistry(path=path)
        assert second.learned_window("nvidia_nim/minimaxai/minimax-m3.1-flash") == 262144
        # A later, smaller proven limit wins; a larger one never widens it.
        second.record_context_limit("nvidia_nim/minimaxai/minimax-m3.1-flash", 300000)
        assert second.learned_window("nvidia_nim/minimaxai/minimax-m3.1-flash") == 262144

    def test_failure_event_learns_context_window(self, mp, fresh):
        """The plugin's failure hook records the proven limit from the
        mapped BadRequestError's provider body."""
        lib, plugin = mp
        _lib, _test_plugin, _cfg, stats, manager = fresh
        logger = plugin.ModelPickerStatsLogger(stats=stats, manager=manager)
        manager._snapshot = lib.CatalogSnapshot(
            candidates=[favored_candidate(lib, "nvidia_nim/minimaxai/minimax-m3.1-flash", ctx=1048576)]
        )

        class FakeBadRequest(Exception):
            def __init__(self):
                super().__init__("Invalid request")
                self.body = {
                    "details": {"type": "context_length", "limit": 262144, "actual": 265267}
                }

        import asyncio

        asyncio.run(
            logger.async_log_failure_event(
                {"litellm_metadata": {"model_group": "nvidia_nim/minimaxai/minimax-m3.1-flash"},
                 "exception": FakeBadRequest()},
                None,
                None,
                None,
            )
        )
        assert stats.learned_window("nvidia_nim/minimaxai/minimax-m3.1-flash") == 262144
