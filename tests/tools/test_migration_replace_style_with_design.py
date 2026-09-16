"""Tests for the replace_style_with_design migration.

Covers the one-shot migration semantics: legacy-only, DESIGN-only, both files
present, neither present, arbitrary legacy text, write failure, and repeated
runs.
"""
import importlib.util
import stat
import sys
from pathlib import Path

import pytest


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "20260916120000_replace_style_with_design.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "replace_style_with_design_migration", MIGRATION
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LEGACY = (
    "# Visual Style Seed: Card Arena\n\n"
    "## Initial Visual Seed\n\n"
    "polished vertical mobile card game UI with chunky rounded shapes\n\n"
    "## Avoid\n\n"
    "- muddy desaturated palettes\n"
)


# ---------- legacy-only ----------

def test_legacy_only_preserves_text_and_removes_style(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")

    migration.migrate(tmp_path)

    design = (tmp_path / "DESIGN.md").read_text(encoding="utf-8")
    assert design.startswith("# DESIGN: Card Arena\n")
    assert migration.LEGACY_HEADING in design
    # Lossless: every legacy line survives verbatim.
    design_lines = design.splitlines()
    for line in LEGACY.splitlines():
        assert line in design_lines
    assert not (tmp_path / "STYLE.md").exists()


def test_legacy_only_leaves_dimensions_unspecified(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")

    migration.migrate(tmp_path)

    design = (tmp_path / "DESIGN.md").read_text(encoding="utf-8")
    for index, dimension in enumerate(migration.DIMENSIONS, start=1):
        assert "### {}. {}".format(index, dimension) in design
    # Nine dimensions + Visual Identity + UI + Do + Dont == 13 placeholders,
    # so nothing was inferred for the legacy project.
    assert design.count(migration.UNSPECIFIED) == 13


def test_legacy_text_with_code_fence_stays_lossless(tmp_path: Path):
    migration = _load_migration()
    fence = "`" * 3
    weird = "# Visual Style: Odd\n\n{f}markdown\n## Not A Real Section\n{f}\n".format(f=fence)
    (tmp_path / "STYLE.md").write_text(weird, encoding="utf-8")

    migration.migrate(tmp_path)

    design = (tmp_path / "DESIGN.md").read_text(encoding="utf-8")
    assert "{f}markdown\n## Not A Real Section\n{f}".format(f=fence) in design
    # The quoting fence must be longer than any fence inside the legacy text,
    # otherwise the block terminates early and the rest leaks into the document.
    assert ("`" * 4) + "markdown" in design
    # The legacy heading stays quoted inside Legacy Style Notes rather than
    # becoming a section of the contract itself.
    assert design.index(migration.LEGACY_HEADING) < design.index("## Not A Real Section")


def test_project_name_falls_back_to_gdd(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "GDD.md").write_text(
        "# Game Design Document: Ember Run\n", encoding="utf-8"
    )
    (tmp_path / "STYLE.md").write_text(
        "# Visual Style Seed\n\nnothing\n", encoding="utf-8"
    )

    migration.migrate(tmp_path)

    assert (tmp_path / "DESIGN.md").read_text(encoding="utf-8").startswith(
        "# DESIGN: Ember Run\n"
    )


# ---------- DESIGN-only ----------

def test_design_only_is_a_noop(tmp_path: Path):
    migration = _load_migration()
    original = "# DESIGN: Card Arena\n\n## Visual Identity\n\nhand-painted.\n"
    (tmp_path / "DESIGN.md").write_text(original, encoding="utf-8")

    migration.migrate(tmp_path)

    assert (tmp_path / "DESIGN.md").read_text(encoding="utf-8") == original
    assert not (tmp_path / "STYLE.md").exists()


def test_no_files_is_a_noop(tmp_path: Path):
    migration = _load_migration()

    migration.migrate(tmp_path)

    assert not (tmp_path / "DESIGN.md").exists()
    assert not (tmp_path / "STYLE.md").exists()


# ---------- both present ----------

def test_both_present_keeps_design_untouched_and_drops_style(tmp_path: Path):
    migration = _load_migration()
    original = "# DESIGN: Card Arena\n\n## Visual Identity\n\nhand-painted.\n"
    (tmp_path / "DESIGN.md").write_text(original, encoding="utf-8")
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")

    migration.migrate(tmp_path)

    design = (tmp_path / "DESIGN.md").read_text(encoding="utf-8")
    assert design == original
    assert "Initial Visual Seed" not in design
    assert not (tmp_path / "STYLE.md").exists()


def test_both_present_style_content_does_not_affect_result(tmp_path: Path):
    """Changing STYLE.md alone must not change what the migration produces."""
    migration = _load_migration()
    original = "# DESIGN: Card Arena\n\n## Visual Identity\n\nhand-painted.\n"

    results = []
    for legacy in (LEGACY, "# Visual Style: Totally Different\n\nneon brutalism\n"):
        project = tmp_path / "p{}".format(len(results))
        project.mkdir()
        (project / "DESIGN.md").write_text(original, encoding="utf-8")
        (project / "STYLE.md").write_text(legacy, encoding="utf-8")
        migration.migrate(project)
        results.append((project / "DESIGN.md").read_text(encoding="utf-8"))

    assert results[0] == results[1] == original


def test_both_present_refuses_to_drop_style_when_design_is_empty(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "DESIGN.md").write_text("   \n", encoding="utf-8")
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")

    with pytest.raises(RuntimeError):
        migration.migrate(tmp_path)

    assert (tmp_path / "STYLE.md").read_text(encoding="utf-8") == LEGACY


# ---------- failure / idempotence ----------

@pytest.mark.skipif(sys.platform == "win32",
                    reason="read-only directories do not block writes on Windows")
def test_write_failure_leaves_style_in_place(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")
    tmp_path.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(OSError):
            migration.migrate(tmp_path)
    finally:
        tmp_path.chmod(stat.S_IRWXU)

    assert (tmp_path / "STYLE.md").read_text(encoding="utf-8") == LEGACY
    assert not (tmp_path / "DESIGN.md").exists()


def test_rerun_is_idempotent(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")

    migration.migrate(tmp_path)
    first = (tmp_path / "DESIGN.md").read_text(encoding="utf-8")
    migration.migrate(tmp_path)
    migration.migrate(tmp_path)

    assert (tmp_path / "DESIGN.md").read_text(encoding="utf-8") == first
    assert not (tmp_path / "STYLE.md").exists()


# ---------- TOC ----------

def test_toc_entry_is_replaced_not_duplicated(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")
    (tmp_path / "TOC.md").write_text(
        "# Document Index: Card Arena\n\n"
        "- `ROADMAP.md` - plan\n"
        "- `STYLE.md` - Visual prompt style guide for image generation\n"
        "- `ASSETS.md` - assets\n",
        encoding="utf-8",
    )

    migration.migrate(tmp_path)
    migration.migrate(tmp_path)

    toc = (tmp_path / "TOC.md").read_text(encoding="utf-8")
    assert "`STYLE.md`" not in toc
    assert toc.count("- `DESIGN.md`") == 1


def test_toc_entry_is_added_when_absent(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")
    (tmp_path / "TOC.md").write_text(
        "# Document Index: Card Arena\n\n"
        "- `ROADMAP.md` - plan\n"
        "- `ASSETS.md` - assets\n",
        encoding="utf-8",
    )

    migration.migrate(tmp_path)

    toc = (tmp_path / "TOC.md").read_text(encoding="utf-8")
    assert toc.count("- `DESIGN.md`") == 1
    assert toc.index("- `ASSETS.md`") < toc.index("- `DESIGN.md`")


def test_missing_toc_is_tolerated(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")

    migration.migrate(tmp_path)

    assert not (tmp_path / "TOC.md").exists()
