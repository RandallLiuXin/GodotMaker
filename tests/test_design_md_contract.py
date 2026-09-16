"""Contract tests for the project DESIGN.md visual contract.

`DESIGN.md` replaces the legacy `STYLE.md` seed outright: there is no dual
read, no dual write, and no priority fallback. These tests pin the template
shape, the no-invention authoring rules, and the fact that every active
consumer entry point names `DESIGN.md`.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = REPO_ROOT / "templates" / "DESIGN.md"

MIGRATION = (
    REPO_ROOT / "migrations" / "20260916120000_replace_style_with_design.py"
)

# The nine image-style dimensions are a fixed contract, in this order.
DIMENSIONS = (
    "Medium And Rendering",
    "Color And Value",
    "Shape And Silhouette",
    "Line And Edge",
    "Material And Texture",
    "Lighting And Shadow",
    "Space, Perspective, And Depth",
    "Composition And Visual Hierarchy",
    "Detail Density And Abstraction",
)

UI_NA_SENTENCE = "N/A - this project has no visible UI."

HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
STYLE_MD = re.compile(r"\bSTYLE\.md\b", re.IGNORECASE)

# `STYLE.md` may only survive where it describes history or the migration that
# removes it. Everything else must name `DESIGN.md`.
STYLE_MD_ALLOWED_FILES = {
    "migrations/20260521191628_add_style_md.py",
    "migrations/20260916120000_replace_style_with_design.py",
    "tests/tools/test_migration_add_style_md.py",
    "tests/tools/test_migration_replace_style_with_design.py",
    "tests/test_design_md_contract.py",
    # Pins that a tag archive sealed before DESIGN.md keeps its frozen
    # STYLE.md without it ever being read as the visual contract.
    "tests/tools/test_seal_tag.py",
    "CHANGELOG.md",
}
STYLE_MD_ALLOWED_PREFIXES = ("docs/update/",)


def _template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _authoring_surface() -> str:
    """Template text with the instructional HTML comments stripped."""
    return HTML_COMMENT.sub("", _template_text())


def _headings(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines()
            if line.startswith("## ") or line.startswith("### ")]


def _load_migration():
    spec = importlib.util.spec_from_file_location("design_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# ---------- AC-01: template shape ----------

def test_style_template_is_gone_and_design_template_ships():
    assert TEMPLATE.exists(), "templates/DESIGN.md must exist"
    assert not (REPO_ROOT / "templates" / "STYLE.md").exists(), (
        "templates/STYLE.md must be removed, not kept alongside DESIGN.md"
    )


def test_template_sections_are_fixed_and_ordered():
    expected = [
        "## Visual Identity",
        "## Image Style",
        *[f"### {i}. {name}" for i, name in enumerate(DIMENSIONS, start=1)],
        "## UI Visual Language",
        "## Do",
        "## Don't",
    ]
    assert _headings(_template_text()) == expected


def test_template_title_is_a_design_heading():
    assert _template_text().splitlines()[0].startswith("# DESIGN: ")


def test_template_is_plain_markdown():
    """No YAML front matter, no token blocks, no required imagery."""
    text = _template_text()
    assert not text.startswith("---"), "DESIGN.md must not carry YAML front matter"
    assert "```" not in text, "DESIGN.md is plain prose — no fenced token blocks"
    assert "![" not in text, "DESIGN.md must not require embedded screenshots"


def test_template_authoring_surface_has_no_technical_fields():
    """Runtime/asset requirements belong to ASSETS.md and the Asset Skills."""
    surface = _authoring_surface().lower()
    for term in ("canvas size", "alpha", "frame count", "atlas", "nine-slice",
                 "stylebox", "atlastexture", "spriteframes", ".tres", ".png"):
        assert term not in surface, f"DESIGN.md must not request `{term}`"


def test_template_documents_the_ui_na_rule():
    assert UI_NA_SENTENCE in _template_text()


def test_template_documents_the_unspecified_placeholder():
    assert "{unspecified}" in _template_text()


def test_template_stays_concise():
    """A reusable visual contract, not an art bible."""
    assert len(_template_text().splitlines()) <= 200


def test_migration_skeleton_matches_the_template_dimensions():
    """The migration inlines the section list — keep it bound to the template."""
    migration = _load_migration()
    assert migration.DIMENSIONS == DIMENSIONS


# ---------- AC-02: no invented rules ----------

def test_decomposer_forbids_inventing_visual_rules():
    text = _read("agents/decomposer.md")
    step = text.split("### Step 2: DESIGN.md", 1)[1].split("### Step 3:", 1)[0]
    assert "Never invent" in step
    assert "{unspecified}" in step
    assert UI_NA_SENTENCE in step


def test_decomposer_limits_subsequent_mode_to_changed_sections():
    text = _read("agents/decomposer.md")
    step = text.split("### Step 2: DESIGN.md", 1)[1].split("### Step 3:", 1)[0]
    assert "leave every other section exactly as it is" in step
    assert "leave `DESIGN.md`\n  untouched" in step


def test_gdd_gate_checks_the_design_contract():
    text = _read("skills/core/gm-gdd/SKILL.md")
    assert "- [ ] `DESIGN.md` exists with Visual Identity, the nine numbered image-style" in text
    assert "N/A for a project with no visible UI" in text
    assert "is left `{unspecified}`" in text


# ---------- AC-03: every active consumer entry point ----------

def test_gdd_stage_schema_requires_design_md():
    schema = json.loads(_read("config/stage_schemas.json"))
    files = schema["gdd"]["files"]
    assert "DESIGN.md" in files
    assert "STYLE.md" not in files


def test_file_permission_hook_guards_design_md():
    sys.path.insert(0, str(REPO_ROOT / "hooks"))
    try:
        import check_file_permissions  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    assert "design.md" in check_file_permissions.PLANNING_DOCS
    assert "style.md" not in check_file_permissions.PLANNING_DOCS


def test_stage_reminder_expects_design_md_in_the_tag_archive():
    sys.path.insert(0, str(REPO_ROOT / "hooks"))
    try:
        import stage_reminder  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    assert "DESIGN.md" in stage_reminder._TAG_ARCHIVE_FILES
    assert "STYLE.md" not in stage_reminder._TAG_ARCHIVE_FILES


def test_seal_tag_archives_design_md():
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import seal_tag  # noqa: PLC0415
    finally:
        sys.path.pop(0)
    assert ("DESIGN.md", "DESIGN.md") in seal_tag.ARCHIVE_MAP
    assert not any(src == "STYLE.md" for src, _dest in seal_tag.ARCHIVE_MAP)
    assert "DESIGN.md" in seal_tag.ARCHIVE_FILE_ROLES
    assert "STYLE.md" not in seal_tag.ARCHIVE_FILE_ROLES


@pytest.mark.parametrize("rel, needle", [
    ("skills/core/gm-finalize/SKILL.md", "| `docs/tags/<Tag>/DESIGN.md` | `DESIGN.md` |"),
    ("skills/core/gm-gdd/SKILL.md",
     "Owned Files: SCENES.md, DESIGN.md, ASSETS.md, TOC.md"),
    ("agents/decomposer.md",
     "| `scene-asset-package` | `DESIGN.md`, `SCENES.md`, `ASSETS.md`, `TOC.md` |"),
    ("skills/core/gm-asset/SKILL.md", "Read `PLAN.md`, `DESIGN.md`, `SCENES.md`"),
    ("templates/TOC.md", "- `DESIGN.md` — Project visual contract"),
])
def test_consumer_entry_points_name_design_md(rel: str, needle: str):
    assert needle in _read(rel)


def test_no_active_reference_to_style_md_remains():
    """Controlled repository-wide search — see STYLE_MD_ALLOWED_* above."""
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    offenders = []
    for rel in tracked:
        rel = rel.strip()
        if not rel or rel in STYLE_MD_ALLOWED_FILES:
            continue
        if rel.startswith(STYLE_MD_ALLOWED_PREFIXES):
            continue
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if STYLE_MD.search(text):
            offenders.append(rel)

    assert not offenders, (
        "These files still reference STYLE.md; every active consumer must read "
        f"DESIGN.md instead: {sorted(offenders)}"
    )


# ---------- AC-05: published layout ----------

def test_published_templates_expose_design_md_only(tmp_path: Path):
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    try:
        import publish  # noqa: PLC0415
    finally:
        sys.path.pop(0)

    target = tmp_path / ".claude" / "templates"
    publish.publish_directory(REPO_ROOT / "templates", target, "templates/", "*.md")

    assert (target / "DESIGN.md").exists()
    assert not (target / "STYLE.md").exists()
