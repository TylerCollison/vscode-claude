"""Unit tests for the LiteLLM opencode_headers callback.

Covers the header-injection contract of lite-llm/opencode_headers.py: the
full OpenCode identity header set is stamped onto chat-path requests,
caller-supplied extra_headers survive (merge, not replace), env vars
override the identity values, non-chat call types pass through untouched,
and OPENCODE_HEADERS_MODEL_PREFIXES scopes injection to matching model
groups.

Run with: python3 -m pytest tests/test_opencode_headers.py
"""

import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))

# Make opencode_headers importable (the proxy runs with cwd=/lite-llm).
sys.path.insert(0, os.path.join(HERE, "..", "lite-llm"))

import opencode_headers as oh  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Keep host env from leaking into the assertions."""
    for var in (
        "OPENCODE_SESSION_ID",
        "OPENCODE_USER_ID",
        "OPENCODE_PROJECT_ID",
        "OPENCODE_CLIENT",
        "OPENCODE_USER_AGENT",
        "OPENCODE_HEADERS_MODEL_PREFIXES",
    ):
        monkeypatch.delenv(var, raising=False)


def call_hook(data, call_type="completion", user_api_key_dict=None):
    return asyncio.run(
        oh.opencode_headers_handler.async_pre_call_hook(
            user_api_key_dict=user_api_key_dict,
            cache=None,
            data=data,
            call_type=call_type,
        )
    )


def test_injects_all_five_headers():
    data = {"model": "lite-llm/router", "messages": []}
    result = call_hook(data)

    headers = result["extra_headers"]
    assert headers["x-opencode-session"] == oh._PROCESS_SESSION_ID
    assert headers["x-opencode-client"] == "cli"
    assert headers["x-opencode-project"] == os.uname().nodename
    assert headers["User-Agent"] == "opencode/1.18.35"
    # No virtual-key user ID -> a per-call UUID
    assert len(headers["x-opencode-request"]) == 36
    assert headers["x-opencode-request"] != headers["x-opencode-session"]


def test_merges_with_existing_extra_headers():
    data = {
        "model": "lite-llm/router",
        "messages": [],
        "extra_headers": {"X-Custom": "keep-me", "User-Agent": "caller/1.0"},
    }
    result = call_hook(data)

    headers = result["extra_headers"]
    assert headers["X-Custom"] == "keep-me"
    # Callback values win on collision
    assert headers["User-Agent"] == "opencode/1.18.35"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("OPENCODE_SESSION_ID", "sess-1")
    monkeypatch.setenv("OPENCODE_PROJECT_ID", "proj-1")
    monkeypatch.setenv("OPENCODE_CLIENT", "vscode")
    monkeypatch.setenv("OPENCODE_USER_AGENT", "opencode/9.9.9")

    headers = call_hook({"model": "m", "messages": []})["extra_headers"]

    assert headers["x-opencode-session"] == "sess-1"
    assert headers["x-opencode-project"] == "proj-1"
    assert headers["x-opencode-client"] == "vscode"
    assert headers["User-Agent"] == "opencode/9.9.9"


def test_request_id_from_virtual_key_user():
    user = SimpleNamespace(user_id="user-123")
    headers = call_hook({"model": "m", "messages": []}, user_api_key_dict=user)["extra_headers"]
    assert headers["x-opencode-request"] == "user-123"


def test_request_id_rotates_per_call_without_user():
    first = call_hook({"model": "m", "messages": []})["extra_headers"]["x-opencode-request"]
    second = call_hook({"model": "m", "messages": []})["extra_headers"]["x-opencode-request"]
    assert first != second


def test_session_id_stable_across_calls():
    first = call_hook({"model": "m", "messages": []})["extra_headers"]["x-opencode-session"]
    second = call_hook({"model": "m", "messages": []})["extra_headers"]["x-opencode-session"]
    assert first == second


def test_non_chat_call_types_untouched():
    for call_type in ("embeddings", "image_generation", "moderation", "audio_transcription"):
        data = {"model": "m", "messages": []}
        result = call_hook(data, call_type=call_type)
        assert "extra_headers" not in result


def test_chat_call_types_inject():
    # The proxy delivers "acompletion" for /chat/completions and
    # "anthropic_messages" for /v1/messages (verified against 1.102.1);
    # "completion" is the sync spelling.
    for call_type in ("completion", "acompletion", "anthropic_messages"):
        headers = call_hook({"model": "m", "messages": []}, call_type=call_type)["extra_headers"]
        assert headers["x-opencode-client"] == "cli"


def test_model_prefix_scoping(monkeypatch):
    monkeypatch.setenv("OPENCODE_HEADERS_MODEL_PREFIXES", "zen-, opencode/")

    in_scope = call_hook({"model": "zen-nemotron", "messages": []})
    assert "User-Agent" in in_scope["extra_headers"]

    out_of_scope = call_hook({"model": "gemini/gemini-3.5-flash-lite", "messages": []})
    assert "extra_headers" not in out_of_scope


def test_empty_prefix_list_applies_to_all(monkeypatch):
    monkeypatch.setenv("OPENCODE_HEADERS_MODEL_PREFIXES", "")
    headers = call_hook({"model": "anything/at/all", "messages": []})["extra_headers"]
    assert headers["User-Agent"] == "opencode/1.18.35"
