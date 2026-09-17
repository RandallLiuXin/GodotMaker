"""Replace the legacy project STYLE.md with the DESIGN.md visual contract.

One-shot migration, no compatibility layer:

- only `STYLE.md`  -> its text is preserved byte-for-byte inside a new
  `DESIGN.md` (`Legacy Style Notes`), the nine image-style dimensions stay
  unspecified, and the obsolete `STYLE.md` is removed only after the embedded
  block has been extracted back out and compared against the original;
- only `DESIGN.md` -> no-op;
- both            -> `DESIGN.md` is the sole active authority. Nothing is
  merged or copied from `STYLE.md`; it is removed once `DESIGN.md` is confirmed
  readable and non-empty;
- neither         -> nothing to migrate (`/gm-gdd` writes `DESIGN.md`).
"""
import os
from pathlib import Path

LEGACY_HEADING = "## Legacy Style Notes"

# Suffix used by `_atomic_write_verbatim`. A crash can leave one behind; it is
# never mistaken for a project document because the name is not `DESIGN.md`.
TMP_SUFFIX = ".migrate-tmp"

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

FENCE_INFO = "markdown"

# A file with no final newline cannot sit inside a fenced block unchanged — the
# closing fence needs a line of its own. That is the only edit ever made to the
# legacy text, and it is stated in the document so the original stays derivable.
NO_FINAL_NEWLINE_NOTE = (
    "The original file ended without a final newline; exactly one was added so "
    "the block below can close. Nothing else was changed."
)


def _read_verbatim(path: Path) -> str:
    """Read text with no universal-newline translation.

    `Path.read_text` rewrites CRLF to LF, which would silently normalise a
    legacy file we promised to keep byte-for-byte.
    """
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _atomic_write_verbatim(path: Path, text: str) -> None:
    """Write through a same-directory temp file + `os.replace`, translating nothing.

    `newline=""` because `write_text` would emit CRLF on Windows and undo the
    byte-for-byte promise made about the quoted legacy text.

    Atomic because a direct write that dies partway (full disk, crash) would
    leave a truncated `DESIGN.md` next to a still-present `STYLE.md` while the
    migration is still pending. The retry would then take that partial file as
    the active contract and delete the only copy of the legacy text.
    `os.replace` is atomic on POSIX and Windows, so `DESIGN.md` is either
    absent or complete.
    """
    tmp = path.with_name(path.name + TMP_SUFFIX)
    try:
        with tmp.open("w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _embed_legacy(legacy: str) -> tuple[str, bool]:
    """Return (text to place inside the fence, whether a newline was added)."""
    if legacy.endswith(("\n", "\r")):
        return legacy, False
    return legacy + "\n", True


def _extract_legacy(design_text: str) -> str | None:
    """Pull the quoted legacy block back out of Legacy Style Notes.

    This is the migration's own proof of losslessness: what goes in must come
    back out before the source file is deleted.
    """
    lines = design_text.splitlines(keepends=True)
    for start, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if not stripped.endswith(FENCE_INFO):
            continue
        fence = stripped[:-len(FENCE_INFO)]
        if len(fence) < 3 or set(fence) != {"`"}:
            continue
        for end in range(start + 1, len(lines)):
            if lines[end].rstrip("\r\n") == fence:
                return "".join(lines[start + 1:end])
        return None
    return None


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
    embedded, added_newline = _embed_legacy(legacy)
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
    ]
    if added_newline:
        lines += [NO_FINAL_NEWLINE_NOTE, ""]

    # Everything above is ours, so it is joined with LF. The legacy block is
    # spliced in as-is — its own line endings, blank lines and trailing
    # newlines must survive, so it is never passed through the join.
    head = "\n".join(lines) + "\n"
    return f"{head}{fence}{FENCE_INFO}\n{embedded}{fence}\n"


def _ensure_toc_entry(target: Path) -> None:
    """Point TOC.md at DESIGN.md and drop any stale STYLE.md entry."""
    toc = target / "TOC.md"
    if not toc.exists():
        return

    entry = ("- `DESIGN.md` — Project visual contract: visual identity, nine "
             "image-style dimensions, UI visual language, Do / Don't "
             "(produced by `/gm-gdd`)")

    original = _read_verbatim(toc)
    # Rewriting an entry must not also rewrite the file's line endings.
    eol = "\r\n" if "\r\n" in original else "\n"

    kept: list[str] = []
    replaced = False
    for line in original.splitlines():
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

    text = eol.join(kept).rstrip("\r\n") + eol
    if text != original:
        _atomic_write_verbatim(toc, text)
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

    legacy = _read_verbatim(style_path)
    content = _build_design_md(target, legacy)
    _atomic_write_verbatim(design_path, content)

    written = _read_verbatim(design_path)
    if written != content:
        raise RuntimeError(
            "DESIGN.md did not read back as written; STYLE.md left in place."
        )

    # Deleting the only copy of the legacy text is the irreversible step, so
    # prove the round trip first rather than trusting the construction.
    expected, _added_newline = _embed_legacy(legacy)
    if _extract_legacy(written) != expected:
        raise RuntimeError(
            "Legacy Style Notes did not round-trip to the original STYLE.md "
            "text; STYLE.md left in place."
        )

    style_path.unlink()
    print("Migrated STYLE.md into DESIGN.md (Legacy Style Notes) and removed STYLE.md")
    _ensure_toc_entry(target)
