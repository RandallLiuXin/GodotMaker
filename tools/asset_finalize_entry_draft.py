#!/usr/bin/env python3
"""Build a v1 stable-entry draft from an ``asset_image_finalize.py`` report.

Every production path that ends in one finalized image registers through this
tool: screen references, backgrounds and parallax plates, and single card or
portrait frames. Together with ``asset_action_entry_draft.py`` and
``asset_curation_entry_draft.py`` it means no production unit needs a
hand-written draft.

The checks that matter for a finalized image stay mechanical here:

- the finalize run succeeded and actually validated the aspect
  (``--require-aspect``), which every one of these units requires before the
  image is accepted;
- the report's own label identifies the same asset the draft is being built for,
  so a report from a different image cannot be pointed at this entry;
- the finalized file exists, and sits where its layout demands.

That last rule matters most for references. A ``reference`` layout is the single
case the schema lets out of the stable generated tree and out of the
``godot_artifact`` requirement, so an unconstrained reference path is a way to
register a scratch source — or a real runtime asset — while skipping compilation
entirely. Pinning references to ``references/`` and everything else to the stable
output directory closes that.

The layout is derived from the production family rather than passed in: the
schema already binds reference families and reference layouts to each other in
both directions, so a flag could only introduce a contradiction.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asset_stable_entry import (
    GENERATED_ROOT,
    PRODUCTION_FAMILIES,
    REFERENCE_FAMILIES,
    SCHEMA_VERSION,
    StableEntryError,
    check_output_path,
    validate_entry,
)

REFERENCES_ROOT = "references"
DRAFT_STATUS = "source_ready"


class FinalizeEntryDraftError(Exception):
    """Raised when a finalized-image stable-entry draft cannot be built."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced as a tool error
        raise FinalizeEntryDraftError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(data, dict):
        raise FinalizeEntryDraftError(f"{label} must be a JSON object: {path}")
    return data


def _string(data: dict[str, Any], field: str, label: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise FinalizeEntryDraftError(f"{label}.{field} must be a non-empty string")
    return value


def _number(data: dict[str, Any], field: str, label: str) -> float:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FinalizeEntryDraftError(f"{label}.{field} must be a number")
    return float(value)


def _project_relative(raw_path: str, project_root: Path) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(Path(project_root).resolve()).as_posix()
        except ValueError as exc:
            raise FinalizeEntryDraftError(
                f"path resolves outside the project root: {raw_path}"
            ) from exc
    return path.as_posix()


def _clean_relative(relative: str) -> str:
    if "\\" in relative:
        raise FinalizeEntryDraftError("finalized path must use forward slashes")
    if any(segment in ("", ".", "..") for segment in relative.split("/")):
        raise FinalizeEntryDraftError(
            "finalized path must have no empty, '.' or '..' segments"
        )
    return relative


def _reference_res_path(relative: str) -> str:
    _clean_relative(relative)
    if relative.startswith(f"{GENERATED_ROOT}/"):
        raise FinalizeEntryDraftError(
            f"a reference must not live under {GENERATED_ROOT}/; "
            "that tree is for compiled runtime assets"
        )
    if not relative.startswith(f"{REFERENCES_ROOT}/"):
        raise FinalizeEntryDraftError(
            f"reference path must be a file under {REFERENCES_ROOT}/"
        )
    return f"res://{relative}"


def _runtime_res_path(relative: str, *, production_family: str, asset_id: str) -> str:
    _clean_relative(relative)
    try:
        return check_output_path(
            f"res://{relative}",
            production_family=production_family,
            asset_id=asset_id,
            label="finalized path",
        )
    except StableEntryError as exc:
        raise FinalizeEntryDraftError(str(exc)) from exc


def build_finalize_entry_draft(
    finalize_report: Path,
    *,
    asset_id: str,
    tag: str,
    production_family: str,
    project_root: Path,
) -> dict[str, Any]:
    """Validate a finalize report and return the draft stable entry."""
    if not asset_id.strip():
        raise FinalizeEntryDraftError("--asset-id must be a non-empty string")
    if not tag.strip():
        raise FinalizeEntryDraftError("--tag must be a non-empty string")
    if production_family not in PRODUCTION_FAMILIES:
        raise FinalizeEntryDraftError(
            f"production_family is not allowed: {production_family}"
        )
    is_reference = production_family in REFERENCE_FAMILIES

    report = _load_object(finalize_report, "finalize report")
    if report.get("ok") is not True:
        raise FinalizeEntryDraftError("finalize report must report ok: true")

    # `--require-aspect` is what every finalize-driven production unit demands
    # before the image is accepted; its absence means the check never ran.
    if "required_aspect" not in report:
        raise FinalizeEntryDraftError(
            "finalize report has no required_aspect; rerun asset_image_finalize.py "
            "with --require-aspect"
        )
    delta = _number(report, "aspect_delta", "finalize report")
    tolerance = _number(report, "aspect_tolerance", "finalize report")
    if delta > tolerance:
        raise FinalizeEntryDraftError(
            f"finalize report aspect_delta {delta} exceeds tolerance {tolerance}"
        )

    # Cross-bind the report to this asset so a report for a different image
    # cannot be reused to register this one.
    reported_id = report.get("asset_id") or report.get("label")
    if not isinstance(reported_id, str) or not reported_id.strip():
        raise FinalizeEntryDraftError(
            "finalize report has no asset label; rerun asset_image_finalize.py "
            "with --label <asset_id>"
        )
    if reported_id != asset_id:
        raise FinalizeEntryDraftError(
            f"finalize report is for {reported_id}, not {asset_id}"
        )

    relative = _project_relative(
        _string(report, "path", "finalize report"), project_root
    )
    if is_reference:
        layout_type = "reference"
        res_path = _reference_res_path(relative)
    else:
        layout_type = "single"
        res_path = _runtime_res_path(
            relative, production_family=production_family, asset_id=asset_id
        )
    if not (Path(project_root) / relative).is_file():
        raise FinalizeEntryDraftError(f"finalized file not found: {relative}")

    entry = {
        "version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": production_family,
        "source_layout": {"type": layout_type, "path": res_path},
        "processing_status": DRAFT_STATUS,
    }
    try:
        validate_entry(entry, project_root=Path(project_root), check_files=True)
    except StableEntryError as exc:
        raise FinalizeEntryDraftError(str(exc)) from exc
    return entry


def write_finalize_entry_draft(
    finalize_report: Path,
    *,
    asset_id: str,
    tag: str,
    production_family: str,
    project_root: Path,
    out: Path,
) -> dict[str, Any]:
    entry = build_finalize_entry_draft(
        finalize_report,
        asset_id=asset_id,
        tag=tag,
        production_family=production_family,
        project_root=project_root,
    )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "draft": str(out),
        "asset_id": asset_id,
        "tag": tag,
        "source_layout": entry["source_layout"]["type"],
        "path": entry["source_layout"]["path"],
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a v1 stable-entry draft from an asset_image_finalize.py report"
    )
    parser.add_argument(
        "--finalize-report",
        required=True,
        type=Path,
        help="JSON report printed by asset_image_finalize.py",
    )
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--production-family", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        result = write_finalize_entry_draft(
            args.finalize_report,
            asset_id=args.asset_id,
            tag=args.tag,
            production_family=args.production_family,
            project_root=args.project_root,
            out=args.out,
        )
    except FinalizeEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
