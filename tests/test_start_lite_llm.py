"""Tests for start-lite-llm.sh config resolution (beads workspace-yvy).

The script picks which LiteLLM config the proxy loads. A user-supplied
config (LITELLM_CONFIG_PATH, e.g. a mounted file) must win over the baked-in
defaults, and a bad path must fall back with a warning rather than taking the
proxy down. The litellm binary is stubbed so these run without the proxy
installed, and LITE_LLM_DIR is pointed at a temp dir so nothing outside the
repo is touched.
"""

import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
START_LITE_LLM_SH = REPO_ROOT / "start-lite-llm.sh"


def _seed_config_dir(tmp_path):
    """A temp stand-in for /lite-llm holding the two baked-in configs."""
    lite_llm_dir = tmp_path / "lite-llm"
    lite_llm_dir.mkdir()
    (lite_llm_dir / "lite-llm-default.yaml").write_text("default config\n")
    (lite_llm_dir / "lite-llm-picker.yaml").write_text("picker config\n")
    return lite_llm_dir


@pytest.fixture
def stub_litellm(tmp_path):
    """Put a stub 'litellm' on PATH that records its argv and cwd, then exits."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "litellm"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$@" > "$RECORD_ARGS_FILE"\n'
        'pwd >> "$RECORD_ARGS_FILE"\n'
        'touch "$RECORD_ARGS_FILE.done"\n'
    )
    stub.chmod(0o755)
    return bindir


def _run_script(tmp_path, stub_litellm, **env):
    """Run the startup script; return (proc, config path, proxy working dir)."""
    lite_llm_dir = _seed_config_dir(tmp_path)
    args_file = tmp_path / "args.txt"
    result = subprocess.run(
        ["bash", str(START_LITE_LLM_SH)],
        env={
            "PATH": f"{stub_litellm}:/usr/bin:/bin",
            "LITE_LLM_DIR": str(lite_llm_dir),
            "RECORD_ARGS_FILE": str(args_file),
            **env,
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    # litellm is backgrounded by the script, so the stub's output may land
    # slightly after the script itself exits.
    used = cwd = None
    done_file = args_file.with_suffix(args_file.suffix + ".done")
    for _ in range(50):
        if done_file.exists():
            lines = [line for line in args_file.read_text().splitlines() if line]
            used = lines[lines.index("--config") + 1] if "--config" in lines else None
            cwd = lines[-1]  # the stub's trailing `pwd`
            break
        time.sleep(0.05)
    return result, used, cwd


def test_uses_default_config_by_default(tmp_path, stub_litellm):
    result, used, cwd = _run_script(tmp_path, stub_litellm)
    assert result.returncode == 0, result.stderr
    assert used == str(tmp_path / "lite-llm" / "lite-llm-default.yaml")
    assert cwd == str(tmp_path / "lite-llm")


def test_model_picker_mode_selects_picker_config(tmp_path, stub_litellm):
    result, used, _ = _run_script(tmp_path, stub_litellm, MODEL_PICKER_ENABLED="true")
    assert result.returncode == 0, result.stderr
    assert used == str(tmp_path / "lite-llm" / "lite-llm-picker.yaml")


def test_mounted_config_path_wins_over_default(tmp_path, stub_litellm):
    """A mounted file overrides the baked-in default config."""
    mounted = tmp_path / "mounted-litellm.yaml"
    mounted.write_text("user config\n")
    result, used, cwd = _run_script(
        tmp_path, stub_litellm, LITELLM_CONFIG_PATH=str(mounted)
    )
    assert result.returncode == 0, result.stderr
    assert used == str(mounted)


def test_config_path_wins_over_picker_mode(tmp_path, stub_litellm):
    """The override also wins in picker mode - one escape hatch for both modes."""
    mounted_folder = tmp_path / "config-dir"
    mounted_folder.mkdir()
    mounted = mounted_folder / "custom.yaml"
    mounted.write_text("user config\n")
    result, used, _ = _run_script(
        tmp_path, stub_litellm, MODEL_PICKER_ENABLED="true", LITELLM_CONFIG_PATH=str(mounted)
    )
    assert result.returncode == 0, result.stderr
    assert used == str(mounted)


def test_proxy_keeps_working_dir_so_callbacks_resolve(tmp_path, stub_litellm):
    """The proxy must still run from the config dir even with a mounted config.

    The built-in configs reference callback modules by name
    (router_callback, websearch_interception, model_picker_plugin); if the
    working directory followed the mounted config instead, those imports
    would break and the proxy would fail to start.
    """
    mounted = tmp_path / "somewhere-else" / "my-litellm.yaml"
    mounted.parent.mkdir()
    mounted.write_text("user config\n")
    result, used, cwd = _run_script(
        tmp_path, stub_litellm, LITELLM_CONFIG_PATH=str(mounted)
    )
    assert result.returncode == 0, result.stderr
    assert used == str(mounted)
    assert cwd == str(tmp_path / "lite-llm")


def test_missing_config_path_falls_back_with_warning(tmp_path, stub_litellm):
    """A bad LITELLM_CONFIG_PATH warns and uses the default, not a broken proxy."""
    missing = tmp_path / "nope.yaml"
    result, used, _ = _run_script(
        tmp_path, stub_litellm, LITELLM_CONFIG_PATH=str(missing)
    )
    assert result.returncode == 0, result.stderr
    assert "LITELLM_CONFIG_PATH" in result.stderr
    assert "not a file" in result.stderr
    assert used == str(tmp_path / "lite-llm" / "lite-llm-default.yaml")
