from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_verifier_dispatch_uses_configured_godot_path():
    text = _text("skills/core/_shared/verifier-dispatch.md")
    assert "### Godot Path" in text
    assert "{Absolute path read from .claude/godotmaker.yaml}" in text
    assert "godot --headless" not in text
    assert '"<godot_path>" --headless --quit' in text
    assert '"<godot_path>" --headless --path .' in text


def test_verifier_agent_references_dispatch_and_examples_use_godot_path_placeholder():
    text = _text("agents/verifier.md")
    assert "references/verifier-dispatch.md" in text
    assert "## Brief Format (What You Receive)" not in text
    assert "godot --headless" not in text
    assert '"<godot_path>" --headless --quit' in text
    assert '"<godot_path>" --headless --path .' in text
