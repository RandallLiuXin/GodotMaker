"""Migrate existing projects to the tag-based pipeline layout.

Before: a project has a single root-level GDD.md + PLAN.md + STRUCTURE.md
+ SCENES.md + ASSETS.md describing the entire game in one shot. /gm-build
runs end-to-end against that single PLAN.

After: ROADMAP.md splits the game into SemVer-tagged release tags; root
docs are scoped to one tag at a time; finished tags are archived to
docs/tags/<tag>/. ASSETS.md tables carry a `Tag` column (introducing
tag per row); PLAN.md has a `## Tag Mechanics` section listing the
mechanics this tag must deliver.

This migration retroactively treats whatever was already there as
v0.1.0's working docs:
  - writes a stub ROADMAP.md with a single v0.1.0 entry the user can edit
  - copies the current root docs into docs/tags/v0.1.0/ as v0.1.0's
    archive (GDD.md is copied as GDD-snapshot.md to match the new naming)
  - leaves root files untouched — /gm-gdd subsequent-mode picks them up
    as the in-progress v0.1.0 working set on the next run
  - injects the missing schema additions into root ASSETS.md / PLAN.md so
    /gm-asset Resume Check + /gm-evaluate mechanic-orphan detection don't
    silently fall back / deadlock on legacy projects (root cause of the
    2026-05-09 e2e fixgap loop on GodotMakerTest1)

Does NOT run `git tag v0.1.0` — the migration cannot know whether the
working tree is in a state worth tagging. The user decides when to tag.

Idempotency contract: every step is independently idempotent — checks
the target end state and skips its own work if already present. So
re-running on a partially-migrated project completes whatever's still
missing without disturbing what's already there. There is no early-return
gate at the top.
"""
import os
import re
import shutil
from pathlib import Path

ROOT_DOCS = ("PLAN.md", "STRUCTURE.md", "SCENES.md")
INITIAL_TAG = "v0.1.0"
ROADMAP_FILENAME = "ROADMAP.md"
TAGS_DIR_REL = Path("docs") / "tags"

_TAG_HEADER_RE = re.compile(r"^\*\*Tag:\*\*\s*v\d+\.\d+\.\d+\s*$", re.MULTILINE)


def migrate(target: Path) -> None:
    """target is the absolute path to the game project root."""
    gdd = target / "GDD.md"
    plan = target / "PLAN.md"
    roadmap = target / ROADMAP_FILENAME
    archive_dir = target / TAGS_DIR_REL / INITIAL_TAG
    assets = target / "ASSETS.md"
    scenes = target / "SCENES.md"

    if not gdd.is_file() or not plan.is_file():
        print(f"  [skip] no existing GDD.md+PLAN.md at {target} — nothing to migrate")
        return

    # Validate PLAN.md is UTF-8 before any mutation. Strict read here so a
    # CP-1252/GBK file aborts cleanly instead of getting silently corrupted
    # by `errors="replace"` + write-back inside `_inject_tag_header`.
    try:
        plan.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        print(
            f"  [error] PLAN.md is not UTF-8 (decode failed at byte "
            f"{exc.start}). Re-save as UTF-8 without BOM and re-run the "
            f"migration. No files have been modified."
        )
        return

    if _inject_tag_header(plan, INITIAL_TAG):
        print(f"  [done] inject `**Tag:** {INITIAL_TAG}` header into PLAN.md")
    else:
        print("  [skip] PLAN.md already has **Tag:** header")

    archive_dir.mkdir(parents=True, exist_ok=True)
    snapshot = archive_dir / "GDD-snapshot.md"
    if snapshot.is_file():
        print(f"  [skip] docs/tags/{INITIAL_TAG}/GDD-snapshot.md already exists")
    else:
        shutil.copy2(gdd, snapshot)
        print(f"  [done] copy GDD.md → docs/tags/{INITIAL_TAG}/GDD-snapshot.md")

    for name in ROOT_DOCS:
        src = target / name
        dst = archive_dir / name
        if dst.is_file():
            print(f"  [skip] docs/tags/{INITIAL_TAG}/{name} already exists")
            continue
        if src.is_file():
            shutil.copy2(src, dst)
            print(f"  [done] copy {name} → docs/tags/{INITIAL_TAG}/{name}")
        else:
            print(f"  [skip] {name} not at root — nothing to archive")

    if roadmap.is_file():
        print(f"  [skip] {ROADMAP_FILENAME} already exists")
    else:
        project_name = _extract_project_name(gdd, plan)
        feature_bullets = _extract_feature_bullets(plan)
        _atomic_write_text(roadmap, _render_roadmap(project_name, feature_bullets))
        print(f"  [done] write {ROADMAP_FILENAME}")

    # Schema gaps the original migration shipped without. Each helper is
    # independently idempotent and prints its own [done]/[skip] line.
    if assets.is_file():
        _add_tag_column_to_assets(assets, INITIAL_TAG)
        if scenes.is_file():
            _add_scene_reference_rows(assets, scenes, INITIAL_TAG)
        else:
            print("  [skip] no SCENES.md — cannot add scene reference rows")
    else:
        print("  [skip] no ASSETS.md — cannot add Tag column / scene reference rows")

    _add_plan_mechanic_sections(plan)

    print(
        f"  [info] {INITIAL_TAG} archived but NOT git-tagged. Inspect "
        f"docs/tags/{INITIAL_TAG}/ and the new {ROADMAP_FILENAME}, then "
        f"run `git tag {INITIAL_TAG}` yourself when the working tree is "
        f"in a state worth marking."
    )


def _atomic_write_text(path: Path, content: str) -> None:
    """Write content to path via tempfile + os.replace. Crash-safe: a
    SIGTERM mid-write either leaves the original file intact (if rename
    didn't run) or fully replaced (if it did). LF line endings on every
    platform so the output diffs cleanly against the rest of the repo.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _inject_tag_header(plan: Path, tag: str) -> bool:
    """Add `**Tag:** {tag}` to PLAN.md if missing. Returns True if modified.

    Inserts two lines below the first H1; if no H1, prepends to top.
    Idempotent: any pre-existing `**Tag:** vX.Y.Z` (regardless of value)
    is left alone so a re-run never duplicates the header.

    Caller MUST have validated PLAN.md is UTF-8 (see migrate()).
    """
    text = plan.read_text(encoding="utf-8")
    if _TAG_HEADER_RE.search(text):
        return False

    header_line = f"**Tag:** {tag}"
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("# "):
            ending = "\n" if line.endswith("\n") else ""
            lines.insert(i + 1, f"\n{header_line}{ending}")
            _atomic_write_text(plan, "".join(lines))
            return True
    _atomic_write_text(plan, f"{header_line}\n\n{text}")
    return True


def _extract_project_name(gdd: Path, plan: Path) -> str:
    """Read the first H1 from GDD.md or PLAN.md, strip leading prose."""
    for path in (gdd, plan):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("# "):
                        title = line[2:].strip()
                        for prefix in ("Game Design Document:", "Game Plan:"):
                            if title.startswith(prefix):
                                title = title[len(prefix):].strip()
                        if title:
                            return title
        except OSError:
            continue
    return "Untitled"


def _extract_feature_bullets(plan: Path) -> list[str]:
    """Pull a few bullets to seed the v0.1.0 ROADMAP entry. Best-effort.

    Looks for the first table whose header includes 'System' or 'Task'
    and grabs up to 5 row labels. If nothing matches, returns a single
    placeholder line.
    """
    try:
        with open(plan, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return ["initial implementation (see docs/tags/v0.1.0/PLAN.md for details)"]

    bullets: list[str] = []
    in_table = False
    header_seen = False
    for raw in lines:
        line = raw.strip()
        if line.startswith("|") and not in_table:
            lower = line.lower()
            if "system" in lower or "task" in lower or "mechanic" in lower:
                in_table = True
                continue
        elif in_table:
            if not line.startswith("|"):
                if header_seen:
                    break
                continue
            if set(line.replace("|", "").strip()) <= set("-: "):
                header_seen = True
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and cells[0]:
                bullets.append(cells[0])
                if len(bullets) >= 5:
                    break

    if not bullets:
        bullets = ["initial implementation (see docs/tags/v0.1.0/PLAN.md for details)"]
    return bullets


def _render_roadmap(project_name: str, bullets: list[str]) -> str:
    bullet_lines = "\n".join(f"- {b}" for b in bullets)
    return f"""# Roadmap: {project_name}

<!-- Auto-generated by the tag-based-pipeline migration. The features
     listed under v0.1.0 below were extracted from the pre-migration
     PLAN.md as a starting point — edit them to match what was actually
     built (or what you want v0.1.0 to claim it built). Add later tags
     (v0.2.0, v0.3.0, ...) describing what comes next. -->

## SemVer convention

- **MAJOR** (vX.0.0): core gameplay loop changes
- **MINOR** (v0.X.0): new full system or playable module
- **PATCH** (v0.X.Y): in-tag fixes / small tweaks

## v0.1.0 — Initial implementation

<!-- Working docs at the moment of migration were archived to
     docs/tags/v0.1.0/ as a snapshot. The root GDD/PLAN/STRUCTURE/
     SCENES/ASSETS remain in place; /gm-gdd subsequent-mode
     picks them up as the in-progress v0.1.0 working set. -->

{bullet_lines}

## v0.2.0 — {{next theme}}

- {{feature 1}}
- {{feature 2}}
"""


# ── ASSETS.md schema upgrades ──────────────────────────────────────


def _add_tag_column_to_assets(assets: Path, tag: str) -> None:
    """Insert a `Tag` column into each markdown table in ASSETS.md that
    is missing one. Idempotent — tables already containing `Tag` are
    skipped. Existing data rows are backfilled with `tag` in the new
    column. Placeholder rows (all `...`) get `...`; summary rows
    (first cell `**Total**`) get `—`.

    Detects 4 table shapes by their first-column header:
      - first cell == "#"     → Asset Table / 3D Models / Audio
      - first cell == "Asset" → Budget Tracking
    The new `Tag` column is always inserted at index 1 (immediately
    after the first column).
    """
    text = assets.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    out: list[str] = []
    i = 0
    tables_modified = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        cells = _row_cells(stripped) if _is_table_row(stripped) else None

        # Header row of a recognized table?
        if cells is not None and _tag_insert_position(cells) is not None \
                and i + 1 < len(lines) and _is_separator_row(lines[i + 1]):
            insert_at = _tag_insert_position(cells)
            assert insert_at is not None  # narrowed by previous guard
            # Header
            new_header_cells = list(cells)
            new_header_cells.insert(insert_at, "Tag")
            out.append(_render_row(new_header_cells, line))
            # Separator
            sep_cells = _row_cells(lines[i + 1].strip())
            sep_cells.insert(insert_at, "-----")
            out.append(_render_row(sep_cells, lines[i + 1]))
            i += 2
            # Data rows
            while i < len(lines):
                row = lines[i]
                rstripped = row.strip()
                if not _is_table_row(rstripped):
                    break
                row_cells = _row_cells(rstripped)
                row_cells.insert(insert_at, _tag_value_for_row(row_cells, tag, insert_at))
                out.append(_render_row(row_cells, row))
                i += 1
            tables_modified += 1
            continue

        out.append(line)
        i += 1

    if tables_modified == 0:
        print("  [skip] ASSETS.md has no tables missing a Tag column")
        return
    _atomic_write_text(assets, "".join(out))
    print(f"  [done] add Tag column (= {tag}) to {tables_modified} ASSETS.md table(s)")


def _is_table_row(stripped: str) -> bool:
    return stripped.startswith("|") and stripped.endswith("|") and len(stripped) >= 2


def _row_cells(stripped: str) -> list[str]:
    """Split a `| a | b | c |` line into ['a', 'b', 'c']."""
    return [c.strip() for c in stripped.strip("|").split("|")]


def _is_separator_row(line: str) -> bool:
    """`|---|---|---|` and variants (`:---`, `---:`, `:---:`)."""
    stripped = line.strip()
    if not _is_table_row(stripped):
        return False
    cells = _row_cells(stripped)
    return all(c and set(c) <= set("-:") for c in cells)


def _tag_insert_position(header_cells: list[str]) -> int | None:
    """Where to insert `Tag` in a table header, or None if not applicable.

    Returns None if the header already has a `Tag` column or if the
    first column doesn't match a recognized signature.
    """
    if "Tag" in header_cells:
        return None
    if not header_cells:
        return None
    first = header_cells[0]
    if first == "#" or first == "Asset":
        return 1
    return None


def _tag_value_for_row(row_cells: list[str], tag: str, insert_at: int) -> str:
    """Decide what value to put in the new Tag cell for one data row.

    - Placeholder rows (all `...`) → `...`
    - Summary rows (first cell starts with `**`, e.g. `**Total**`) → `—`
    - Otherwise → `tag`
    """
    if all(c == "..." for c in row_cells if c):
        return "..."
    if row_cells and row_cells[0].startswith("**"):
        return "—"
    return tag


def _render_row(cells: list[str], original_line: str) -> str:
    """Render `cells` as a markdown table row. Preserves the original
    line's trailing newline (or lack thereof)."""
    rendered = "| " + " | ".join(cells) + " |"
    if original_line.endswith("\r\n"):
        return rendered + "\r\n"
    if original_line.endswith("\n"):
        return rendered + "\n"
    return rendered


# ── ASSETS.md scene reference rows ────────────────────────────────


def _scene_id_from_heading(heading: str) -> str:
    """Convert a `## Scene: <Name> [(...)]` heading line into a
    snake_case id matching Godot .tscn naming convention.

    Examples:
      "## Scene: MainMenu"                     → "main_menu"
      "## Scene: PauseOverlay (CanvasLayer)"   → "pause_overlay"
      "## Scene: Gameplay"                     → "gameplay"

    Note: standard CamelCase only. Consecutive caps like `APIClient`
    would produce `a_p_i_client` (wrong) — fix at point-of-use if a
    project actually uses such names. Test fixtures do not.
    """
    name = heading[len("## Scene:"):].strip()
    name = name.split(" (", 1)[0]  # drop trailing parenthetical
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _add_scene_reference_rows(assets: Path, scenes: Path, tag: str) -> None:
    """For each `## Scene: <Name>` in SCENES.md, append a `MISSING` row
    for `references/scene_<snake_case>.png` to the Asset Table in
    ASSETS.md. Skip scenes whose row already exists by File Path match.
    Each new row carries `tag` in the Tag column. Assumes
    _add_tag_column_to_assets has already run (so the Asset Table is
    8-column).
    """
    scene_ids: list[str] = []
    for line in scenes.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Scene:"):
            scene_ids.append(_scene_id_from_heading(line))

    if not scene_ids:
        print("  [skip] SCENES.md has no `## Scene:` headings")
        return

    text = assets.read_text(encoding="utf-8")
    new_ids = [
        sid for sid in scene_ids
        if f"references/scene_{sid}.png" not in text
    ]
    if not new_ids:
        print("  [skip] ASSETS.md already has reference rows for every scene")
        return

    lines = text.splitlines(keepends=True)

    # Find the Asset Table — first table whose header has both `Tag` and
    # `Name` and `Type` columns. (3D Models has Format not Type; Audio
    # has both Type AND Duration; we want the simplest one.)
    table_start = None
    for i, line in enumerate(lines):
        if not _is_table_row(line.strip()):
            continue
        if i + 1 >= len(lines) or not _is_separator_row(lines[i + 1]):
            continue
        cells = _row_cells(line.strip())
        if cells == ["#", "Tag", "Name", "Type", "Size", "Generation Params", "File Path", "Status"]:
            table_start = i
            break

    if table_start is None:
        print("  [warn] could not locate Asset Table (8-col with Tag) in ASSETS.md")
        return

    # Walk forward to find end of data rows.
    table_end = len(lines)
    for j in range(table_start + 2, len(lines)):
        if not _is_table_row(lines[j].strip()):
            table_end = j
            break

    # Highest existing row number, ignoring `...` placeholder rows.
    max_row_num = 0
    for j in range(table_start + 2, table_end):
        cells = _row_cells(lines[j].strip())
        if cells and cells[0].isdigit():
            max_row_num = max(max_row_num, int(cells[0]))

    # Insert before any `| ... | ... | ... | ... |` placeholder row at
    # the bottom (so new real rows precede the cosmetic ellipsis).
    insert_at = table_end
    while insert_at > table_start + 2:
        prev = lines[insert_at - 1].strip()
        if not _is_table_row(prev):
            insert_at -= 1
            continue
        cells = _row_cells(prev)
        if all(c == "..." for c in cells if c):
            insert_at -= 1
            continue
        break

    new_rows = []
    for offset, sid in enumerate(new_ids, start=1):
        n = max_row_num + offset
        new_rows.append(
            f"| {n} | {tag} | scene_{sid} | reference | — | — | "
            f"references/scene_{sid}.png | MISSING |\n"
        )

    out = lines[:insert_at] + new_rows + lines[insert_at:]
    _atomic_write_text(assets, "".join(out))
    print(
        f"  [done] add {len(new_ids)} scene reference row(s) to ASSETS.md "
        f"({', '.join('scene_' + s for s in new_ids)})"
    )


# ── PLAN.md mechanic sections ─────────────────────────────────────

_TAG_MECHANICS_SECTION = """## Tag Mechanics

<!-- Mechanics this tag MUST deliver. Each gets a stable id `<Tag>-M<N>`
     so later tags can reference it as something they inherit. State the
     observable behavior — not how it'll be verified.

     Backfilled by tag-pipeline migration with no mechanics listed —
     re-run /gm-gdd subsequent-mode to populate from the existing GDD/
     PLAN, or fill in manually. -->

- [TODO-M1] TODO: fill in the first mechanic this tag delivers

"""


def _add_plan_mechanic_sections(plan: Path) -> None:
    """Inject `## Tag Mechanics` into PLAN.md if missing.

    Inherited Mechanics section is intentionally NOT injected here.
    INITIAL_TAG is hardcoded to "v0.1.0" in this migration; per
    templates/PLAN.md the Inherited Mechanics section is "Omit this
    entire section for the very first tag (v0.1.0)" — and v0.1.0 is the
    only tag this migration ever produces. If a future migration
    generalizes INITIAL_TAG to non-v0.1.0 starting tags, add the
    Inherited Mechanics injection at that point.
    """
    text = plan.read_text(encoding="utf-8")
    if "## Tag Mechanics" in text:
        print("  [skip] PLAN.md already has ## Tag Mechanics section")
        return

    lines = text.splitlines(keepends=True)
    insert_idx = _find_tag_mechanics_insert_index(lines)

    new_lines = lines[:insert_idx] + [_TAG_MECHANICS_SECTION] + lines[insert_idx:]
    _atomic_write_text(plan, "".join(new_lines))
    print("  [done] inject ## Tag Mechanics section into PLAN.md")


def _find_tag_mechanics_insert_index(lines: list[str]) -> int:
    """Where in PLAN.md to inject `## Tag Mechanics`.

    Per templates/PLAN.md the section sits between Game Description and
    Risk Tasks / Main Build. Strategy:
      - If there's a `## Game Description`, inject right before its
        next `## ` sibling (= end of Game Description block).
      - Else, inject before the first `## ` H2 we see.
      - Else, append at end.
    """
    in_game_description = False
    for i, line in enumerate(lines):
        if line.startswith("## Game Description"):
            in_game_description = True
            continue
        if in_game_description and line.startswith("## "):
            return i
    if in_game_description:
        return len(lines)
    for i, line in enumerate(lines):
        if line.startswith("## "):
            return i
    return len(lines)
