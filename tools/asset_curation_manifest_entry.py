#!/usr/bin/env python3
"""Build a runtime manifest entry from a selected curation candidate."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


class CurationManifestEntryError(Exception):
    """Raised when a curation manifest entry cannot be built."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CurationManifestEntryError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(data, dict):
        raise CurationManifestEntryError(f"{label} must be a JSON object: {path}")
    return data


def _string(data: dict[str, Any], field: str, label: str, *, required: bool = True) -> str | None:
    value = data.get(field)
    if value is None:
        if required:
            raise CurationManifestEntryError(f"{label}.{field} is required")
        return None
    if not isinstance(value, str) or not value.strip():
        raise CurationManifestEntryError(f"{label}.{field} must be a non-empty string")
    return value


def _as_project_path(raw_path: str, project_root: Path) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        try:
            return path.relative_to(project_root).as_posix()
        except ValueError:
            return path.as_posix()
    return path.as_posix()


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


def _selected_candidate(report: dict[str, Any], selector: str) -> dict[str, Any]:
    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        raise CurationManifestEntryError("report.candidates must be a list")
    matches = [
        item
        for item in candidates
        if isinstance(item, dict)
        and (item.get("candidate_id") == selector or item.get("name") == selector)
    ]
    if not matches:
        raise CurationManifestEntryError(f"Candidate not found: {selector}")
    if len(matches) > 1:
        raise CurationManifestEntryError(f"Candidate selector is ambiguous: {selector}")
    candidate = matches[0]
    if candidate.get("state") != "selected":
        raise CurationManifestEntryError(f"Candidate is not selected: {selector}")
    return candidate


def build_curation_manifest_entry(
    report_path: Path,
    source_entry_path: Path,
    *,
    candidate: str,
    asset_id: str,
    project_root: Path,
    family: str | None = None,
    production_shape: str | None = None,
    runtime_role: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Build one runtime manifest entry from a selected curation candidate."""
    if not asset_id.strip():
        raise CurationManifestEntryError("--asset-id must be a non-empty string")

    report = _load_object(report_path, "report")
    source_entry = _load_object(source_entry_path, "source_entry")
    selected = _selected_candidate(report, candidate)

    final_path = _string(selected, "final_path", "candidate")
    source_asset_id = _string(source_entry, "asset_id", "source_entry")
    tag = _string(source_entry, "tag", "source_entry")
    source_path = _string(source_entry, "source_path", "source_entry")
    prompt_path = _string(source_entry, "prompt_path", "source_entry")
    clean_family = family or _string(source_entry, "family", "source_entry")
    clean_shape = production_shape or _string(source_entry, "production_shape", "source_entry")
    clean_runtime_role = runtime_role or str(selected.get("role") or "").strip()
    if not clean_runtime_role:
        clean_runtime_role = _string(source_entry, "runtime_role", "source_entry") or ""

    canonical_reference = source_entry.get("canonical_reference")
    if canonical_reference is not None and not isinstance(canonical_reference, str):
        raise CurationManifestEntryError("source_entry.canonical_reference must be a string or null")

    selected_count = report.get("selected_count")
    if not isinstance(selected_count, int) or selected_count <= 0:
        raise CurationManifestEntryError("report.selected_count must be positive")
    rejected_count = report.get("rejected_count")
    if not isinstance(rejected_count, int) or rejected_count < 0:
        raise CurationManifestEntryError("report.rejected_count must be a non-negative integer")

    entry = {
        "asset_id": asset_id,
        "tag": tag,
        "family": clean_family,
        "production_shape": clean_shape,
        "runtime_role": clean_runtime_role,
        "source_path": source_path,
        "final_path": _as_project_path(final_path or "", project_root),
        "derived_from": source_asset_id,
        "canonical_reference": canonical_reference,
        "prompt_path": prompt_path,
        "runtime_artifact": "single",
        "processing_status": "ready",
        "extraction_status": "processed",
        "curation": {
            "status": "selected",
            "strategy": _string(report, "strategy", "report"),
            "report_path": _as_project_path(str(report_path), project_root),
            "selected_count": selected_count,
            "rejected_count": rejected_count,
            "selected_candidate_ids": report.get("selected_candidate_ids", []),
        },
        "qc": {
            "curation_candidate": {
                "candidate_id": selected.get("candidate_id"),
                "name": selected.get("name"),
                "bbox": selected.get("bbox"),
                "crop_bbox": selected.get("crop_bbox"),
                "component_count": selected.get("component_count"),
                "selected_component_bbox": selected.get("selected_component_bbox"),
                "selected_component_area": selected.get("selected_component_area"),
            }
        },
        "preview_path": _as_project_path(final_path or "", project_root),
        "notes": notes,
    }
    return entry


def _main() -> int:
    parser = argparse.ArgumentParser(description="Build a manifest entry from a selected curation candidate")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--source-entry", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--family")
    parser.add_argument("--production-shape")
    parser.add_argument("--runtime-role")
    parser.add_argument("--notes", default="")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    try:
        entry = build_curation_manifest_entry(
            args.report,
            args.source_entry,
            candidate=args.candidate,
            asset_id=args.asset_id,
            project_root=args.project_root,
            family=args.family,
            production_shape=args.production_shape,
            runtime_role=args.runtime_role,
            notes=args.notes,
        )
        if args.out is not None:
            _write_atomic(args.out, entry)
    except CurationManifestEntryError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps({"ok": True, "entry": entry, "path": str(args.out) if args.out else None}))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
