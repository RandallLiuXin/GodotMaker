"""Tests for add_style_md migration."""
import importlib.util
from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "20260521191628_add_style_md.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("add_style_md_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_creates_style_md_from_assets_art_direction(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "GDD.md").write_text(
        "# Game Design Document: Card Arena\n", encoding="utf-8"
    )
    (tmp_path / "ASSETS.md").write_text(
        "# Assets: Card Arena\n\n"
        "## Art Direction\n\n"
        "- **Style:** polished vertical mobile card game UI with chunky rounded shapes.\n"
        "- **Color palette:** bright blues, gold accents.\n"
        "- **Perspective:** vertical portrait UI.\n"
        "- **Lighting:** soft glossy highlights.\n"
        "- **Reference:** reference.png\n\n"
        "## Asset Table\n",
        encoding="utf-8",
    )

    migration.migrate(tmp_path)

    style = (tmp_path / "STYLE.md").read_text(encoding="utf-8")
    assert "# Visual Style: Card Arena" in style
    assert "polished vertical mobile card game UI with chunky rounded shapes" in style
    assert "bright blues, gold accents" in style
    assert "Reference image: reference.png" in style
    assert "shapes.." not in style
    assert "accents.." not in style


def test_adds_style_md_to_toc(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "TOC.md").write_text(
        "# Document Index\n\n"
        "## Cross-Tag (live, accumulating)\n"
        "- `GDD.md` - Game Design Document\n"
        "- `ROADMAP.md` - Tag-by-tag release plan\n"
        "- `MEMORY.md` - Knowledge base index\n"
        "- `ASSETS.md` - Cross-tag asset manifest\n",
        encoding="utf-8",
    )

    migration.migrate(tmp_path)

    toc = (tmp_path / "TOC.md").read_text(encoding="utf-8")
    assert "- `STYLE.md` - Visual prompt style guide for image generation" in toc
    assert toc.index("`ASSETS.md`") < toc.index("`STYLE.md`")


def test_leaves_existing_style_md_unchanged(tmp_path: Path):
    migration = _load_migration()
    style_path = tmp_path / "STYLE.md"
    style_path.write_text("# Visual Style: Custom\n", encoding="utf-8")

    migration.migrate(tmp_path)

    assert style_path.read_text(encoding="utf-8") == "# Visual Style: Custom\n"
