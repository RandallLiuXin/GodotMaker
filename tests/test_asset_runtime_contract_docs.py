from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def test_provider_contracts_are_separate_from_generic_asset_docs():
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")
    skill = _read("skills/core/gm-asset/SKILL.md")
    codex = _read("skills/core/gm-asset/references/providers/codex.md")
    native = _read("skills/core/gm-asset/references/providers/native.md")
    gemini = _read("skills/core/gm-asset/references/providers/gemini.md")
    codex_runtime = _read("agent-runtimes/codex/references/runtime-mapping.md")
    claude_runtime = _read("agent-runtimes/claude-code/references/runtime-mapping.md")

    assert "references/providers/codex.md" in runtime
    assert "references/providers/native.md" in skill
    assert "references/providers/gemini.md" in skill
    assert "generated_path" in codex
    assert "--out-report" in codex
    assert "exactly one new image file" in codex
    assert "tools/codex_image_claim.py --plan" in codex
    assert "active coding-agent runtime's native image-generation path" in native
    assert "tools/asset_source_generate.py --spec" in gemini
    assert "generated-path claim protocol" in codex_runtime
    assert "generated-path claim protocol" in claude_runtime
    assert "--out-report" in codex_runtime
    assert "--out-report" in claude_runtime

    forbidden = [
        "ImageGenerationEnd.saved_path",
        "tools/codex_image_claim.py --plan",
        "codex exec --json",
        "generated_images",
        "Sort-Object LastWriteTime",
        "Select-Object -First 1",
    ]
    for token in forbidden:
        assert token not in runtime
        assert token not in skill

    assert "ImageGenerationEnd.saved_path" not in codex
    assert "\"saved_path\"" not in codex
    assert "saved_path claim protocol" not in codex_runtime
    assert "saved_path claim protocol" not in claude_runtime


def test_gm_asset_manager_dispatches_asset_producer_units():
    skill = _read("skills/core/gm-asset/SKILL.md")
    producer = _read("agents/asset-producer.md")

    assert "Dispatch `asset-producer`" in skill
    assert "Do not generate raw visual art in the manager context." in skill
    assert "Dispatch one subagent per production unit." in skill
    assert "## Asset Producer Report:" in producer
    assert "Write only the output paths listed in the brief." in producer
    assert "Use visible scene references and canonical asset references" in producer


def test_production_unit_docs_are_first_entry_points():
    skill = _read("skills/core/gm-asset/SKILL.md")
    planner = _read("skills/core/gm-asset/references/asset-planner.md")
    runtime = _read("skills/core/gm-asset/references/asset-runtime-pipeline.md")

    units = [
        "screen-reference",
        "character-bundle",
        "fx-bundle",
        "ui-kit",
        "compact-prop-pack",
        "background-map",
        "platform-strip",
        "scene-prop-set",
    ]
    for unit in units:
        path = f"skills/core/gm-asset/references/production-units/{unit}.md"
        assert (REPO_ROOT / path).exists(), f"missing production unit: {unit}"
        assert f"references/production-units/{unit}.md" in skill
        assert f"`{unit}`" in planner

    assert "## Production Shapes" in runtime
    assert "## Processing Status" in runtime
    assert "## Extraction Status" in runtime
    assert "## Curation Field" in runtime


def test_ui_and_prop_units_default_to_autoslice():
    ui = _read("skills/core/gm-asset/references/production-units/ui-kit.md")
    props = _read("skills/core/gm-asset/references/production-units/compact-prop-pack.md")
    curation = _read("skills/core/gm-asset/references/asset-curation.md")

    assert "--snap-mode autoslice" in ui
    assert "--snap-mode autoslice" in props
    assert "--snap-mode grid" in ui
    assert "--snap-mode grid" in props
    assert "Use the assigned production-unit doc for extraction" in curation
