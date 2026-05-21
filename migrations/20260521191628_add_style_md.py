"""Create STYLE.md for existing projects."""
from pathlib import Path


def _extract_markdown_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip().lower() == heading.lower():
            start = index + 1
            break
    if start is None:
        return ""

    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def _extract_field(section: str, label: str) -> str:
    prefix = f"- **{label}:**"
    for line in section.splitlines():
        if line.strip().startswith(prefix):
            return line.split(prefix, 1)[1].strip()
    return ""


def _sentence(value: str) -> str:
    return value.strip().rstrip(".。;；")


def _project_name(target: Path) -> str:
    gdd = target / "GDD.md"
    if not gdd.exists():
        return "Project Name"
    first_line = gdd.read_text(encoding="utf-8").splitlines()[0:1]
    if not first_line:
        return "Project Name"
    prefix = "# Game Design Document:"
    if first_line[0].startswith(prefix):
        return first_line[0][len(prefix):].strip() or "Project Name"
    return "Project Name"


def _build_style_md(target: Path) -> str:
    assets = target / "ASSETS.md"
    art_direction = ""
    if assets.exists():
        art_direction = _extract_markdown_section(
            assets.read_text(encoding="utf-8"), "## Art Direction"
        )

    style = _extract_field(art_direction, "Style")
    palette = _extract_field(art_direction, "Color palette")
    perspective = _extract_field(art_direction, "Perspective")
    lighting = _extract_field(art_direction, "Lighting")
    reference = _extract_field(art_direction, "Reference")

    anchor = style or "Use the visual style described in GDD.md section 4."
    suffix_parts = [
        _sentence(part) for part in [style, palette, perspective, lighting] if part
    ]
    suffix = ". ".join(suffix_parts)
    if suffix:
        suffix += ". Clean game-ready rendering."
    else:
        suffix = "Clean game-ready rendering matching the project visual direction."

    reference_note = (
        f"Reference image: {reference}"
        if reference
        else "Review GDD.md section 4 and existing scene references."
    )

    return f"""# Visual Style: {_project_name(target)}

## Style Anchor

{anchor}

## Prompt Suffix

{suffix}

## UI / Asset Rules

- Generate game-ready assets that match the style anchor.
- Keep UI components separate when generating UI kits.
- Avoid baked-in placeholder text or numbers unless requested.

## Avoid

- Inconsistent style between generated assets.
- Overly detailed elements that will not read at gameplay size.

## Reference Notes

- {reference_note}
"""


def _ensure_toc_entry(target: Path) -> None:
    toc = target / "TOC.md"
    if not toc.exists():
        return

    text = toc.read_text(encoding="utf-8")
    entry = "- `STYLE.md` - Visual prompt style guide for image generation"
    if "`STYLE.md`" in text:
        return

    for line in text.splitlines():
        if line.startswith("- `ASSETS.md`"):
            text = text.replace(line, f"{line}\n{entry}", 1)
            break
    else:
        for line in text.splitlines():
            if line.startswith("- `ROADMAP.md`"):
                text = text.replace(line, f"{line}\n{entry}", 1)
                break
        else:
            text = text.rstrip() + f"\n{entry}\n"

    toc.write_text(text, encoding="utf-8")
    print("Updated TOC.md with STYLE.md entry")


def migrate(target: Path) -> None:
    """target is the absolute path to the game project root.

    Scripts MUST be idempotent — re-runs after a partial failure must
    not corrupt state. Raise an exception to abort the migration chain.
    """
    style_path = target / "STYLE.md"
    if style_path.exists():
        print("STYLE.md already exists; leaving unchanged")
        _ensure_toc_entry(target)
        return

    style_path.write_text(_build_style_md(target), encoding="utf-8")
    print("Created STYLE.md")
    _ensure_toc_entry(target)
