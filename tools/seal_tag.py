#!/usr/bin/env python3
"""Mechanical helpers for `/gm-finalize`'s Steps 4 / 7 / 5+8.

`/gm-finalize` mixes LLM-judgment work (Step 3 doc consistency check, Step 5
CHANGELOG prose, Step 8 final_report writeup) with mechanical fs/git ops
(archive working docs and evidence, truncate stage.jsonl, delete
metrics_current.jsonl, slice git log between tags). The mechanical ops show up in `2026-05-12` AAR as
20+ tool calls with ~4 path-syntax fallbacks (Windows-absolute paths under
Bash, PowerShell not in allowedTools). This helper collapses them into
deterministic subcommands so the SKILL can stay short and the agent
stays in LLM-judgment work.

Subcommands:
    archive <Tag>   Step 4 — copy per-tag docs, the memory/ subtree and
                    evidence into docs/tags/<Tag>/ and write a provisional
                    manifest (`sealed: false`)
    index <Tag>     Step 6b — generate docs/tags/<Tag>/SUMMARY.md, the tag
                    README, the sealed manifest and the parent
                    docs/tags/README.md index. This is what seals the tag.
    backfill        Retrofit README / SUMMARY / manifest onto tag archives
                    that were sealed by an older finalize. Never runs as
                    part of a normal finalize.
    reindex         Regenerate docs/tags/README.md from the sealed archives
                    on disk. Repair path when a seal landed but the index
                    refresh after it did not.
    reset           Step 7 — truncate stage.jsonl + delete metrics_current.jsonl
    bundle <Tag>    Step 5+8 — emit JSON bundle (roadmap entry, git log slice,
                    plan tag mechanics, test counts, previous tag) to stdout

Usage:
    python tools/seal_tag.py archive v0.1.0
    python tools/seal_tag.py index v0.1.0
    python tools/seal_tag.py backfill --all
    python tools/seal_tag.py reindex
    python tools/seal_tag.py reset
    python tools/seal_tag.py bundle v0.1.0

All subcommands accept `--project-path` (default cwd) to support running
from outside the project root (used by the test suite).

Immutability: once `index` has written `sealed: true` into a tag's
manifest, `archive` and `index` refuse to touch that archive again. A
partially archived tag (manifest absent or `sealed: false`) is resumable
— re-running `archive` is the documented recovery path. Resealing a
sealed tag requires an explicit `--force`.

Seal ordering, and why it is this way. Two invariants are in tension:

  (A) docs/tags/README.md must never list a tag that is not sealed — it is
      the retrieval entry point, and an unsealed archive is still an
      overwritable partial snapshot.
  (B) a failed run must never leave a tag sealed-but-incomplete, because
      `archive` / `index` refuse to touch a sealed tag (exit 3).

The order is: SUMMARY.md and the tag README, then ONE atomic manifest
write committing `sealed: true`, then the parent index — which is pure
derived state, rendered only from manifests already on disk.

  - fail before or at the seal commit → tag unsealed, parent index
    untouched. (A) holds, (B) holds, `index` re-runs cleanly.
  - fail at the parent index → the tag is sealed and correct; the index
    merely omits it. (A) still holds — an omission misleads no one toward
    a partial snapshot. `reindex` repairs it without touching any archive.

Every generated file goes through `_atomic_write_text`, so an interrupted
write never truncates the previous version.

Exit codes:
    0   succeeded
    1   runtime failure — missing project state (.godotmaker/ absent) OR
        an fs failure mid-operation (copy / write / read / unlink raises
        OSError, JSON output raises UnicodeError, etc.)
    2   archive source files missing, unresolvable archived memory links,
        or bad CLI usage
    3   the tag archive is already sealed — refused to overwrite it
        (pass --force to reseal deliberately)
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote


# (source path relative to project root, destination filename under
# docs/tags/<Tag>/). Mirrors gm-finalize SKILL Step 4's archive table —
# update both if either side changes.
ARCHIVE_MAP = [
    ("GDD.md",                          "GDD-snapshot.md"),
    ("PLAN.md",                         "PLAN.md"),
    ("STRUCTURE.md",                    "STRUCTURE.md"),
    ("STYLE.md",                        "STYLE.md"),
    ("SCENES.md",                       "SCENES.md"),
    ("MEMORY.md",                       "MEMORY.md"),
    (".godotmaker/evaluation.json",     "evaluation-final.json"),
]

EVIDENCE_DIR = "evidence"
E2E_DIR = "e2e"
SCREENSHOTS_DIR = "e2e/screenshots"
MEMORY_DIR = "memory"
MANIFEST_RELPATH = f"{EVIDENCE_DIR}/manifest.json"

MANIFEST_SCHEMA_VERSION = 1

# Suffix used by `_atomic_write_text`. A crash can leave one behind, and it
# must never be mistaken for archived content.
TMP_SUFFIX = ".seal-tmp"

# Temporary files, caches and editor droppings never enter the archive, so
# the manifest can list everything that is actually there.
JUNK_PATTERNS = (
    "__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".mypy_cache",
    ".DS_Store", "Thumbs.db", "*.tmp", "*.bak", "*.log", "*.swp",
)

# Archive-relative filename → (role shown in the tag README, source at seal time).
ARCHIVE_FILE_ROLES = {
    "README.md":             ("Navigation page for this archive", "generated by `tools/seal_tag.py index`"),
    "SUMMARY.md":            ("Bounded retrieval summary", "generated by `tools/seal_tag.py index`"),
    "CHANGELOG.md":          ("Changelog entry for this tag", "written by `/gm-finalize`"),
    "GDD-snapshot.md":       ("Game design document as it stood when the tag shipped", "`GDD.md`"),
    "PLAN.md":               ("Playable units and the task table for this tag", "`PLAN.md`"),
    "STRUCTURE.md":          ("ECS component/system layout for this tag", "`STRUCTURE.md`"),
    "STYLE.md":              ("Visual style contract for this tag", "`STYLE.md`"),
    "SCENES.md":             ("Scene inventory for this tag", "`SCENES.md`"),
    "MEMORY.md":             ("Cross-tag notebook frozen at seal time", "`MEMORY.md`"),
    "evaluation-final.json": ("Final evaluator verdict for this tag", "`.godotmaker/evaluation.json`"),
}

INDEX_FILES = ("README.md", "SUMMARY.md")

# SUMMARY.md is a retrieval entry point, not a second source of truth —
# these bounds keep it cheap to read for both humans and agents.
SUMMARY_MAX_LINES = 160
SUMMARY_MAX_LIST_ITEMS = 12
SUMMARY_MAX_ITEM_CHARS = 200


def _resolve_project_path(arg: str | None) -> Path:
    return Path(arg).resolve() if arg else Path.cwd()


def _ignore_junk(*extra: str):
    return shutil.ignore_patterns(*JUNK_PATTERNS, *extra)


def _copy_tree_optional(src: Path, dst: Path, ignore=None) -> int:
    if not src.is_dir():
        return 0
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)
    return _count_files(dst, "*")


# ---------------------------------------------------------------- provenance


def _generator_version(project_path: Path) -> str:
    """Framework version stamped into the target project at publish time."""
    for candidate in (project_path / ".godotmaker" / "version", project_path / "VERSION"):
        try:
            text = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text.splitlines()[0].strip()
    return "unknown"


def _rev_parse(project_path: Path, rev: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "rev-parse", rev],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip() or None


def _source_revision(project_path: Path) -> str | None:
    """Repository HEAD at seal time (the commit the archive was taken from).

    `/gm-finalize` archives before it commits, so this is the pre-seal
    commit — the revision whose working tree the snapshot reflects.
    """
    return _rev_parse(project_path, "HEAD")


def _archived_tag_revision(project_path: Path, tag: str) -> str | None:
    """Revision a historical tag was sealed at, for `backfill`.

    Backfill runs long after the fact, so HEAD says nothing about the
    archive it is indexing. `git tag <Tag>` does: `/gm-finalize` points it
    at the seal commit. Untagged archives get a null revision rather than
    a fabricated one.
    """
    return _rev_parse(project_path, f"refs/tags/{tag}^{{commit}}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ------------------------------------------------------------------ manifest


def _categorize(rel_posix: str) -> str:
    if rel_posix in INDEX_FILES:
        return "index"
    if rel_posix.startswith(f"{MEMORY_DIR}/"):
        return "memory"
    if rel_posix.startswith(f"{EVIDENCE_DIR}/screenshots/"):
        return "screenshot"
    if rel_posix.startswith(f"{EVIDENCE_DIR}/e2e/"):
        return "e2e"
    if rel_posix.startswith(f"{EVIDENCE_DIR}/"):
        return "evidence"
    return "document"


def _scan_archive_files(dest_dir: Path) -> list[dict]:
    """Every file in the archive except the manifest itself, sorted by path.

    Paths are archive-relative and POSIX-separated so a manifest written on
    Windows compares byte-for-byte with one written on Linux.
    """
    entries: list[dict] = []
    for path in sorted(dest_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(dest_dir).as_posix()
        if rel == MANIFEST_RELPATH or rel.endswith(TMP_SUFFIX):
            continue
        entries.append({
            "path": rel,
            "category": _categorize(rel),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        })
    entries.sort(key=lambda e: e["path"])
    return entries


def _build_manifest(
    project_path: Path,
    tag: str,
    dest_dir: Path,
    *,
    sealed: bool,
    backfilled: bool = False,
    warnings: list[str] | None = None,
    link_warnings: list[str] | None = None,
    source_revision: str | None = None,
) -> dict:
    files = _scan_archive_files(dest_dir)
    by_category: dict[str, int] = {}
    for entry in files:
        by_category[entry["category"]] = by_category.get(entry["category"], 0) + 1
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generator": "tools/seal_tag.py",
        "generator_version": _generator_version(project_path),
        "tag": tag,
        "sealed": sealed,
        "stage": "sealed" if sealed else "archived",
        "backfilled": backfilled,
        "source_revision": source_revision if backfilled else _source_revision(project_path),
        "archive_root": f"docs/tags/{tag}/",
        # Back-compat keys — `bundle` and `final_report.json` have read these
        # three since v0.5.0. Keep them even though `files` now supersedes them.
        "archive_path": f"docs/tags/{tag}/{EVIDENCE_DIR}/",
        "e2e_files": by_category.get("e2e", 0),
        "screenshots": by_category.get("screenshot", 0),
        "memory_files": by_category.get("memory", 0),
        "warnings": list(warnings or []),
        "link_warnings": list(link_warnings or []),
        "files": files,
    }


def _atomic_write_text(path: Path, text: str) -> None:
    """Write `text` to `path` through a same-directory temp file + os.replace.

    `os.replace` is atomic on POSIX and Windows, so a crash or a full disk
    mid-write leaves the previous file intact rather than a truncated one —
    which matters most for the manifest, since a half-written manifest is
    what decides whether a tag counts as sealed.

    Newlines are pinned to LF: these files are hashed into the manifest, and
    the platform default would make identical inputs hash differently on
    Windows and Linux.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + TMP_SUFFIX)
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _write_manifest(dest_dir: Path, manifest: dict) -> None:
    """The seal commit — a single atomic write, always the caller's last step."""
    _atomic_write_text(
        dest_dir / MANIFEST_RELPATH,
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
    )


def _read_manifest(dest_dir: Path) -> dict | None:
    path = dest_dir / MANIFEST_RELPATH
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _is_sealed(dest_dir: Path) -> bool:
    manifest = _read_manifest(dest_dir)
    return bool(manifest and manifest.get("sealed") is True)


# --------------------------------------------------------------- link checks


_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*([^)]+?)\s*\)")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE_RE = re.compile(r"^```.*?^```", re.DOTALL | re.MULTILINE)
_WINDOWS_ABS_RE = re.compile(r"^[a-zA-Z]:[\\/]")


def _local_markdown_links(text: str) -> list[str]:
    """Relative link targets in `text`, ignoring comments and code fences.

    Template MEMORY.md ships its example `memory/*.md` entries inside an
    HTML comment; treating those as real links would block every first
    finalize, so commented and fenced regions are stripped first.
    """
    text = _HTML_COMMENT_RE.sub("", text)
    text = _FENCE_RE.sub("", text)
    targets: list[str] = []
    for match in _LINK_RE.finditer(text):
        target = match.group(1).strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        else:
            # `[x](path "title")` — the title is not part of the target.
            target = target.split()[0] if target.split() else ""
        if not target or target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = unquote(target.split("#", 1)[0])
        if target:
            targets.append(target)
    return targets


def _check_memory_links(dest_dir: Path) -> tuple[list[str], list[str]]:
    """Validate the archived MEMORY.md's local links against the archive.

    Returns `(errors, warnings)`:

    - error — the link escapes the archive boundary, is absolute, or points
      into `memory/` without a matching archived file. These block a seal:
      a frozen index whose entries 404 is worse than no index.
    - warning — the link points at a project path that is deliberately not
      archived (`src/player.gd`, `assets/…`). MEMORY.md legitimately cites
      source files, so these are recorded, not fatal.
    """
    errors: list[str] = []
    warnings: list[str] = []
    memory_md = dest_dir / "MEMORY.md"
    if not memory_md.is_file():
        return errors, warnings
    try:
        text = memory_md.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [f"MEMORY.md unreadable in the archive: {exc}"], warnings

    root = dest_dir.resolve()
    for target in _local_markdown_links(text):
        if target.startswith("/") or _WINDOWS_ABS_RE.match(target):
            errors.append(f"MEMORY.md links to an absolute path `{target}` - archives must stay relocatable")
            continue
        resolved = (dest_dir / target).resolve()
        try:
            rel = resolved.relative_to(root)
        except ValueError:
            errors.append(f"MEMORY.md link `{target}` escapes the archive boundary")
            continue
        if resolved.exists():
            continue
        if rel.parts and rel.parts[0] == MEMORY_DIR:
            errors.append(f"MEMORY.md links to `{target}`, which is missing from the archive")
        else:
            warnings.append(f"MEMORY.md links to `{target}`, which is outside the archive")
    return errors, warnings


# ------------------------------------------------------------------- archive


def _archive_memory_tree(project_path: Path, dest_dir: Path) -> tuple[int, list[str]]:
    """Freeze `memory/` next to the archived MEMORY.md.

    Without this the archived index links to files that only exist in the
    live project, so a sealed tag's MEMORY.md rots the moment the root
    `memory/` moves on.
    """
    try:
        count = _copy_tree_optional(
            project_path / MEMORY_DIR,
            dest_dir / MEMORY_DIR,
            ignore=_ignore_junk(),
        )
    except OSError as exc:
        return 0, [f"memory subtree archive skipped: {exc}"]
    return count, []


def _archive_evidence(project_path: Path, dest_dir: Path) -> list[str]:
    warnings: list[str] = []
    evidence_dir = dest_dir / EVIDENCE_DIR
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        _copy_tree_optional(
            project_path / E2E_DIR,
            evidence_dir / "e2e",
            ignore=_ignore_junk("screenshots"),
        )
    except OSError as exc:
        warnings.append(f"e2e archive skipped: {exc}")
    try:
        _copy_tree_optional(
            project_path / SCREENSHOTS_DIR,
            evidence_dir / "screenshots",
            ignore=_ignore_junk(),
        )
    except OSError as exc:
        warnings.append(f"screenshot archive skipped: {exc}")
    return warnings


def cmd_archive(project_path: Path, tag: str, force: bool = False) -> int:
    missing = [src for src, _ in ARCHIVE_MAP if not (project_path / src).exists()]
    if missing:
        print(
            f"error: missing archive source(s) under {project_path}: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    dest_dir = project_path / "docs" / "tags" / tag
    if _is_sealed(dest_dir) and not force:
        print(
            f"error: docs/tags/{tag}/ is already sealed - refusing to overwrite it. "
            f"Re-run with --force only if you deliberately want to reseal this tag.",
            file=sys.stderr,
        )
        return 3

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        for src_rel, dst_name in ARCHIVE_MAP:
            shutil.copy2(project_path / src_rel, dest_dir / dst_name)
        memory_files, warnings = _archive_memory_tree(project_path, dest_dir)
        warnings += _archive_evidence(project_path, dest_dir)
    except OSError as exc:
        # Mid-copy fs failure leaves a partial archive; surface that to the
        # caller instead of leaking a traceback.
        print(
            f"error: archive failed at {dest_dir} ({exc.__class__.__name__}: {exc}). "
            f"The directory may contain a partial archive - re-run after fixing the underlying fs issue.",
            file=sys.stderr,
        )
        return 1

    link_errors, link_warnings = _check_memory_links(dest_dir)

    try:
        manifest = _build_manifest(
            project_path, tag, dest_dir,
            sealed=False, warnings=warnings, link_warnings=link_warnings,
        )
        _write_manifest(dest_dir, manifest)
    except OSError as exc:
        print(f"error: manifest write failed ({exc})", file=sys.stderr)
        return 1

    if link_errors:
        print(
            f"error: docs/tags/{tag}/MEMORY.md has unresolvable archive links:\n"
            + "\n".join(f"  - {e}" for e in link_errors)
            + "\nThe archive is left in place but NOT sealed. Fix the root MEMORY.md "
              "(or restore the missing memory/ files) and re-run `archive`.",
            file=sys.stderr,
        )
        return 2

    print(
        f"archived {len(ARCHIVE_MAP)} documents + {memory_files} memory file(s) to docs/tags/{tag}/ "
        f"(evidence: {manifest['e2e_files']} e2e files, {manifest['screenshots']} screenshots). "
        f"Run `seal_tag.py index {tag}` after CHANGELOG.md exists to seal the archive."
    )
    return 0


# --------------------------------------------------------------- changelog IO


def _parse_changelog(path: Path) -> dict:
    """Pull the structured bits out of an archived per-tag CHANGELOG.md.

    Section names are matched by keyword, not verbatim, because the
    CHANGELOG body is LLM-written prose against a template rather than a
    machine-generated file.
    """
    parsed = {"released": None, "theme": None, "mechanics": [], "changed": [], "limitations": []}
    if not path.is_file():
        return parsed
    text = path.read_text(encoding="utf-8", errors="replace")

    for field, key in (("Released", "released"), ("Theme", "theme")):
        match = re.search(rf"(?m)^\*\*{field}:\*\*\s*(.+?)\s*$", text)
        if match:
            parsed[key] = match.group(1).strip()

    current: str | None = None
    for line in text.splitlines():
        heading = re.match(r"^##+\s+(.*?)\s*$", line)
        if heading:
            name = heading.group(1).lower()
            if "mechanic" in name:
                current = "mechanics"
            elif "limitation" in name:
                current = "limitations"
            elif any(word in name for word in ("system", "scene", "asset", "refactor")):
                current = "changed"
            else:
                current = None
            continue
        if current is None:
            continue
        bullet = re.match(r"^\s*[-*]\s+(.*?)\s*$", line)
        if bullet and bullet.group(1):
            parsed[current].append(bullet.group(1))
    return parsed


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# -------------------------------------------------------------- doc rendering


def _clip(items: list[str], limit: int = SUMMARY_MAX_LIST_ITEMS) -> list[str]:
    clipped = [
        item if len(item) <= SUMMARY_MAX_ITEM_CHARS else item[: SUMMARY_MAX_ITEM_CHARS - 1] + "…"
        for item in items[:limit]
    ]
    if len(items) > limit:
        clipped.append(f"… and {len(items) - limit} more — see `CHANGELOG.md`")
    return clipped


def _bullets(items: list[str], empty: str) -> list[str]:
    return [f"- {item}" for item in _clip(items)] or [f"- {empty}"]


def _render_summary(project_path: Path, tag: str, dest_dir: Path, manifest: dict) -> str:
    """Render SUMMARY.md from confirmed, canonical inputs only.

    Inputs: the archived CHANGELOG.md, evaluation-final.json, PLAN.md, the
    archive manifest and — only when it belongs to this tag —
    `.godotmaker/final_report.json`. Worker traces, exploration notes and
    unverified MEMORY learnings are deliberately NOT read: SUMMARY is a
    retrieval index over confirmed deliverables, not a second notebook.
    """
    changelog = _parse_changelog(dest_dir / "CHANGELOG.md")
    evaluation = _read_json(dest_dir / "evaluation-final.json") or {}
    final_report = _read_json(project_path / ".godotmaker" / "final_report.json") or {}
    # final_report.json is per-tag overwritten — only trust it for THIS tag.
    if final_report.get("tag") != tag:
        final_report = {}

    mechanics = changelog["mechanics"] or _extract_plan_tag_mechanics(dest_dir / "PLAN.md", tag)
    limitations = changelog["limitations"] or [
        str(issue) for issue in evaluation.get("minor_issues", []) if str(issue).strip()
    ]

    verdict = str(evaluation.get("result") or "not recorded")
    counts = final_report.get("summary", {}).get("test_count", {}) if final_report else {}
    test_bits = [f"{label}: {counts[key]}" for key, label in (
        ("unit", "unit"), ("e2e_tag", "e2e (this tag)"), ("e2e_regression", "e2e (regression)"),
    ) if isinstance(counts.get(key), int)]

    lines: list[str] = [
        f"# Summary — {tag}",
        "",
        "<!-- Generated by `tools/seal_tag.py index`. Retrieval entry point only:",
        "     every fact below is restated from the canonical documents linked",
        "     under \"Canonical documents\", which remain the source of truth. -->",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Tag | `{tag}` |",
        f"| Released | {changelog['released'] or 'not recorded'} |",
        f"| Source revision | `{manifest.get('source_revision') or 'unknown'}` |",
        f"| Theme | {changelog['theme'] or 'not recorded'} |",
        "",
        "## Canonical documents",
        "",
        "- [CHANGELOG.md](CHANGELOG.md) — what shipped in this tag",
        "- [PLAN.md](PLAN.md) — playable units and the task table",
        "- [GDD-snapshot.md](GDD-snapshot.md) — design as of this tag",
        "- [STRUCTURE.md](STRUCTURE.md) · [SCENES.md](SCENES.md) · [STYLE.md](STYLE.md) — architecture, scenes, style",
        "- [MEMORY.md](MEMORY.md) + [memory/](memory/) — frozen notebook and sub-system files",
        "- [evaluation-final.json](evaluation-final.json) — evaluator verdict",
        "- [evidence/manifest.json](evidence/manifest.json) — full archive inventory with hashes",
        "",
        "## Verification",
        "",
        f"- Evaluation verdict: **{verdict}**",
        f"- Tests: {' · '.join(test_bits) if test_bits else 'not recorded'}",
        f"- Evidence: {manifest.get('e2e_files', 0)} e2e file(s), "
        f"{manifest.get('screenshots', 0)} screenshot(s)",
        "",
        "## Delivered mechanics",
        "",
        *_bullets(mechanics, "none recorded"),
        "",
        "## Systems, scenes and assets changed",
        "",
        *_bullets(changelog["changed"], "none recorded"),
        "",
        "## Known limitations",
        "",
        *_bullets(limitations, "none recorded"),
        "",
    ]

    if len(lines) > SUMMARY_MAX_LINES:
        lines = lines[: SUMMARY_MAX_LINES - 2] + [
            "",
            "_Summary truncated — read the canonical documents linked above._",
        ]
    return "\n".join(lines) + "\n"


def _render_tag_readme(tag: str, manifest: dict, link_warnings: list[str]) -> str:
    # The index files are written in the same pass as this README, so they
    # count as present even though the manifest snapshot predates them —
    # otherwise a first seal and a `--force` reseal would render differently.
    present = {entry["path"] for entry in manifest.get("files", [])} | set(INDEX_FILES)
    memory_count = manifest.get("memory_files", 0)
    # Completeness is about what the archive holds. A MEMORY.md citation to a
    # live source file (`src/player.gd`) is a note, not a gap.
    complete = not manifest.get("warnings") and all(
        name in present for name in ARCHIVE_FILE_ROLES
    )

    lines = [
        f"# {tag} — sealed archive",
        "",
        f"Immutable snapshot of the working documents and evidence for `{tag}`, "
        "written by `/gm-finalize`. Nothing in this directory is a live document — "
        "edit the root working docs instead.",
        "",
        "- **Start here:** [SUMMARY.md](SUMMARY.md)",
        f"- **Source revision:** `{manifest.get('source_revision') or 'unknown'}`",
        f"- **Sealed by:** `{manifest.get('generator')}` v{manifest.get('generator_version')}",
        f"- **Completeness:** {'complete' if complete else 'partial — see notes below'}",
        "- **Inventory:** [evidence/manifest.json](evidence/manifest.json) — "
        "every archived file with its size and sha256",
        "",
        "## Files",
        "",
        "| Path | Role | Source at seal time |",
        "| --- | --- | --- |",
    ]
    for name, (role, source) in ARCHIVE_FILE_ROLES.items():
        if name not in present:
            continue
        lines.append(f"| [{name}]({name}) | {role} | {source} |")
    if memory_count:
        lines.append(
            f"| [memory/](memory/) | Sub-system memory files linked from MEMORY.md "
            f"({memory_count} file(s)) | `memory/` |"
        )
    if manifest.get("e2e_files") or manifest.get("screenshots"):
        lines.append(
            f"| [evidence/](evidence/) | E2E tests and screenshots captured at seal time "
            f"({manifest.get('e2e_files', 0)} e2e, {manifest.get('screenshots', 0)} screenshots) "
            f"| `e2e/` |"
        )

    lines += [
        "",
        "## Reading order",
        "",
        "1. `SUMMARY.md` — one-screen answer to \"what shipped in this tag\".",
        "2. `CHANGELOG.md` / `PLAN.md` — the delivered mechanics and their task trail.",
        "3. `STRUCTURE.md`, `SCENES.md`, `STYLE.md` — how it was built, if you need to touch it again.",
        "4. `MEMORY.md` + `memory/` — the gotchas that were true at seal time.",
        "5. `evidence/` — the proof, only when a claim above is in doubt.",
        "",
        "## Immutability",
        "",
        "This archive is sealed: `evidence/manifest.json` carries `\"sealed\": true`, "
        "and `tools/seal_tag.py archive|index` refuse to rewrite it. Resealing is a "
        "deliberate `--force` action, and retrofitting index files onto older archives "
        "goes through `tools/seal_tag.py backfill`, which never rewrites canonical documents.",
    ]
    if manifest.get("warnings") or link_warnings:
        lines += ["", "## Notes", ""]
        lines += [f"- {note}" for note in manifest.get("warnings", [])]
        lines += [f"- {note}" for note in link_warnings]
    return "\n".join(lines) + "\n"


def _version_key(tag: str) -> tuple:
    """Sort key that orders v0.2.0 before v0.10.0 and keeps junk names last."""
    numbers = [int(part) for part in re.findall(r"\d+", tag)]
    return (0, numbers, tag) if numbers else (1, [], tag)


def _sealed_tag_dirs(tags_root: Path) -> list[Path]:
    """Sealed tag directories, version-ordered.

    Sealed means the manifest on disk says so. The parent index is rendered
    purely from that, never from a seal this run intends to commit later —
    otherwise a failed seal commit would leave the index advertising a tag
    that is still an overwritable partial snapshot.
    """
    if not tags_root.is_dir():
        return []
    sealed = [child for child in tags_root.iterdir() if child.is_dir() and _is_sealed(child)]
    return sorted(sealed, key=lambda p: _version_key(p.name))


def _render_parent_readme(tags_root: Path) -> str:
    lines = [
        "# Tag archives",
        "",
        "One directory per sealed tag. Each is an immutable snapshot of the "
        "working documents, memory and evidence as they stood when that tag "
        "shipped — the live documents live at the project root.",
        "",
        "| Tag | Released | Theme | Source revision | Summary |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows = 0
    for tag_dir in _sealed_tag_dirs(tags_root):
        manifest = _read_manifest(tag_dir) or {}
        changelog = _parse_changelog(tag_dir / "CHANGELOG.md")
        revision = manifest.get("source_revision")
        lines.append(
            f"| [{tag_dir.name}]({tag_dir.name}/) "
            f"| {changelog['released'] or '—'} "
            f"| {changelog['theme'] or '—'} "
            f"| `{revision[:10] if revision else 'unknown'}` "
            f"| [SUMMARY]({tag_dir.name}/SUMMARY.md) |"
        )
        rows += 1
    if not rows:
        lines.append("| _(no sealed tag yet)_ | — | — | — | — |")

    lines += [
        "",
        "## How to read an archive",
        "",
        "1. Pick the tag from the table and open its `SUMMARY.md` — bounded, "
        "regenerable, and enough to decide whether you need more.",
        "2. Open that tag's `README.md` for the file-by-file map.",
        "3. Only then open the canonical documents (`PLAN.md`, `STRUCTURE.md`, …) "
        "or `evidence/`. They are complete but expensive to read.",
        "",
        "## Rules",
        "",
        "- Only tags whose `evidence/manifest.json` says `\"sealed\": true` are listed here. "
        "An in-progress finalize is invisible until it seals.",
        "- Archived documents are immutable. Corrections go into the live root documents "
        "and ship with the next tag.",
        "- This index is generated — `tools/seal_tag.py index <Tag>` rewrites it on every "
        "seal, and `tools/seal_tag.py backfill --all` rebuilds it from the archives on disk.",
    ]
    return "\n".join(lines) + "\n"


def _write_parent_readme(tags_root: Path) -> None:
    _atomic_write_text(tags_root / "README.md", _render_parent_readme(tags_root))


# --------------------------------------------------------------------- index


def _write_index_files(
    project_path: Path,
    tag: str,
    dest_dir: Path,
    *,
    backfilled: bool,
    link_warnings: list[str],
    carried_warnings: list[str],
    source_revision: str | None = None,
) -> dict:
    """Write SUMMARY.md and README.md; return the manifest that would seal them.

    The manifest is deliberately NOT written here. `"sealed": true` is the
    single marker every other command keys off, so committing it is the
    caller's last action, after every other artifact — including the parent
    index — is on disk. Anything that fails before that leaves the tag
    unsealed and re-runnable instead of sealed-but-incomplete.

    The returned manifest is built after the two files are written, so it
    hashes the index files it describes.
    """
    def build() -> dict:
        return _build_manifest(
            project_path, tag, dest_dir,
            sealed=True, backfilled=backfilled,
            warnings=carried_warnings, link_warnings=link_warnings,
            source_revision=source_revision,
        )

    provisional = build()
    _atomic_write_text(
        dest_dir / "SUMMARY.md",
        _render_summary(project_path, tag, dest_dir, provisional),
    )
    _atomic_write_text(
        dest_dir / "README.md",
        _render_tag_readme(tag, provisional, link_warnings),
    )
    return build()


def cmd_index(project_path: Path, tag: str, force: bool = False) -> int:
    dest_dir = project_path / "docs" / "tags" / tag
    required = [dst for _, dst in ARCHIVE_MAP] + ["CHANGELOG.md"]
    missing = [name for name in required if not (dest_dir / name).is_file()]
    if missing:
        print(
            f"error: docs/tags/{tag}/ is not ready to seal - missing: "
            + ", ".join(missing)
            + ". Run `seal_tag.py archive` and write CHANGELOG.md first.",
            file=sys.stderr,
        )
        return 2

    if _is_sealed(dest_dir) and not force:
        print(
            f"error: docs/tags/{tag}/ is already sealed - refusing to rewrite it. "
            f"Pass --force to reseal deliberately.",
            file=sys.stderr,
        )
        return 3

    link_errors, link_warnings = _check_memory_links(dest_dir)
    if link_errors:
        print(
            f"error: docs/tags/{tag}/MEMORY.md has unresolvable archive links:\n"
            + "\n".join(f"  - {e}" for e in link_errors)
            + "\nSeal aborted — the archive stays unsealed until the links resolve.",
            file=sys.stderr,
        )
        return 2

    previous = _read_manifest(dest_dir) or {}
    try:
        manifest = _write_index_files(
            project_path, tag, dest_dir,
            backfilled=False,
            link_warnings=link_warnings,
            carried_warnings=list(previous.get("warnings", [])),
        )
        _write_manifest(dest_dir, manifest)
    except OSError as exc:
        print(
            f"error: index failed ({exc.__class__.__name__}: {exc}). "
            f"docs/tags/{tag}/ is left UNSEALED and docs/tags/README.md was not "
            f"touched - fix the underlying fs issue and re-run `seal_tag.py index {tag}`.",
            file=sys.stderr,
        )
        return 1

    # The parent index is derived state, rendered only from manifests already
    # committed on disk. Writing it after the seal is what keeps it from ever
    # advertising a tag whose seal did not land.
    try:
        _write_parent_readme(dest_dir.parent)
    except OSError as exc:
        print(
            f"error: docs/tags/{tag}/ sealed, but refreshing docs/tags/README.md failed "
            f"({exc.__class__.__name__}: {exc}). The index still lists only sealed tags, "
            f"so nothing is misadvertised - it is just missing {tag}. "
            f"Fix the fs issue and run `seal_tag.py reindex` (do NOT re-run `index`; "
            f"the tag is already sealed and it will exit 3).",
            file=sys.stderr,
        )
        return 1

    print(
        f"sealed docs/tags/{tag}/: {len(manifest['files'])} file(s) in manifest, "
        f"SUMMARY.md + README.md written, docs/tags/README.md refreshed."
    )
    return 0


# ------------------------------------------------------------------ backfill


def _looks_like_archive(path: Path) -> bool:
    return path.is_dir() and (path / "PLAN.md").is_file()


def cmd_backfill(
    project_path: Path, tag: str | None, all_tags: bool, force: bool = False
) -> int:
    """Retrofit README / SUMMARY / manifest onto archives sealed by an older
    finalize.

    Deliberately separate from `archive` / `index`: normal finalize must
    never rewrite history. Canonical documents are read-only here — the
    command verifies their bytes are unchanged before it returns, and it
    does not copy today's `memory/` into a historical tag (that would inject
    present-day content into a past snapshot). Missing memory links become
    manifest warnings and a `partial` completeness note instead.

    Archives that already carry a sealed manifest are skipped unless
    `--force`: re-indexing them would replace their recorded seal revision
    with whatever this run happens to resolve.
    """
    tags_root = project_path / "docs" / "tags"
    if all_tags:
        targets = sorted(
            (child for child in tags_root.iterdir() if _looks_like_archive(child)),
            key=lambda p: _version_key(p.name),
        ) if tags_root.is_dir() else []
    else:
        dest_dir = tags_root / tag
        if not _looks_like_archive(dest_dir):
            print(f"error: docs/tags/{tag}/ is not a tag archive", file=sys.stderr)
            return 2
        targets = [dest_dir]

    if not targets:
        print("backfill: no tag archives found under docs/tags/")
        return 0

    canonical = [dst for _, dst in ARCHIVE_MAP] + ["CHANGELOG.md"]
    sealed_now: list[str] = []
    try:
        for dest_dir in targets:
            if _is_sealed(dest_dir) and not force:
                print(
                    f"skipped docs/tags/{dest_dir.name}/ (already sealed; "
                    f"pass --force to re-index it)"
                )
                continue
            before = {
                name: _sha256(dest_dir / name)
                for name in canonical if (dest_dir / name).is_file()
            }
            link_errors, link_warnings = _check_memory_links(dest_dir)
            gaps = [n for n in canonical if n not in before]
            carried = (
                [f"missing canonical document(s): {', '.join(gaps)}"] if gaps else []
            )
            # A legacy archive has no memory/ subtree, so MEMORY.md's index
            # links cannot resolve. Backfill records that instead of blocking:
            # copying today's memory/ into a historical tag would rewrite it.
            carried += link_errors
            manifest = _write_index_files(
                project_path, dest_dir.name, dest_dir,
                backfilled=True,
                link_warnings=link_warnings,
                carried_warnings=carried,
                source_revision=_archived_tag_revision(project_path, dest_dir.name),
            )
            after = {
                name: _sha256(dest_dir / name)
                for name in canonical if (dest_dir / name).is_file()
            }
            if before != after:
                changed = sorted(set(before) | set(after))
                print(
                    f"error: backfill modified canonical document(s) in "
                    f"docs/tags/{dest_dir.name}/: {', '.join(changed)}",
                    file=sys.stderr,
                )
                return 1
            # Same ordering as `index`: seal this target before moving on, and
            # leave the derived parent index for after the loop. A failure here
            # leaves this tag unsealed and the index untouched, so the index
            # never lists a tag whose seal did not land.
            _write_manifest(dest_dir, manifest)
            sealed_now.append(dest_dir.name)
            print(
                f"backfilled docs/tags/{dest_dir.name}/ "
                f"({len(manifest['files'])} file(s) in manifest)"
            )
    except OSError as exc:
        print(
            f"error: backfill failed ({exc.__class__.__name__}: {exc}). "
            f"{len(sealed_now)} archive(s) sealed before the failure; the rest stay "
            f"unsealed and docs/tags/README.md was not touched. Re-run backfill after "
            f"fixing the underlying fs issue - already-sealed archives are skipped.",
            file=sys.stderr,
        )
        return 1

    try:
        _write_parent_readme(tags_root)
    except OSError as exc:
        print(
            f"error: archives sealed, but refreshing docs/tags/README.md failed "
            f"({exc.__class__.__name__}: {exc}). The index still lists only sealed tags. "
            f"Fix the fs issue and run `seal_tag.py reindex`.",
            file=sys.stderr,
        )
        return 1

    print(f"backfill complete: docs/tags/README.md lists {len(_sealed_tag_dirs(tags_root))} sealed tag(s).")
    return 0


# ------------------------------------------------------------------- reindex


def cmd_reindex(project_path: Path) -> int:
    """Regenerate `docs/tags/README.md` from the sealed archives on disk.

    The parent index is pure derived state, so rebuilding it is always safe
    and never touches an archive. This is the repair path for the one failure
    `index` / `backfill` cannot finish themselves: the seal committed, but the
    index refresh that follows it did not. Re-running `index` there would only
    exit 3, because the tag is legitimately sealed already.
    """
    tags_root = project_path / "docs" / "tags"
    if not tags_root.is_dir():
        print(f"error: {tags_root} does not exist", file=sys.stderr)
        return 2
    try:
        _write_parent_readme(tags_root)
    except OSError as exc:
        print(
            f"error: reindex failed ({exc.__class__.__name__}: {exc})",
            file=sys.stderr,
        )
        return 1
    sealed = _sealed_tag_dirs(tags_root)
    print(
        f"reindexed docs/tags/README.md: {len(sealed)} sealed tag(s)"
        + (f" ({', '.join(p.name for p in sealed)})" if sealed else "")
    )
    return 0


# --------------------------------------------------------------------- reset


def cmd_reset(project_path: Path) -> int:
    gm_dir = project_path / ".godotmaker"
    if not gm_dir.is_dir():
        print(f"error: {gm_dir} does not exist", file=sys.stderr)
        return 1

    stage = gm_dir / "stage.jsonl"
    metrics_current = gm_dir / "metrics_current.jsonl"

    try:
        stage.write_text("", encoding="utf-8")
        metrics_current.unlink(missing_ok=True)
    except OSError as exc:
        print(
            f"error: reset failed ({exc.__class__.__name__}: {exc})",
            file=sys.stderr,
        )
        return 1

    print("reset: stage.jsonl truncated, metrics_current.jsonl deleted if present")
    return 0


# -------------------------------------------------------------------- bundle


def _extract_roadmap_entry(roadmap_path: Path, tag: str) -> dict | None:
    """Return {'heading': str, 'body': str} for the given tag, or None.

    Recognizes any markdown heading that mentions the tag (e.g. `## v0.1.0`,
    `### v0.1.0 — Foundation`, `## Tag v0.1.0`). Body stops at the next
    heading of the same or higher level.
    """
    if not roadmap_path.exists():
        return None
    text = roadmap_path.read_text(encoding="utf-8")
    pattern = rf"(?m)^(#+)[^\n]*\b{re.escape(tag)}\b[^\n]*$"
    match = re.search(pattern, text)
    if not match:
        return None
    level = len(match.group(1))
    heading_line = match.group(0)
    start = match.end()
    # Body ends at the next heading at level <= current.
    end_pattern = rf"(?m)^#{{1,{level}}}\s"
    end_match = re.search(end_pattern, text[start:])
    body_end = start + end_match.start() if end_match else len(text)
    body = text[start:body_end].strip()
    return {"heading": heading_line.strip(), "body": body}


def _extract_plan_tag_mechanics(plan_path: Path, tag: str) -> list[str]:
    """Find all `[<Tag>-Mn]` style mechanic IDs in PLAN.md."""
    if not plan_path.exists():
        return []
    text = plan_path.read_text(encoding="utf-8")
    pattern = rf"\[({re.escape(tag)}-M\d+)\]"
    seen: list[str] = []
    for m in re.finditer(pattern, text):
        mid = m.group(1)
        if mid not in seen:
            seen.append(mid)
    return seen


def _list_tags(project_path: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "tag", "--sort=v:refname"],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [t.strip() for t in result.stdout.splitlines() if t.strip()]


def _resolve_tag_anchors(
    project_path: Path, tag: str
) -> tuple[str | None, str]:
    """Return `(previous_tag, upper_rev)` for the changelog slice.

    When `tag` already exists in git (retry-finalize case), cap the upper
    rev at `tag` so commits beyond the sealed tag don't leak into the
    rerun's log. Otherwise the upper rev is HEAD.
    """
    tags = _list_tags(project_path)
    if tag in tags:
        idx = tags.index(tag)
        return (tags[idx - 1] if idx > 0 else None), tag
    if tags:
        return tags[-1], "HEAD"
    return None, "HEAD"


def _git_log_since(project_path: Path, previous_tag: str | None, upper: str = "HEAD") -> str:
    rev_range = f"{previous_tag}..{upper}" if previous_tag else upper
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "log", "--oneline", "--no-decorate", rev_range],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return result.stdout.strip()


def _count_files(directory: Path, pattern: str) -> int:
    if not directory.is_dir():
        return 0
    return sum(1 for path in directory.rglob(pattern) if path.is_file())


def _count_unit_tests(project_path: Path) -> int:
    return _count_files(project_path / "test", "*.gd")


def _evidence_summary(project_path: Path, tag: str) -> dict:
    """Evidence block for the bundle — from the archive manifest when sealed.

    Only the four legacy keys are forwarded; `files` would bloat the bundle
    that `/gm-finalize` reads inline, and the manifest itself is linked from
    the archive README for anyone who needs the full inventory.
    """
    manifest = _read_manifest(project_path / "docs" / "tags" / tag)
    if manifest:
        return {
            key: manifest[key]
            for key in ("archive_path", "e2e_files", "screenshots", "warnings")
            if key in manifest
        }
    return {
        "archive_path": f"docs/tags/{tag}/{EVIDENCE_DIR}/",
        "e2e_files": _count_files(project_path / E2E_DIR, "*"),
        "screenshots": _count_files(project_path / SCREENSHOTS_DIR, "*"),
    }


def cmd_bundle(project_path: Path, tag: str) -> int:
    try:
        previous_tag, upper = _resolve_tag_anchors(project_path, tag)
        bundle = {
            "tag": tag,
            "previous_tag": previous_tag,
            "roadmap_entry": _extract_roadmap_entry(project_path / "ROADMAP.md", tag),
            "plan_tag_mechanics": _extract_plan_tag_mechanics(project_path / "PLAN.md", tag),
            "git_log_since_previous_tag": _git_log_since(project_path, previous_tag, upper),
            # File counts only — final_report schema's `e2e_tag` vs `e2e_regression`
            # split is LLM judgment (which test files belong to this tag), so bundle
            # provides the total and SKILL Step 8 narrates the split.
            "test_count": {
                "unit": _count_unit_tests(project_path),
                "e2e": _count_files(project_path / "e2e", "test_*.py"),
            },
            "evidence": _evidence_summary(project_path, tag),
        }
        # Force UTF-8 on stdout regardless of platform locale. Python text
        # mode on Windows defaults to cp936/GBK, which mangles em-dash and
        # other chars common in ROADMAP headings — sending bytes directly
        # to stdout.buffer sidesteps the encoding entirely.
        payload = json.dumps(bundle, indent=2, ensure_ascii=False) + "\n"
        sys.stdout.buffer.write(payload.encode("utf-8"))
    except (OSError, UnicodeError) as exc:
        # ROADMAP.md / PLAN.md read or stdout write blew up — surface a
        # CLI exit-code instead of leaking a traceback so /gm-finalize can
        # halt cleanly.
        print(
            f"error: bundle failed ({exc.__class__.__name__}: {exc})",
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="gm-finalize mechanical helpers (archive / index / backfill / reindex / reset / bundle)",
    )
    parser.add_argument(
        "--project-path",
        default=None,
        help="project root (default: cwd)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    archive = sub.add_parser("archive")
    archive.add_argument("tag")
    archive.add_argument("--force", action="store_true",
                         help="overwrite an already-sealed archive")

    index = sub.add_parser("index")
    index.add_argument("tag")
    index.add_argument("--force", action="store_true",
                       help="reseal an already-sealed archive")

    backfill = sub.add_parser("backfill")
    backfill.add_argument("tag", nargs="?", default=None)
    backfill.add_argument("--all", action="store_true",
                          help="backfill every archive under docs/tags/")
    backfill.add_argument("--force", action="store_true",
                          help="re-index archives that already carry a sealed manifest")

    sub.add_parser("reindex")
    sub.add_parser("reset")
    sub.add_parser("bundle").add_argument("tag")

    args = parser.parse_args(argv)
    project_path = _resolve_project_path(args.project_path)

    if args.cmd == "archive":
        return cmd_archive(project_path, args.tag, args.force)
    if args.cmd == "index":
        return cmd_index(project_path, args.tag, args.force)
    if args.cmd == "backfill":
        if bool(args.tag) == bool(args.all):
            print("error: backfill takes exactly one of <Tag> or --all", file=sys.stderr)
            return 2
        return cmd_backfill(project_path, args.tag, args.all, args.force)
    if args.cmd == "reindex":
        return cmd_reindex(project_path)
    if args.cmd == "reset":
        return cmd_reset(project_path)
    if args.cmd == "bundle":
        return cmd_bundle(project_path, args.tag)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
