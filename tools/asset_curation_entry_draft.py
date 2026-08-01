#!/usr/bin/env python3
"""Build a v1 stable-entry draft from a selected curation candidate.

``asset_curation_select.py`` marks one candidate ``selected`` in a curation
report and finalizes it into a runtime path. This tool turns that decision into a
v1 stable-entry draft ready for ``asset_stable_entry.py --write``.

The curation checks stay mechanical here rather than being restated in prose for
a producer to honour by hand: the named candidate must exist, be unambiguous, and
actually be ``selected``; the report's selected/rejected counts must be coherent;
and the finalized path must sit inside the asset's stable output directory.

The default draft stops at ``processing_status: source_ready`` and carries no
``godot_artifact``. The dedicated static FX mode binds the selected image to its
native ``Texture2D`` import and writes a compiled entry; the FX Skill owns the
L0-L4 validation loop and promotes it to ready before worker handoff.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asset_stable_entry import (
    PRODUCTION_FAMILIES,
    REFERENCE_FAMILIES,
    REFERENCE_LAYOUTS,
    SCHEMA_VERSION,
    SOURCE_LAYOUT_TYPES,
    StableEntryError,
    check_output_path,
    validate_entry,
)
from asset_animated_bundle_contract_check import (
    AnimatedBundleContractError,
    check_bundle_request,
)

SHARED_ROOT = Path(__file__).resolve().parents[1] / "skills" / "assets" / "_shared"
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))
from asset_compiler import CompileRequest, CompilerError, build_default_registry  # noqa: E402

DRAFT_STATUS = "source_ready"


class CurationEntryDraftError(Exception):
    """Raised when a curation stable-entry draft cannot be built."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced as a tool error
        raise CurationEntryDraftError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(data, dict):
        raise CurationEntryDraftError(f"{label} must be a JSON object: {path}")
    return data


def _string(data: dict[str, Any], field: str, label: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CurationEntryDraftError(f"{label}.{field} must be a non-empty string")
    return value


def _count(data: dict[str, Any], field: str, *, minimum: int) -> int:
    value = data.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise CurationEntryDraftError(
            f"report.{field} must be an integer >= {minimum}"
        )
    return value


def _project_relative(raw_path: str, project_root: Path) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(Path(project_root).resolve()).as_posix()
        except ValueError as exc:
            raise CurationEntryDraftError(
                f"path resolves outside the project root: {raw_path}"
            ) from exc
    return path.as_posix()


def _selected_candidate(report: dict[str, Any], selector: str) -> dict[str, Any]:
    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        raise CurationEntryDraftError("report.candidates must be a list")
    matches = [
        item
        for item in candidates
        if isinstance(item, dict)
        and (item.get("candidate_id") == selector or item.get("name") == selector)
    ]
    if not matches:
        raise CurationEntryDraftError(f"Candidate not found: {selector}")
    if len(matches) > 1:
        raise CurationEntryDraftError(f"Candidate selector is ambiguous: {selector}")
    candidate = matches[0]
    if candidate.get("state") != "selected":
        raise CurationEntryDraftError(f"Candidate is not selected: {selector}")
    return candidate


def build_curation_entry_draft(
    report_path: Path,
    *,
    candidate: str,
    asset_id: str,
    tag: str,
    production_family: str,
    project_root: Path,
    source_layout: str = "single",
) -> dict[str, Any]:
    """Validate a curation selection and return the draft stable entry."""
    if not asset_id.strip():
        raise CurationEntryDraftError("--asset-id must be a non-empty string")
    if not tag.strip():
        raise CurationEntryDraftError("--tag must be a non-empty string")
    if production_family not in PRODUCTION_FAMILIES:
        raise CurationEntryDraftError(
            f"production_family is not allowed: {production_family}"
        )
    if production_family in REFERENCE_FAMILIES:
        raise CurationEntryDraftError(
            f"production_family {production_family} is reference-only and is not curated"
        )
    if source_layout not in SOURCE_LAYOUT_TYPES or source_layout in REFERENCE_LAYOUTS:
        raise CurationEntryDraftError(
            f"source_layout is not allowed for a curated asset: {source_layout}"
        )

    report = _load_object(report_path, "report")
    selected = _selected_candidate(report, candidate)

    # A report claiming a selection must also account for what it rejected;
    # incoherent counts mean the curation record was hand-edited.
    _count(report, "selected_count", minimum=1)
    _count(report, "rejected_count", minimum=0)
    _string(report, "strategy", "report")

    final_relative = _project_relative(
        _string(selected, "final_path", "candidate"), project_root
    )
    try:
        final_res = check_output_path(
            f"res://{final_relative}",
            production_family=production_family,
            asset_id=asset_id,
            label="candidate.final_path",
        )
    except StableEntryError as exc:
        raise CurationEntryDraftError(str(exc)) from exc

    entry = {
        "version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": production_family,
        "source_layout": {"type": source_layout, "path": final_res},
        "processing_status": DRAFT_STATUS,
    }
    try:
        validate_entry(entry, project_root=Path(project_root))
    except StableEntryError as exc:
        raise CurationEntryDraftError(str(exc)) from exc
    return entry


def write_curation_entry_draft(
    report_path: Path,
    *,
    candidate: str,
    asset_id: str,
    tag: str,
    production_family: str,
    project_root: Path,
    source_layout: str,
    out: Path,
) -> dict[str, Any]:
    entry = build_curation_entry_draft(
        report_path,
        candidate=candidate,
        asset_id=asset_id,
        tag=tag,
        production_family=production_family,
        project_root=project_root,
        source_layout=source_layout,
    )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "draft": str(out),
        "asset_id": asset_id,
        "tag": tag,
        "candidate": candidate,
    }


def _load_fx_static_request(path: Path) -> dict[str, Any]:
    request = _load_object(path, "request")
    try:
        check_bundle_request(request)
    except AnimatedBundleContractError as exc:
        raise CurationEntryDraftError(str(exc)) from exc
    if request["asset_type"] != "fx-bundle" or request["spec"]["mode"] != "static":
        raise CurationEntryDraftError("--request must describe a static fx-bundle")
    return request


def build_fx_static_entry_draft(
    report_path: Path,
    *,
    candidate: str,
    request_path: Path,
    asset_id: str,
    tag: str,
    project_root: Path,
) -> dict[str, Any]:
    """Build the selected static FX image as a compiled Texture2D stable entry."""
    request = _load_fx_static_request(request_path)
    if request["asset_id"] != asset_id:
        raise CurationEntryDraftError("--asset-id must match request.asset_id")
    source_ready = build_curation_entry_draft(
        report_path,
        candidate=candidate,
        asset_id=asset_id,
        tag=tag,
        production_family="fx-bundle",
        project_root=project_root,
        source_layout="single",
    )
    source_path = source_ready["source_layout"]["path"]
    expected = f"res://assets/generated/fx-bundle/{asset_id}/{asset_id}.png"
    if source_path != expected:
        raise CurationEntryDraftError("static FX selected path must match its stable PNG path")
    entry = {
        **source_ready,
        "godot_artifact": {"type": "Texture2D", "path": source_path},
        "processing_status": "compiled",
    }
    try:
        validate_entry(entry, project_root=Path(project_root), check_files=True)
        build_default_registry().compile(
            CompileRequest(
                "fx-bundle",
                asset_id,
                "single",
                source_path,
                "Texture2D",
                source_path,
                Path(project_root),
            )
        )
    except (CompilerError, StableEntryError) as exc:
        raise CurationEntryDraftError(str(exc)) from exc
    return entry


def write_fx_static_entry_draft(
    report_path: Path,
    *,
    candidate: str,
    request_path: Path,
    asset_id: str,
    tag: str,
    project_root: Path,
    out: Path,
) -> dict[str, Any]:
    entry = build_fx_static_entry_draft(
        report_path,
        candidate=candidate,
        request_path=request_path,
        asset_id=asset_id,
        tag=tag,
        project_root=project_root,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "draft": str(out),
        "asset_id": asset_id,
        "tag": tag,
        "path": entry["godot_artifact"]["path"],
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a v1 stable-entry draft from a selected curation candidate"
    )
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--production-family", required=True)
    parser.add_argument("--source-layout", default="single")
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        if args.request:
            if args.production_family != "fx-bundle":
                raise CurationEntryDraftError(
                    "--request static mode supports fx-bundle only"
                )
            result = write_fx_static_entry_draft(
                args.report,
                candidate=args.candidate,
                request_path=args.request,
                asset_id=args.asset_id,
                tag=args.tag,
                project_root=args.project_root,
                out=args.out,
            )
        else:
            result = write_curation_entry_draft(
                args.report,
                candidate=args.candidate,
                asset_id=args.asset_id,
                tag=args.tag,
                production_family=args.production_family,
                project_root=args.project_root,
                source_layout=args.source_layout,
                out=args.out,
            )
    except CurationEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
