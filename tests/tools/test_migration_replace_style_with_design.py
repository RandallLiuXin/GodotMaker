"""Tests for the replace_style_with_design migration.

Covers the one-shot migration semantics: legacy-only, DESIGN-only, both files
present, neither present, arbitrary legacy text, write failure, and repeated
runs.
"""
import errno
import importlib.util
import os
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

def test_write_failure_leaves_style_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A failed DESIGN.md write must never cost the only copy of the legacy text.

    The failure is injected rather than provoked with directory permissions:
    read-only directories do not block writes on Windows, nor for a root user
    in a container, so a permission-based version of this test silently stops
    testing anything on most runners.
    """
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")

    def out_of_space(_src, _dst):
        raise OSError(errno.ENOSPC, "No space left on device")

    # Fails the final swap, so the real temp-file write and cleanup still run.
    monkeypatch.setattr(os, "replace", out_of_space)

    with pytest.raises(OSError):
        migration.migrate(tmp_path)

    assert (tmp_path / "STYLE.md").read_text(encoding="utf-8") == LEGACY
    assert not (tmp_path / "DESIGN.md").exists()
    assert list(tmp_path.glob("*" + migration.TMP_SUFFIX)) == []


def test_a_failed_write_never_leaves_a_partial_design_for_the_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The regression behind the atomic write.

    A torn DESIGN.md would still be non-empty, so the retry would take the
    both-files path, treat the truncated file as the active contract, and
    delete STYLE.md — losing the legacy text for good.
    """
    migration = _load_migration()
    raw = LEGACY.encode("utf-8")
    (tmp_path / "STYLE.md").write_bytes(raw)

    def out_of_space(_src, _dst):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "replace", out_of_space)
    with pytest.raises(OSError):
        migration.migrate(tmp_path)
    monkeypatch.undo()

    # The retry migrate.py performs, the migration still being pending.
    migration.migrate(tmp_path)

    assert _extract_legacy_block(tmp_path / "DESIGN.md") == raw
    assert not (tmp_path / "STYLE.md").exists()


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


def test_toc_line_endings_are_preserved(tmp_path: Path):
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_text(LEGACY, encoding="utf-8")
    (tmp_path / "TOC.md").write_bytes(
        b"# Document Index: Card Arena\r\n\r\n"
        b"- `ROADMAP.md` - plan\r\n"
        b"- `STYLE.md` - Visual prompt style guide for image generation\r\n"
        b"- `ASSETS.md` - assets\r\n"
    )

    migration.migrate(tmp_path)

    toc = (tmp_path / "TOC.md").read_bytes()
    assert b"\r\n" in toc
    assert b"\n" not in toc.replace(b"\r\n", b"")
    assert b"`STYLE.md`" not in toc


# ---------- byte-exact preservation of the legacy text ----------

def _extract_legacy_block(design_path: Path) -> bytes:
    """Independently pull the quoted block out of Legacy Style Notes.

    Deliberately does NOT reuse the migration's own extractor: the point is to
    read the produced document the way a human recovering the old file would.
    """
    text = design_path.read_bytes().decode("utf-8")
    lines = text.splitlines(keepends=True)
    for start, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if not stripped.endswith("markdown"):
            continue
        fence = stripped[: -len("markdown")]
        if len(fence) < 3 or set(fence) != {"`"}:
            continue
        for end in range(start + 1, len(lines)):
            if lines[end].rstrip("\r\n") == fence:
                return "".join(lines[start + 1:end]).encode("utf-8")
    raise AssertionError("no Legacy Style Notes block found")


@pytest.mark.parametrize("raw", [
    pytest.param(b"# Visual Style: A\n\nseed\n", id="lf"),
    pytest.param(b"# Visual Style: A\n\nseed\n\n\n", id="lf-trailing-blank-lines"),
    pytest.param(b"# Visual Style: A\r\n\r\nseed\r\n", id="crlf"),
    pytest.param(b"# Visual Style: A\r\n\r\nseed\r\n\r\n\r\n", id="crlf-trailing-blank-lines"),
    pytest.param(b"# Visual Style: A\rseed\r", id="cr"),
    pytest.param(b"# Visual Style: A\n```md\nx\n```\n\n", id="inner-fence-and-blank-tail"),
    pytest.param("# Visual Style: A\n\n  \tseed  \n".encode("utf-8"), id="whitespace-and-nbsp"),
])
def test_legacy_text_survives_byte_for_byte(tmp_path: Path, raw: bytes):
    """A file ending in a newline must come back out of DESIGN.md unchanged."""
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_bytes(raw)

    migration.migrate(tmp_path)

    assert _extract_legacy_block(tmp_path / "DESIGN.md") == raw
    assert migration.NO_FINAL_NEWLINE_NOTE not in (
        (tmp_path / "DESIGN.md").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("raw", [
    pytest.param(b"# Visual Style: A\n\nseed", id="no-final-newline"),
    pytest.param(b"", id="empty-file"),
])
def test_only_added_byte_is_a_closing_newline_and_it_is_disclosed(
    tmp_path: Path, raw: bytes
):
    """A fenced block needs a final newline. That single edit is stated in the
    document, so the original stays derivable."""
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_bytes(raw)

    migration.migrate(tmp_path)

    assert _extract_legacy_block(tmp_path / "DESIGN.md") == raw + b"\n"
    assert migration.NO_FINAL_NEWLINE_NOTE in (
        (tmp_path / "DESIGN.md").read_text(encoding="utf-8")
    )


def test_generated_sections_use_lf_regardless_of_platform(tmp_path: Path):
    """Only the quoted legacy block may carry foreign line endings."""
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_bytes(b"# Visual Style: A\n\nseed\n")

    migration.migrate(tmp_path)

    assert b"\r" not in (tmp_path / "DESIGN.md").read_bytes()


def test_migration_refuses_to_delete_style_when_the_block_cannot_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The delete is irreversible, so a broken embedding must stop it."""
    migration = _load_migration()
    (tmp_path / "STYLE.md").write_bytes(b"# Visual Style: A\n\nseed\n")
    monkeypatch.setattr(migration, "_extract_legacy", lambda _text: "corrupted")

    with pytest.raises(RuntimeError, match="round-trip"):
        migration.migrate(tmp_path)

    assert (tmp_path / "STYLE.md").read_bytes() == b"# Visual Style: A\n\nseed\n"
