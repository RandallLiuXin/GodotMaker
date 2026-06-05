#!/usr/bin/env python3
"""Find user-provided asset candidates before AI generation.

The script is intentionally lightweight: it scans file suffixes under
``assets/`` and filters out paths already consumed by ASSETS.md or
assets/manifest.json. It does not inspect image/audio content.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
AUDIO_SUFFIXES = {".wav", ".ogg", ".mp3"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | AUDIO_SUFFIXES
DONE_STATUSES = {"provided", "generated", "n/a"}
UNFILLED_STATUSES = {"missing", "pending", "deferred"}
ASSET_PATH_RE = re.compile(r"assets[/\\][^\s|,;)]+", re.IGNORECASE)


def _normalize_project_path(path: str | Path) -> str:
    value = str(path).replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    return value


def _normalize_manifest_path(path: str) -> str | None:
    value = _normalize_project_path(path.strip().strip("`'\""))
    if not value:
        return None
    if value.startswith("assets/"):
        return value
    if "/" in value or "\\" in path:
        return f"assets/{value}"
    return None


def _kind_for_suffix(suffix: str) -> str:
    lower = suffix.lower()
    if lower in IMAGE_SUFFIXES:
        return "image"
    if lower in AUDIO_SUFFIXES:
        return "audio"
    return "unknown"


def _extract_asset_paths(text: str) -> set[str]:
    paths: set[str] = set()
    for match in ASSET_PATH_RE.findall(text):
        cleaned = match.strip().strip("`'\"")
        paths.add(_normalize_project_path(cleaned))
    return paths


def _assets_paths_by_status(assets_md: Path) -> tuple[set[str], dict[str, dict[str, str]]]:
    if not assets_md.exists():
        return set(), {}

    done_paths: set[str] = set()
    unfilled_paths: dict[str, dict[str, str]] = {}
    text = assets_md.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped:
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue

        status = cells[-1].strip().lower()
        row_paths = _extract_asset_paths(stripped)
        row_info = {
            "asset_id": cells[2] if len(cells) > 2 else "",
            "asset_type": cells[3] if len(cells) > 3 else "",
            "status": cells[-1],
        }
        if status in DONE_STATUSES:
            done_paths.update(row_paths)
        elif status in UNFILLED_STATUSES:
            for row_path in row_paths:
                unfilled_paths[row_path] = row_info

    return done_paths, unfilled_paths


def _collect_manifest_paths(value: Any) -> set[str]:
    paths: set[str] = set()
    if isinstance(value, str):
        paths.update(_extract_asset_paths(value))
    elif isinstance(value, list):
        for item in value:
            paths.update(_collect_manifest_paths(item))
    elif isinstance(value, dict):
        file_value = value.get("file")
        if isinstance(file_value, str):
            normalized = _normalize_manifest_path(file_value)
            if normalized is not None:
                paths.add(normalized)
        for key, item in value.items():
            if key == "file":
                continue
            paths.update(_collect_manifest_paths(item))
    return paths


def _manifest_paths(manifest_path: Path) -> tuple[set[str], list[str]]:
    if not manifest_path.exists():
        return set(), []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return set(), [f"Could not parse {manifest_path}: {exc}"]
    return _collect_manifest_paths(data), []


def find_user_asset_candidates(project_root: Path) -> dict[str, object]:
    project_root = project_root.resolve()
    assets_dir = project_root / "assets"
    assets_md = project_root / "ASSETS.md"
    manifest_path = assets_dir / "manifest.json"

    done_paths, unfilled_paths = _assets_paths_by_status(assets_md)
    manifest_paths, warnings = _manifest_paths(manifest_path)
    consumed_paths = done_paths | manifest_paths

    candidates: list[dict[str, object]] = []
    if assets_dir.exists():
        for path in sorted(assets_dir.rglob("*")):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_SUFFIXES:
                continue

            rel_path = _normalize_project_path(path.relative_to(project_root))
            if rel_path == "assets/manifest.json":
                continue
            if rel_path.startswith("assets/origin/"):
                continue
            if rel_path in consumed_paths:
                continue

            reason = "not in completed ASSETS.md rows or assets/manifest.json"
            candidate: dict[str, object] = {
                "path": rel_path,
                "kind_hint": _kind_for_suffix(suffix),
                "reason": reason,
                "match_kind": "unmatched",
            }
            if rel_path in unfilled_paths:
                reason = "matches an unfilled ASSETS.md path"
                row_info = unfilled_paths[rel_path]
                candidate.update({
                    "reason": reason,
                    "match_kind": "exact_path",
                    "matched_asset_id": row_info["asset_id"],
                    "matched_asset_type": row_info["asset_type"],
                    "matched_status": row_info["status"],
                })
            candidates.append(candidate)

    image_count = sum(1 for item in candidates if item["kind_hint"] == "image")
    audio_count = sum(1 for item in candidates if item["kind_hint"] == "audio")
    return {
        "ok": True,
        "assets_dir": "assets",
        "candidate_count": len(candidates),
        "image_candidate_count": image_count,
        "audio_candidate_count": audio_count,
        "needs_analyst": image_count > 0,
        "candidates": candidates,
        "consumed_paths": sorted(consumed_paths),
        "warnings": warnings,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Find unconsumed user-provided asset candidates under assets/"
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root containing ASSETS.md and assets/",
    )
    args = parser.parse_args()

    result = find_user_asset_candidates(Path(args.project_root))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
