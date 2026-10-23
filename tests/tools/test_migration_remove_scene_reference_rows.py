"""Upgrade coverage for removing obsolete scene-reference catalog rows."""
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "migrations" / "20261023000000_remove_scene_reference_rows.py"


def _module():
    spec = importlib.util.spec_from_file_location("remove_scene_reference_rows", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_migration_removes_only_framework_scene_reference_rows_and_is_idempotent(
    tmp_path,
):
    assets = tmp_path / "ASSETS.md"
    assets.write_text(
        "# Assets\n\n"
        "| # | Tag | Name | Type | Size | Generation Params | Runtime Type | Runtime Path | Status |\n"
        "|---|-----|------|------|------|-------------------|--------------|--------------|--------|\n"
        "| 1 | v0.1.0 | scene_main | reference | — | family=screen-reference | reference | references/scene_main.png | source_ready |\n"
        "| 2 | v0.1.0 | foundation | reference | — | family=screen-reference | reference | references/foundation.png | source_ready |\n"
        "| 3 | v0.1.0 | hero | animation | frames | family=character-bundle | SpriteFrames | res://assets/hero.tres | generated |\n"
        "| 4 | v0.1.0 | user_board | reference | — | user-maintained | - | references/user_board.png | provided |\n",
        encoding="utf-8",
    )
    references = tmp_path / "references"
    references.mkdir()
    expected = {
        name: payload
        for name, payload in {
            "scene_main.png": b"scene",
            "foundation.png": b"foundation",
            "user_board.png": b"user",
        }.items()
    }
    for name, payload in expected.items():
        (references / name).write_bytes(payload)

    migration = _module()
    migration.migrate(tmp_path)
    first = assets.read_text(encoding="utf-8")
    migration.migrate(tmp_path)

    assert "scene_main |" not in first
    assert "foundation |" not in first
    assert "hero |" in first
    assert "user_board |" in first
    assert assets.read_text(encoding="utf-8") == first
    assert {path.name: path.read_bytes() for path in references.iterdir()} == expected


def test_migration_handles_the_legacy_file_path_table(tmp_path):
    assets = tmp_path / "ASSETS.md"
    assets.write_text(
        "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |\n"
        "|---|-----|------|------|------|-------------------|-----------|--------|\n"
        "| 1 | v0.1.0 | scene_menu | reference | — | — | references/scene_menu.png | MISSING |\n"
        "| 2 | v0.1.0 | logo | sprite | 32x32 | — | assets/logo.png | provided |\n",
        encoding="utf-8",
    )

    _module().migrate(tmp_path)

    text = assets.read_text(encoding="utf-8")
    assert "scene_menu" not in text
    assert "logo" in text
