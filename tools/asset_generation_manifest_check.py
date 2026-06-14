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
    "character_portrait",
    "character_action_source",
    "character_frame_output",
    "projectile_fx_source",
    "impact_fx_source",
    "compact_prop_pack",
    "ui_component_sheet",
    "icon_pack",
    "panel_source",
    "card_component_sheet",
    "card_frame_source",
    "portrait_frame_source",
    "background",
    "scene_prop_set",
    "platform_strip",
    "runtime_sprite",
    "texture",
    "audio",
}

FOREGROUND_CURATED_FAMILIES = {
    "projectile_fx_source",
    "impact_fx_source",
    "compact_prop_pack",
    "character_portrait",
    "ui_component_sheet",
    "icon_pack",
    "panel_source",
    "card_component_sheet",
    "card_frame_source",
    "portrait_frame_source",
    "scene_prop_set",
    "platform_strip",
    "runtime_sprite",
}

ALLOWED_RUNTIME_ARTIFACTS = {
    "reference",
    "single",
    "grid_sheet",
    "region_atlas",
}

FOREGROUND_READY_ARTIFACTS = {
    "single",
    "grid_sheet",
    "region_atlas",
}

DIRECT_SINGLE_FAMILIES = {
    "character_portrait",
    "panel_source",
    "card_frame_source",
    "portrait_frame_source",
}

REFERENCE_FAMILIES = {
    "screen_reference",
    "style_reference",
}

ALLOWED_PRODUCTION_SHAPES = {
    "single_image",
    "grid_sheet",
    "action_sheet",
    "frame_sequence",
    "delivery_sheet",
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
    "transparent_autoslice",
    "solid_background_autoslice",
    "row_column_grid",
    "explicit_boxes",
    "manual_selection",
    "regenerate_source",
}

ALLOWED_ACTION_ALIGNS = {"center", "bottom", "feet"}


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


def _target_size_field(
    item: dict[str, Any],
    field: str,
    issues: list[str],
    *,
    index: int,
    required: bool = False,
) -> str | None:
    value = _string_field(item, field, issues, index=index, required=required)
    if value is None:
        return None
    raw = value.lower()
    if "x" not in raw:
        issues.append(f"assets[{index}].{field} must use WIDTHxHEIGHT")
        return None
    left, right = raw.split("x", 1)
    try:
        width = int(left)
        height = int(right)
    except ValueError:
        issues.append(f"assets[{index}].{field} must use integer WIDTHxHEIGHT")
        return None
    if width <= 0 or height <= 0:
        issues.append(f"assets[{index}].{field} dimensions must be positive")
        return None
    return value


def _target_aspect_field(
    item: dict[str, Any],
    field: str,
    issues: list[str],
    *,
    index: int,
    required: bool = False,
) -> str | None:
    value = _string_field(item, field, issues, index=index, required=required)
    if value is None:
        return None
    if ":" not in value:
        issues.append(f"assets[{index}].{field} must use WIDTH:HEIGHT")
        return None
    left, right = value.split(":", 1)
    try:
        width = float(left)
        height = float(right)
    except ValueError:
        issues.append(f"assets[{index}].{field} must use numeric WIDTH:HEIGHT")
        return None
    if width <= 0 or height <= 0:
        issues.append(f"assets[{index}].{field} dimensions must be positive")
        return None
    return value


def _path_exists(project_root: Path, raw_path: str, issues: list[str], message: str) -> None:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        issues.append(f"{message}: {raw_path}")


def _runtime_metadata(
    project_root: Path,
    raw_path: str,
    issues: list[str],
    *,
    index: int,
    label: str,
) -> dict[str, Any] | None:
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        issues.append(f"assets[{index}].{label} not found: {raw_path}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        issues.append(f"assets[{index}].{label} is not readable JSON: {raw_path}: {exc}")
        return None
    if not isinstance(data, dict):
        issues.append(f"assets[{index}].{label} must be a JSON object: {raw_path}")
        return None
    return data


def _normalized_project_path(raw_path: object) -> str | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    return Path(raw_path).as_posix()


def _check_runtime_identity(
    metadata: dict[str, Any],
    item: dict[str, Any],
    *,
    artifact: str,
    index: int,
    issues: list[str],
    label: str,
) -> None:
    if metadata.get("runtime_artifact") != artifact:
        issues.append(f"assets[{index}].{label}.runtime_artifact must be {artifact}")
    for field in ("asset_id", "tag"):
        if metadata.get(field) != item.get(field):
            issues.append(f"assets[{index}].{label}.{field} must match manifest")


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
) -> tuple[str | None, str | None]:
    curation = item.get("curation")
    if curation is None:
        return None, None
    if not isinstance(curation, dict):
        issues.append(f"assets[{index}].curation must be an object or null")
        return None, None

    status = curation.get("status")
    if not isinstance(status, str) or not status.strip():
        issues.append(f"assets[{index}].curation.status must be a non-empty string")
        status = None
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

    if status == "selected":
        selected_count = curation.get("selected_count")
        if not isinstance(selected_count, int) or selected_count <= 0:
            issues.append(f"assets[{index}].curation.selected_count must be positive when selected")

    clean_report_path = report_path if isinstance(report_path, str) and report_path.strip() else None
    return clean_report_path, status if isinstance(status, str) else None


def _check_character_frame_output(
    item: dict[str, Any],
    project_root: Path,
    *,
    index: int,
    issues: list[str],
) -> list[str]:
    for field in ("derived_from", "canonical_reference"):
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            issues.append(f"assets[{index}].{field} is required for character_frame_output")

    return _check_action_runtime_metadata(
        item,
        project_root,
        index=index,
        issues=issues,
        require_sheet=True,
    )


def _check_action_runtime_metadata(
    item: dict[str, Any],
    project_root: Path,
    *,
    index: int,
    issues: list[str],
    require_sheet: bool,
) -> list[str]:
    extra_file_paths: list[str] = []
    qc = item.get("qc")
    if not isinstance(qc, dict):
        issues.append(f"assets[{index}].qc must be an object for animation runtime artifact")
        return extra_file_paths
    action = qc.get("action_processing")
    if not isinstance(action, dict):
        issues.append(
            f"assets[{index}].qc.action_processing is required for animation runtime artifact"
        )
        return extra_file_paths

    frame_count = action.get("frame_count")
    if not isinstance(frame_count, int) or frame_count <= 0:
        issues.append(f"assets[{index}].qc.action_processing.frame_count must be positive")

    metadata_path = action.get("metadata_path")
    if not isinstance(metadata_path, str) or not metadata_path.strip():
        issues.append(f"assets[{index}].qc.action_processing.metadata_path must be a non-empty string")
        return extra_file_paths

    extra_file_paths.append(metadata_path)
    metadata = _runtime_metadata(
        project_root,
        metadata_path,
        issues,
        index=index,
        label="qc.action_processing.metadata_path",
    )
    if metadata is None:
        return extra_file_paths

    _check_runtime_identity(
        metadata,
        item,
        artifact="grid_sheet",
        index=index,
        issues=issues,
        label="runtime metadata",
    )

    metadata_frame_count = metadata.get("frame_count")
    if metadata_frame_count != frame_count:
        issues.append(
            f"assets[{index}].qc.action_processing.frame_count must match runtime metadata"
        )

    frame_paths = metadata.get("frame_paths")
    if not isinstance(frame_paths, list) or not frame_paths:
        issues.append(f"assets[{index}].runtime metadata frame_paths must be a non-empty list")
    else:
        clean_frame_paths = []
        for frame_index, frame_path in enumerate(frame_paths):
            if not isinstance(frame_path, str) or not frame_path.strip():
                issues.append(
                    f"assets[{index}].runtime metadata frame_paths[{frame_index}] "
                    "must be a non-empty string"
                )
                continue
            clean_frame_paths.append(frame_path)
            extra_file_paths.append(frame_path)
        if isinstance(frame_count, int) and frame_count > 0 and len(clean_frame_paths) != frame_count:
            issues.append(
                f"assets[{index}].runtime metadata frame_paths length must match frame_count"
            )

    align = metadata.get("align")
    if align not in ALLOWED_ACTION_ALIGNS:
        issues.append(f"assets[{index}].runtime metadata align is not allowed: {align}")

    if not isinstance(metadata.get("shared_scale"), bool):
        issues.append(f"assets[{index}].runtime metadata shared_scale must be boolean")

    sheet_path = metadata.get("sheet_path")
    if require_sheet:
        if not isinstance(sheet_path, str) or not sheet_path.strip():
            issues.append(f"assets[{index}].runtime metadata sheet_path must be a non-empty string")
        elif _normalized_project_path(sheet_path) != _normalized_project_path(item.get("final_path")):
            issues.append(f"assets[{index}].runtime metadata sheet_path must match final_path")

    edge_touch = metadata.get("edge_touch_frames")
    if edge_touch is not None and not isinstance(edge_touch, list):
        issues.append(f"assets[{index}].runtime metadata edge_touch_frames must be a list")
    if isinstance(edge_touch, list) and edge_touch:
        issues.append(f"assets[{index}].runtime metadata edge_touch_frames must be empty")

    scale_reference = metadata.get("scale_reference")
    if not isinstance(scale_reference, dict):
        issues.append(f"assets[{index}].runtime metadata scale_reference must be an object")
    elif not isinstance(scale_reference.get("checked"), bool):
        issues.append(f"assets[{index}].runtime metadata scale_reference.checked must be boolean")

    return extra_file_paths


def _check_atlas_metadata(
    item: dict[str, Any],
    project_root: Path,
    *,
    index: int,
    issues: list[str],
) -> str | None:
    qc = item.get("qc")
    if not isinstance(qc, dict):
        issues.append(f"assets[{index}].qc must be an object for region_atlas")
        return None
    atlas = qc.get("atlas_metadata")
    if not isinstance(atlas, dict):
        issues.append(f"assets[{index}].qc.atlas_metadata is required for region_atlas")
        return None

    metadata_path = atlas.get("metadata_path")
    if not isinstance(metadata_path, str) or not metadata_path.strip():
        issues.append(f"assets[{index}].qc.atlas_metadata.metadata_path must be a non-empty string")
        metadata_path = None

    region_count = atlas.get("region_count")
    has_region_count = isinstance(region_count, int) and region_count > 0
    if not has_region_count:
        issues.append(f"assets[{index}].qc.atlas_metadata.region_count must be positive")

    if isinstance(metadata_path, str) and metadata_path.strip():
        metadata = _runtime_metadata(
            project_root,
            metadata_path,
            issues,
            index=index,
            label="qc.atlas_metadata.metadata_path",
        )
        if isinstance(metadata, dict):
            _check_runtime_identity(
                metadata,
                item,
                artifact="region_atlas",
                index=index,
                issues=issues,
                label="atlas runtime metadata",
            )
            atlas_path = metadata.get("atlas_path")
            if not isinstance(atlas_path, str) or not atlas_path.strip():
                issues.append(f"assets[{index}].atlas runtime metadata atlas_path must be a non-empty string")
            elif _normalized_project_path(atlas_path) != _normalized_project_path(item.get("final_path")):
                issues.append(f"assets[{index}].atlas runtime metadata atlas_path must match final_path")

            regions = metadata.get("regions")
            if not isinstance(regions, list) or not regions:
                issues.append(f"assets[{index}].atlas runtime metadata regions must be a non-empty list")
            else:
                if isinstance(region_count, int) and region_count > 0 and len(regions) != region_count:
                    issues.append(
                        f"assets[{index}].qc.atlas_metadata.region_count must match runtime metadata"
                    )
                for region_index, region in enumerate(regions):
                    if not isinstance(region, dict):
                        issues.append(
                            f"assets[{index}].atlas runtime metadata regions[{region_index}] "
                            "must be an object"
                        )
                        continue
                    name = region.get("name")
                    if not isinstance(name, str) or not name.strip():
                        issues.append(
                            f"assets[{index}].atlas runtime metadata regions[{region_index}].name "
                            "must be a non-empty string"
                        )
                    rect = region.get("rect")
                    if (
                        not isinstance(rect, list)
                        or len(rect) != 4
                        or any(not isinstance(value, int) or value < 0 for value in rect)
                    ):
                        issues.append(
                            f"assets[{index}].atlas runtime metadata regions[{region_index}].rect "
                            "must be four non-negative integers"
                        )

    return metadata_path if isinstance(metadata_path, str) and metadata_path.strip() else None


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
    seen_final_paths: dict[tuple[str, str], tuple[int, str]] = {}
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
        runtime_artifact = _string_field(
            item,
            "runtime_artifact",
            issues,
            index=index,
            required=False,
        )
        processing_status = _string_field(item, "processing_status", issues, index=index)
        extraction_status = _string_field(item, "extraction_status", issues, index=index)
        curation_report_path, curation_status = _check_curation(item, index=index, issues=issues)
        require_target_geometry = (
            family in {"screen_reference", "background"}
            and processing_status not in {"deferred", "rejected"}
        )
        _target_size_field(
            item,
            "target_size",
            issues,
            index=index,
            required=require_target_geometry,
        )
        _target_aspect_field(
            item,
            "target_aspect",
            issues,
            index=index,
            required=require_target_geometry,
        )

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
            seen_final_paths,
            final_path,
            tag=tag,
            field="final_path",
            index=index,
            issues=issues,
        )

        if family and family not in ALLOWED_FAMILIES:
            issues.append(f"assets[{index}].family is not allowed: {family}")
        if production_shape and production_shape not in ALLOWED_PRODUCTION_SHAPES:
            issues.append(
                f"assets[{index}].production_shape is not allowed: {production_shape}"
            )
        if runtime_artifact and runtime_artifact not in ALLOWED_RUNTIME_ARTIFACTS:
            issues.append(
                f"assets[{index}].runtime_artifact is not allowed: {runtime_artifact}"
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
            processing_status in {"processed", "ready"}
            and curation_status is not None
            and curation_status not in {"selected", "not_required"}
        ):
            issues.append(
                f"assets[{index}].curation.status must be selected or not_required "
                f"for {processing_status}"
            )

        extra_file_paths: list[str] = []
        runtime_artifact_checked = False
        if family in FOREGROUND_CURATED_FAMILIES and processing_status == "ready":
            clean_artifact = runtime_artifact
            if clean_artifact is None:
                if production_shape in {"action_sheet", "delivery_sheet", "frame_sequence"}:
                    clean_artifact = "grid_sheet"
                elif production_shape in {"grid_sheet", "curation_required"}:
                    clean_artifact = "region_atlas"
                else:
                    clean_artifact = "single"
            if clean_artifact not in FOREGROUND_READY_ARTIFACTS:
                issues.append(
                    f"assets[{index}].runtime_artifact is not valid for runtime-ready foreground: "
                    f"{clean_artifact}"
                )
            if clean_artifact == "single":
                if production_shape == "single_image" and family in DIRECT_SINGLE_FAMILIES:
                    if curation_status not in {None, "not_required", "selected"}:
                        issues.append(
                            f"assets[{index}].curation.status must be not_required "
                            "or selected for single_image"
                        )
                else:
                    curation = item.get("curation")
                    if curation is None:
                        issues.append(f"assets[{index}] missing selected curation for single")
                    elif curation_status != "selected":
                        issues.append(
                            f"assets[{index}].curation.status must be selected for single"
                        )
                    elif curation.get("strategy") == "none":
                        issues.append(
                            f"assets[{index}].curation.strategy must not be none for single"
                        )
                allowed_extraction = (
                    {"not_required", "processed", "extracted"}
                    if production_shape == "single_image" and family in DIRECT_SINGLE_FAMILIES
                    else {"extracted", "processed"}
                )
                if extraction_status not in allowed_extraction:
                    issues.append(
                        f"assets[{index}].extraction_status must be one of "
                        f"{sorted(allowed_extraction)} "
                        "for single"
                    )
            elif clean_artifact == "region_atlas":
                runtime_artifact_checked = True
                atlas_metadata_path = _check_atlas_metadata(item, root, index=index, issues=issues)
                if atlas_metadata_path:
                    extra_file_paths.append(atlas_metadata_path)
                if extraction_status not in {"extracted", "processed"}:
                    issues.append(
                        f"assets[{index}].extraction_status must be extracted or processed "
                        "for region_atlas"
                    )
            elif clean_artifact == "grid_sheet":
                runtime_artifact_checked = True
                extra_file_paths.extend(
                    _check_action_runtime_metadata(
                        item,
                        root,
                        index=index,
                        issues=issues,
                        require_sheet=True,
                    )
                )
                if extraction_status != "processed":
                    issues.append(
                        f"assets[{index}].extraction_status must be processed for {clean_artifact}"
                    )

        if runtime_artifact == "reference" and family not in REFERENCE_FAMILIES:
            issues.append(
                f"assets[{index}].runtime_artifact reference is not allowed for family {family}"
            )

        if (
            runtime_artifact == "region_atlas"
            and processing_status in {"processed", "ready"}
            and not runtime_artifact_checked
        ):
            atlas_metadata_path = _check_atlas_metadata(item, root, index=index, issues=issues)
            if atlas_metadata_path:
                extra_file_paths.append(atlas_metadata_path)

        if (
            runtime_artifact == "grid_sheet"
            and processing_status in {"processed", "ready"}
            and family != "character_frame_output"
            and not runtime_artifact_checked
        ):
            extra_file_paths.extend(
                _check_action_runtime_metadata(
                    item,
                    root,
                    index=index,
                    issues=issues,
                    require_sheet=True,
                )
            )

        if (
            production_shape in {
                "grid_sheet",
                "action_sheet",
                "frame_sequence",
                "delivery_sheet",
                "curation_required",
            }
            and processing_status != "deferred"
        ):
            if item.get("curation") is None:
                issues.append(f"assets[{index}] missing curation for {production_shape}")
        if processing_status == "needs_curation" and item.get("curation") is None:
            issues.append(f"assets[{index}] missing curation for needs_curation")

        if family == "character_frame_output":
            extra_file_paths.extend(
                _check_character_frame_output(item, root, index=index, issues=issues)
            )

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
            for extra_path in extra_file_paths:
                _path_exists(root, extra_path, issues, "Action processing path not found")
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
