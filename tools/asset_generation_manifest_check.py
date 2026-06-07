#!/usr/bin/env python3
"""Validate the asset-generation handoff manifest."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ALLOWED_FAMILIES = {
    "screen_reference",
    "style_reference",
    "character_canonical",
    "character_action_source",
    "projectile_fx_source",
    "impact_fx_source",
    "compact_prop_pack",
    "ui_component_sheet",
    "icon_pack",
    "panel_source",
    "background",
    "runtime_sprite",
    "texture",
    "audio",
}

ALLOWED_PRODUCTION_SHAPES = {
    "single_image",
    "grid_sheet",
    "action_sheet",
    "frame_sequence",
    "reference_only",
    "curation_required",
}

ALLOWED_PROCESSING_STATUSES = {
    "source_only",
    "needs_curation",
    "processed",
    "ready",
    "deferred",
    "rejected",
}

ALLOWED_EXTRACTION_STATUSES = {
    "not_required",
    "pending",
    "source_sheet",
    "extracted",
    "processed",
    "needs_curation",
    "rejected",
}

ALLOWED_CURATION_STATUSES = {
    "not_required",
    "pending",
    "candidate_extracted",
    "selected",
    "needs_curation",
    "needs_regeneration",
    "rejected",
}

ALLOWED_CURATION_STRATEGIES = {
    "none",
    "transparent_grid",
    "solid_background_grid",
    "row_column_grid",
    "explicit_boxes",
    "manual_selection",
    "regenerate_source",
}


class ManifestCheckError(Exception):
    """Raised when the asset-generation manifest is invalid."""


def _require(condition: bool, message: str, issues: list[str]) -> None:
    if not condition:
        issues.append(message)


def _string_field(
    item: dict[str, Any],
    field: str,
    issues: list[str],
    *,
    index: int,
    required: bool = True,
) -> str | None:
    value = item.get(field)
    if value is None:
        if required:
            issues.append(f"assets[{index}] missing {field}")
        return None
    if not isinstance(value, str) or not value.strip():
        issues.append(f"assets[{index}].{field} must be a non-empty string")
        return None
    return value


def _path_exists(project_root: Path, raw_path: str, issues: list[str], message: str) -> None:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        issues.append(f"{message}: {raw_path}")


def _track_unique_path(
    seen_paths: dict[tuple[str, str], tuple[int, str]],
    raw_path: str | None,
    *,
    tag: str | None,
    field: str,
    index: int,
    issues: list[str],
) -> None:
    if raw_path is None or tag is None:
        return
    key = (tag, Path(raw_path).as_posix())
    previous = seen_paths.get(key)
    if previous is not None:
        previous_index, previous_field = previous
        issues.append(
            f"Duplicate {field} path for tag {tag} at assets[{index}] also used by "
            f"assets[{previous_index}].{previous_field}: {raw_path}"
        )
        return
    seen_paths[key] = (index, field)


def _check_curation(
    item: dict[str, Any],
    *,
    index: int,
    issues: list[str],
) -> str | None:
    curation = item.get("curation")
    if curation is None:
        return None
    if not isinstance(curation, dict):
        issues.append(f"assets[{index}].curation must be an object or null")
        return None

    status = curation.get("status")
    if not isinstance(status, str) or not status.strip():
        issues.append(f"assets[{index}].curation.status must be a non-empty string")
    elif status not in ALLOWED_CURATION_STATUSES:
        issues.append(f"assets[{index}].curation.status is not allowed: {status}")

    strategy = curation.get("strategy")
    if not isinstance(strategy, str) or not strategy.strip():
        issues.append(f"assets[{index}].curation.strategy must be a non-empty string")
    elif strategy not in ALLOWED_CURATION_STRATEGIES:
        issues.append(f"assets[{index}].curation.strategy is not allowed: {strategy}")

    report_path = curation.get("report_path")
    if status != "not_required":
        if not isinstance(report_path, str) or not report_path.strip():
            issues.append(f"assets[{index}].curation.report_path must be a non-empty string")
            report_path = None
    elif report_path is not None and not isinstance(report_path, str):
        issues.append(f"assets[{index}].curation.report_path must be a string or null")
        report_path = None

    for field in ("selected_count", "rejected_count"):
        value = curation.get(field)
        if value is not None and (not isinstance(value, int) or value < 0):
            issues.append(f"assets[{index}].curation.{field} must be a non-negative integer")

    return report_path if isinstance(report_path, str) and report_path.strip() else None


def check_manifest(
    manifest_path: Path,
    *,
    project_root: Path | None = None,
    check_files: bool = False,
) -> dict[str, object]:
    """Validate one asset-generation manifest."""
    manifest_path = Path(manifest_path)
    root = Path(project_root) if project_root is not None else manifest_path.parent.parent.parent
    issues: list[str] = []

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ManifestCheckError(f"Invalid JSON manifest: {manifest_path}") from exc

    _require(isinstance(data, dict), "Manifest must be a JSON object", issues)
    if not isinstance(data, dict):
        raise ManifestCheckError("; ".join(issues))

    _require(data.get("version") == 1, "Manifest version must be 1", issues)
    assets = data.get("assets")
    _require(isinstance(assets, list), "Manifest assets must be a list", issues)
    if not isinstance(assets, list):
        raise ManifestCheckError("; ".join(issues))

    seen: set[tuple[str, str]] = set()
    seen_source_paths: dict[tuple[str, str], tuple[int, str]] = {}
    seen_final_paths: dict[tuple[str, str], tuple[int, str]] = {}
    seen_prompt_paths: dict[tuple[str, str], tuple[int, str]] = {}
    checked_assets = 0
    file_checks = 0

    for index, item in enumerate(assets):
        if not isinstance(item, dict):
            issues.append(f"assets[{index}] must be an object")
            continue

        asset_id = _string_field(item, "asset_id", issues, index=index)
        tag = _string_field(item, "tag", issues, index=index)
        family = _string_field(item, "family", issues, index=index)
        production_shape = _string_field(item, "production_shape", issues, index=index)
        _string_field(item, "runtime_role", issues, index=index)
        source_path = _string_field(item, "source_path", issues, index=index, required=False)
        final_path = _string_field(item, "final_path", issues, index=index, required=False)
        prompt_path = _string_field(item, "prompt_path", issues, index=index, required=False)
        processing_status = _string_field(item, "processing_status", issues, index=index)
        extraction_status = _string_field(item, "extraction_status", issues, index=index)
        curation_report_path = _check_curation(item, index=index, issues=issues)

        for optional_field in ("derived_from", "canonical_reference", "preview_path", "notes"):
            value = item.get(optional_field)
            if value is not None and not isinstance(value, str):
                issues.append(f"assets[{index}].{optional_field} must be a string or null")

        qc = item.get("qc")
        if qc is not None and not isinstance(qc, dict):
            issues.append(f"assets[{index}].qc must be an object or null")

        if tag and asset_id:
            key = (tag, asset_id)
            if key in seen:
                issues.append(f"Duplicate asset_id for tag {tag}: {asset_id}")
            seen.add(key)

        _track_unique_path(
            seen_source_paths,
            source_path,
            tag=tag,
            field="source_path",
            index=index,
            issues=issues,
        )
        _track_unique_path(
            seen_final_paths,
            final_path,
            tag=tag,
            field="final_path",
            index=index,
            issues=issues,
        )
        _track_unique_path(
            seen_prompt_paths,
            prompt_path,
            tag=tag,
            field="prompt_path",
            index=index,
            issues=issues,
        )

        if family and family not in ALLOWED_FAMILIES:
            issues.append(f"assets[{index}].family is not allowed: {family}")
        if production_shape and production_shape not in ALLOWED_PRODUCTION_SHAPES:
            issues.append(
                f"assets[{index}].production_shape is not allowed: {production_shape}"
            )
        if processing_status and processing_status not in ALLOWED_PROCESSING_STATUSES:
            issues.append(
                f"assets[{index}].processing_status is not allowed: {processing_status}"
            )
        if extraction_status and extraction_status not in ALLOWED_EXTRACTION_STATUSES:
            issues.append(
                f"assets[{index}].extraction_status is not allowed: {extraction_status}"
            )

        if processing_status in {"source_only", "needs_curation", "processed", "ready"}:
            if source_path is None:
                issues.append(f"assets[{index}] missing source_path for {processing_status}")
            if prompt_path is None:
                issues.append(f"assets[{index}] missing prompt_path for {processing_status}")

        if processing_status in {"processed", "ready"} and final_path is None:
            issues.append(f"assets[{index}] missing final_path for {processing_status}")

        if (
            production_shape in {"grid_sheet", "action_sheet", "frame_sequence", "curation_required"}
            and processing_status != "deferred"
        ):
            if item.get("curation") is None:
                issues.append(f"assets[{index}] missing curation for {production_shape}")
        if processing_status == "needs_curation" and item.get("curation") is None:
            issues.append(f"assets[{index}] missing curation for needs_curation")

        if check_files:
            if source_path and processing_status in {"source_only", "needs_curation", "processed", "ready"}:
                _path_exists(root, source_path, issues, "Source path not found")
                file_checks += 1
            if prompt_path and processing_status in {"source_only", "needs_curation", "processed", "ready"}:
                _path_exists(root, prompt_path, issues, "Prompt path not found")
                file_checks += 1
            if final_path and processing_status in {"processed", "ready"}:
                _path_exists(root, final_path, issues, "Final path not found")
                file_checks += 1
            if curation_report_path:
                _path_exists(root, curation_report_path, issues, "Curation report not found")
                file_checks += 1

        checked_assets += 1

    if issues:
        raise ManifestCheckError("; ".join(issues))

    return {
        "ok": True,
        "path": str(manifest_path),
        "asset_count": checked_assets,
        "check_files": check_files,
        "file_checks": file_checks,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Validate asset-generation manifest")
    parser.add_argument(
        "manifest",
        nargs="?",
        default=".godotmaker/asset-generation/manifest.json",
        help="Manifest path",
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Project root for relative file checks",
    )
    parser.add_argument(
        "--check-files",
        action="store_true",
        help="Check referenced source, prompt, and final files where required",
    )
    args = parser.parse_args()

    try:
        result = check_manifest(
            Path(args.manifest),
            project_root=Path(args.project_root),
            check_files=args.check_files,
        )
    except ManifestCheckError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
