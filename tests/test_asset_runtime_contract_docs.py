from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_codex_generation_uses_parent_batch_claim_contract():
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")
    codex = _read("skills/core/gm-asset/references/providers/codex-image.md")
    skill = _read("skills/core/gm-asset/SKILL.md")

    assert "references/providers/codex-image.md" in runtime
    assert "references/providers/codex-image.md" in skill
    assert "ImageGenerationEnd.saved_path" in codex
    assert "tools/codex_image_claim.py --plan" in codex
    assert "Do not inspect `generated_images`" in codex
    assert "Do not choose files by modified time" in codex
    assert "Do not copy files" in codex


def test_generic_asset_docs_do_not_embed_codex_provider_protocol():
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")
    skill = _read("skills/core/gm-asset/SKILL.md")

    forbidden = [
        "ImageGenerationEnd.saved_path",
        "tools/codex_image_claim.py --plan",
        "codex exec --json",
        "generated_images",
        "Each subagent claims",
        "Require each subagent to follow the Source Claim section",
        "Follow the Source Claim section",
        "Sort-Object LastWriteTime",
        "Select-Object -First 1",
    ]
    for token in forbidden:
        assert token not in runtime
        assert token not in skill
