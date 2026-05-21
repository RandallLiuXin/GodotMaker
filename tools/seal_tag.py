#!/usr/bin/env python3
"""Mechanical helpers for `/gm-finalize`'s Steps 4 / 7 / 5+8.

`/gm-finalize` mixes LLM-judgment work (Step 3 doc consistency check, Step 5
CHANGELOG prose, Step 8 final_report writeup) with mechanical fs/git ops
(archive working docs and evidence, truncate stage.jsonl, delete
metrics_current.jsonl, slice git log between tags). The mechanical ops show up in `2026-05-12` AAR as
20+ tool calls with ~4 path-syntax fallbacks (Windows-absolute paths under
Bash, PowerShell not in allowedTools). This helper collapses them into
three deterministic subcommands so the SKILL can stay short and the agent
stays in LLM-judgment work.

Subcommands:
    archive <Tag>   Step 4 — copy per-tag docs and evidence into docs/tags/<Tag>/
    reset           Step 7 — truncate stage.jsonl + delete metrics_current.jsonl
    bundle <Tag>    Step 5+8 — emit JSON bundle (roadmap entry, git log slice,
                    plan tag mechanics, test counts, previous tag) to stdout

Usage:
    python tools/seal_tag.py archive v0.1.0
    python tools/seal_tag.py reset
    python tools/seal_tag.py bundle v0.1.0

All subcommands accept `--project-path` (default cwd) to support running
from outside the project root (used by the test suite).

Exit codes:
    0   succeeded
    1   runtime failure — missing project state (.godotmaker/ absent) OR
        an fs failure mid-operation (copy / write / read / unlink raises
        OSError, JSON output raises UnicodeError, etc.)
    2   archive source files missing, or bad CLI usage
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


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


def _resolve_project_path(arg: str | None) -> Path:
    return Path(arg).resolve() if arg else Path.cwd()


def _copy_tree_optional(src: Path, dst: Path, ignore=None) -> int:
    if not src.is_dir():
        return 0
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)
    return _count_files(dst, "*")


def _archive_evidence(project_path: Path, dest_dir: Path) -> dict:
    summary = {
        "archive_path": f"docs/tags/{dest_dir.name}/evidence/",
        "e2e_files": 0,
        "screenshots": 0,
        "warnings": [],
    }
    evidence_dir = dest_dir / EVIDENCE_DIR
    try:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        summary["e2e_files"] = _copy_tree_optional(
            project_path / E2E_DIR,
            evidence_dir / "e2e",
            ignore=shutil.ignore_patterns("screenshots"),
        )
    except OSError as exc:
        summary["warnings"].append(f"e2e archive skipped: {exc}")
    try:
        summary["screenshots"] = _copy_tree_optional(
            project_path / SCREENSHOTS_DIR,
            evidence_dir / "screenshots",
        )
    except OSError as exc:
        summary["warnings"].append(f"screenshot archive skipped: {exc}")
    try:
        (evidence_dir / "manifest.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        summary["warnings"].append(f"evidence manifest skipped: {exc}")
        print(f"warning: evidence manifest skipped ({exc})", file=sys.stderr)
    return summary


def cmd_archive(project_path: Path, tag: str) -> int:
    missing = [src for src, _ in ARCHIVE_MAP if not (project_path / src).exists()]
    if missing:
        print(
            f"error: missing archive source(s) under {project_path}: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    dest_dir = project_path / "docs" / "tags" / tag
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        for src_rel, dst_name in ARCHIVE_MAP:
            shutil.copy2(project_path / src_rel, dest_dir / dst_name)
    except OSError as exc:
        # Mid-copy fs failure leaves a partial archive; surface that to the
        # caller instead of leaking a traceback.
        print(
            f"error: archive failed at {dest_dir} ({exc.__class__.__name__}: {exc}). "
            f"The directory may contain a partial archive — re-run after fixing the underlying fs issue.",
            file=sys.stderr,
        )
        return 1

    evidence = _archive_evidence(project_path, dest_dir)
    print(
        f"archived {len(ARCHIVE_MAP)} files to docs/tags/{tag}/ "
        f"(evidence: {evidence['e2e_files']} e2e files, "
        f"{evidence['screenshots']} screenshots)"
    )
    return 0


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
    archive = project_path / "docs" / "tags" / tag / EVIDENCE_DIR
    manifest = archive / "manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    return {
        "archive_path": f"docs/tags/{tag}/evidence/",
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
        description="gm-finalize mechanical helpers (archive / reset / bundle)",
    )
    parser.add_argument(
        "--project-path",
        default=None,
        help="project root (default: cwd)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("archive").add_argument("tag")
    sub.add_parser("reset")
    sub.add_parser("bundle").add_argument("tag")

    args = parser.parse_args(argv)
    project_path = _resolve_project_path(args.project_path)

    if args.cmd == "archive":
        return cmd_archive(project_path, args.tag)
    if args.cmd == "reset":
        return cmd_reset(project_path)
    if args.cmd == "bundle":
        return cmd_bundle(project_path, args.tag)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
