#!/usr/bin/env python3
"""Select a curation candidate and finalize it into a runtime asset path."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_image_finalize import ImageFinalizeError, finalize_image_asset


class CurationSelectError(Exception):
    """Raised when a curation candidate cannot be selected."""


def _load_report(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CurationSelectError(f"Invalid curation report: {path}") from exc
    if not isinstance(data, dict):
        raise CurationSelectError(f"Curation report must be an object: {path}")
    if data.get("version") != 1:
        raise CurationSelectError(f"Curation report version must be 1: {path}")
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise CurationSelectError("Curation report candidates must be a list")
    return data


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(path.parent),
        suffix=".json",
        mode="w",
        encoding="utf-8",
    ) as handle:
        tmp_path = Path(handle.name)
        json.dump(data, handle, indent=2)
        handle.write("\n")
    try:
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _candidate_matches(candidate: dict[str, Any], selector: str) -> bool:
    return candidate.get("candidate_id") == selector or candidate.get("name") == selector


def _resolve_project_path(project_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _find_candidate(report: dict[str, Any], selector: str) -> dict[str, Any]:
    matches = [
        item
        for item in report["candidates"]
        if isinstance(item, dict) and _candidate_matches(item, selector)
    ]
    if not matches:
        raise CurationSelectError(f"Candidate not found: {selector}")
    if len(matches) > 1:
        raise CurationSelectError(f"Candidate selector is ambiguous: {selector}")
    candidate = matches[0]
    path = candidate.get("path")
    if not isinstance(path, str) or not path.strip():
        raise CurationSelectError(f"Candidate has no path: {selector}")
    return candidate


def _selected_count(report: dict[str, Any]) -> int:
    return sum(
        1
        for item in report.get("candidates", [])
        if isinstance(item, dict) and item.get("state") == "selected"
    )


def select_candidate(
    report_path: Path,
    selector: str,
    final_path: Path,
    *,
    asset_id: str | None = None,
    resize: str | None = None,
    project_root: Path | None = None,
) -> dict[str, object]:
    """Finalize one candidate and mark it selected in the curation report."""
    project_root = Path.cwd() if project_root is None else Path(project_root)
    report_path = Path(report_path)
    report_file = _resolve_project_path(project_root, report_path)
    report = _load_report(report_file)
    candidate = _find_candidate(report, selector)
    source_path = _resolve_project_path(project_root, Path(str(candidate["path"])))
    if not source_path.exists():
        raise CurationSelectError(f"Candidate image not found: {source_path}")

    final_path = Path(final_path)
    final_file = _resolve_project_path(project_root, final_path)
    label = asset_id or str(candidate.get("name") or candidate.get("candidate_id") or "")
    try:
        finalize = finalize_image_asset(
            source_path,
            final_file,
            resize=resize,
            label=label or None,
        )
    except ImageFinalizeError as exc:
        raise CurationSelectError(str(exc)) from exc

    candidate["state"] = "selected"
    candidate["final_path"] = str(final_path)
    candidate["finalize"] = finalize
    report["status"] = "selected"
    report["selected_count"] = _selected_count(report)
    report["rejected_count"] = len(report.get("rejected", []))
    selected_ids = [
        item.get("candidate_id")
        for item in report.get("candidates", [])
        if isinstance(item, dict) and item.get("state") == "selected"
    ]
    report["selected_candidate_ids"] = [item for item in selected_ids if isinstance(item, str)]
    _write_atomic(report_file, report)

    return {
        "ok": True,
        "report_path": str(report_path),
        "candidate_id": candidate.get("candidate_id"),
        "name": candidate.get("name"),
        "final_path": str(final_path),
        "selected_count": report["selected_count"],
        "finalize": finalize,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Select and finalize one curation candidate")
    parser.add_argument("--report", required=True, help="Curation report path")
    parser.add_argument("--candidate", required=True, help="Candidate id or name")
    parser.add_argument("--final-path", required=True, help="Runtime asset output path")
    parser.add_argument("--asset-id", default=None, help="Final asset id label")
    parser.add_argument("--resize", default=None, help="Optional WIDTHxHEIGHT resize")
    parser.add_argument("--project-root", default=".", help="Project root for relative paths")
    args = parser.parse_args()

    try:
        result = select_candidate(
            Path(args.report),
            args.candidate,
            Path(args.final_path),
            asset_id=args.asset_id,
            resize=args.resize,
            project_root=Path(args.project_root),
        )
    except CurationSelectError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
