#!/usr/bin/env python3
"""Append a stage event to .godotmaker/stage.jsonl with a server-generated UTC timestamp.

Used in SKILL "When Done" sections instead of having the agent hand-write the
event JSON. Moving timestamp generation off the agent eliminates the corruption
pattern observed in 2026-05-09 e2e (every fixgap and late-iter evaluate event
had a fabricated `ts`; verify events written under simpler agent contexts were
honest) — the root cause was agents producing `ts` from model output under
context pressure rather than calling the system clock.

Usage:
    python tools/append_stage_event.py <role> [--key=value ...]

Examples:
    python tools/append_stage_event.py scaffold
    python tools/append_stage_event.py gdd --tag=v0.1.0
    python tools/append_stage_event.py accept --decision=accept
    python tools/append_stage_event.py rescue --conclusion=defect

Exit codes:
    0  appended successfully
    1  .godotmaker/ directory does not exist under project root
    2  bad CLI usage (malformed extra arg)
"""
import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return safe or "untagged"


def _count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for child in path.rglob("*") if child.is_file())


def _unique_dir(base: Path) -> Path:
    if not base.exists():
        return base
    for index in range(2, 1000):
        candidate = base.with_name(f"{base.name}-{index}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not allocate unique archive directory under {base.parent}")


def _archive_evaluation_run(
    project_path: Path,
    event: dict[str, object],
) -> None:
    if event.get("role") != "evaluate":
        return

    tag = str(event.get("tag") or "untagged")
    ts = str(event["ts"])
    run_id = f"{ts.replace(':', '').replace('-', '')}_{_safe_name(tag)}"
    archive_root = project_path / ".godotmaker" / "evaluation-runs"
    run_dir = _unique_dir(archive_root / run_id)
    run_dir.mkdir(parents=True, exist_ok=False)

    screenshots_src = project_path / "e2e" / "screenshots"
    screenshots_dst = run_dir / "screenshots"
    if screenshots_src.is_dir():
        shutil.copytree(screenshots_src, screenshots_dst)
    else:
        screenshots_dst.mkdir(parents=True, exist_ok=True)

    evaluation_src = project_path / ".godotmaker" / "evaluation.json"
    if evaluation_src.is_file():
        shutil.copy2(evaluation_src, run_dir / "evaluation.json")

    manifest = {
        "role": "evaluate",
        "tag": tag,
        "stage_event_ts": ts,
        "archive_path": str(run_dir.relative_to(project_path)).replace("\\", "/"),
        "screenshots_path": str(screenshots_dst.relative_to(project_path)).replace("\\", "/"),
        "screenshot_files": _count_files(screenshots_dst),
        "evaluation_json": (
            str((run_dir / "evaluation.json").relative_to(project_path)).replace("\\", "/")
            if (run_dir / "evaluation.json").is_file()
            else None
        ),
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    (archive_root / "latest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append a stage event to .godotmaker/stage.jsonl",
    )
    parser.add_argument(
        "role",
        help="role name (scaffold, gdd, asset, build, verify, evaluate, "
             "fixgap, accept, finalize, rescue)",
    )
    parser.add_argument(
        "--project-path",
        default=None,
        help="project root containing .godotmaker/ (default: cwd)",
    )
    args, extras = parser.parse_known_args(argv)

    # Field order matches the convention prior SKILLs hand-wrote: role, ts,
    # then any role-specific extras (tag, decision, conclusion). Python dicts
    # preserve insertion order so the JSON output is stable.
    event: dict[str, object] = {"role": args.role}

    # Server-generated UTC timestamp — the whole point of moving this off
    # the agent. Format matches what SKILLs previously asked the agent to
    # write: ISO-8601 seconds precision, trailing Z.
    event["ts"] = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    # --key=value extras land verbatim after ts. partition('=') keeps any
    # later '=' in the value (rare for stage events but harmless).
    for extra in extras:
        if not extra.startswith("--") or "=" not in extra:
            print(
                f"error: extra args must be in --key=value form (got: {extra!r})",
                file=sys.stderr,
            )
            return 2
        key, _, value = extra[2:].partition("=")
        if not key:
            print(f"error: empty key in {extra!r}", file=sys.stderr)
            return 2
        event[key] = value

    project_path = Path(args.project_path) if args.project_path else Path.cwd()
    stage_dir = project_path / ".godotmaker"
    stage_path = stage_dir / "stage.jsonl"

    if not stage_dir.is_dir():
        print(f"error: {stage_dir} does not exist", file=sys.stderr)
        return 1

    _archive_evaluation_run(project_path, event)

    # O_APPEND-mode write: the kernel guarantees the line lands at EOF
    # without a read-modify-write race. Also eliminates the "I'll regenerate
    # the ts from memory before re-writing the file" failure mode that the
    # prior SKILL prose ("read the existing file, append, write back")
    # implicitly invited.
    with open(stage_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
