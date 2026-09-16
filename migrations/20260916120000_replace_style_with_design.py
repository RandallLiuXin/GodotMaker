"""Replace the legacy project STYLE.md with the DESIGN.md visual contract.

One-shot migration, no compatibility layer:

- only `STYLE.md`  -> its text is preserved verbatim inside a new `DESIGN.md`
  (`Legacy Style Notes`), the nine image-style dimensions stay unspecified, and
  the obsolete `STYLE.md` is removed once the new file reads back intact;
- only `DESIGN.md` -> no-op;
- both            -> `DESIGN.md` is the sole active authority. Nothing is
  merged or copied from `STYLE.md`; it is removed once `DESIGN.md` is confirmed
  readable and non-empty;
- neither         -> nothing to migrate (`/gm-gdd` writes `DESIGN.md`).
"""
from pathlib import Path

LEGACY_HEADING = "## Legacy Style Notes"

# Section order and wording are bound to `templates/DESIGN.md` by
# tests/test_design_md_contract.py — change both together.
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

UNSPECIFIED = "{unspecified}"


def _project_name(target: Path, legacy: str) -> str:
    """Project name from the legacy STYLE.md title, else GDD.md, else generic."""
    for line in legacy.splitlines():
        if line.startswith("# ") and ":" in line:
            name = line.split(":", 1)[1].strip()
            if name and not name.startswith("{"):
                return name
        if line.startswith("# "):
            break

    gdd = target / "GDD.md"
    if gdd.exists():
        prefix = "# Game Design Document:"
        first = gdd.read_text(encoding="utf-8").splitlines()[:1]
        if first and first[0].startswith(prefix):
            name = first[0][len(prefix):].strip()
            if name:
                return name
    return "Project Name"


def _fence_for(text: str) -> str:
    """A backtick fence longer than any run already inside `text`.

    Keeps the quoted legacy block lossless even when the old file contained
    its own fenced code.
    """
    longest = 0
    run = 0
    for char in text:
        run = run + 1 if char == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def _build_design_md(target: Path, legacy: str) -> str:
    fence = _fence_for(legacy)
    lines = [
        f"# DESIGN: {_project_name(target, legacy)}",
        "",
        "<!-- Migrated from the legacy STYLE.md. Everything the old file said is",
        "     preserved verbatim under Legacy Style Notes; nothing was inferred or",
        "     invented for it. Fill the sections below as the project's visual",
        "     direction is actually established. -->",
        "",
        "## Visual Identity",
        "",
        UNSPECIFIED,
        "",
        "## Image Style",
        "",
    ]
    for index, dimension in enumerate(DIMENSIONS, start=1):
        lines += [f"### {index}. {dimension}", "", UNSPECIFIED, ""]
    lines += [
        "## UI Visual Language",
        "",
        UNSPECIFIED,
        "",
        "## Do",
        "",
        f"- {UNSPECIFIED}",
        "",
        "## Don't",
        "",
        f"- {UNSPECIFIED}",
        "",
        LEGACY_HEADING,
        "",
        "Verbatim content of the removed `STYLE.md`. Historical record only — it",
        "does not override or supplement the sections above.",
        "",
        fence + "markdown",
        legacy.rstrip("\n"),
        fence,
        "",
    ]
    return "\n".join(lines)


def _ensure_toc_entry(target: Path) -> None:
    """Point TOC.md at DESIGN.md and drop any stale STYLE.md entry."""
    toc = target / "TOC.md"
    if not toc.exists():
        return

    entry = ("- `DESIGN.md` — Project visual contract: visual identity, nine "
             "image-style dimensions, UI visual language, Do / Don't "
             "(produced by `/gm-gdd`)")

    kept: list[str] = []
    replaced = False
    for line in toc.read_text(encoding="utf-8").splitlines():
        if line.startswith("- `STYLE.md`"):
            if not replaced:
                kept.append(entry)
                replaced = True
            continue
        if line.startswith("- `DESIGN.md`"):
            if replaced:
                continue
            replaced = True
        kept.append(line)

    if not replaced:
        anchor = next((line for line in kept if line.startswith("- `ASSETS.md`")), None)
        if anchor is None:
            anchor = next((line for line in kept if line.startswith("- `ROADMAP.md`")), None)
        if anchor is None:
            kept.append(entry)
        else:
            kept.insert(kept.index(anchor) + 1, entry)

    text = "\n".join(kept).rstrip("\n") + "\n"
    if text != toc.read_text(encoding="utf-8"):
        toc.write_text(text, encoding="utf-8")
        print("Updated TOC.md with the DESIGN.md entry")


def migrate(target: Path) -> None:
    """target is the absolute path to the game project root.

    Scripts MUST be idempotent — re-runs after a partial failure must
    not corrupt state. Raise an exception to abort the migration chain.
    """
    style_path = target / "STYLE.md"
    design_path = target / "DESIGN.md"

    if design_path.exists():
        if style_path.exists():
            if not design_path.read_text(encoding="utf-8").strip():
                raise RuntimeError(
                    "DESIGN.md exists but is empty; refusing to remove STYLE.md. "
                    "Restore DESIGN.md, then re-run the migration."
                )
            style_path.unlink()
            print("DESIGN.md is the active visual contract; removed obsolete STYLE.md")
        else:
            print("DESIGN.md already present; nothing to migrate")
        _ensure_toc_entry(target)
        return

    if not style_path.exists():
        print("Neither DESIGN.md nor STYLE.md present; nothing to migrate")
        return

    legacy = style_path.read_text(encoding="utf-8")
    content = _build_design_md(target, legacy)
    design_path.write_text(content, encoding="utf-8")

    if design_path.read_text(encoding="utf-8") != content:
        raise RuntimeError(
            "DESIGN.md did not read back as written; STYLE.md left in place."
        )

    style_path.unlink()
    print("Migrated STYLE.md into DESIGN.md (Legacy Style Notes) and removed STYLE.md")
    _ensure_toc_entry(target)
