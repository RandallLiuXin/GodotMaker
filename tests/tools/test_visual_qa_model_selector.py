"""Tests for visual_qa.py model selector parsing."""
import importlib.util
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "core"
    / "visual-qa"
    / "scripts"
    / "visual_qa.py"
)


def _load_visual_qa():
    spec = importlib.util.spec_from_file_location("visual_qa", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_selector_accepts_provider_prefixed_values():
    visual_qa = _load_visual_qa()

    assert visual_qa._split_model_selector("gemini:gemini-2.5-flash") == (
        "gemini",
        "gemini-2.5-flash",
    )
    assert visual_qa._split_model_selector("openai:gpt-5.5") == (
        "openai",
        "gpt-5.5",
    )


def test_model_selector_keeps_legacy_bare_gemini_model():
    visual_qa = _load_visual_qa()

    assert visual_qa._split_model_selector("gemini-2.0-flash") == (
        "gemini",
        "gemini-2.0-flash",
    )


def test_model_selector_requires_explicit_model(capsys):
    visual_qa = _load_visual_qa()

    with pytest.raises(SystemExit):
        visual_qa._split_model_selector(None)

    assert "--model is required" in capsys.readouterr().err


def test_native_selector_exits_with_runtime_message(capsys):
    visual_qa = _load_visual_qa()

    with pytest.raises(SystemExit):
        visual_qa._split_model_selector("native")

    assert "agent runtime" in capsys.readouterr().err


def test_codex_selector_exits_with_runtime_message(capsys):
    visual_qa = _load_visual_qa()

    with pytest.raises(SystemExit):
        visual_qa._split_model_selector("codex")

    assert "agent runtime" in capsys.readouterr().err
