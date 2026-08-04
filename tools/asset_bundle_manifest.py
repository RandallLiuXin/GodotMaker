#!/usr/bin/env python3
"""Build and validate a pointer-only manifest for one multi-output asset bundle.

ASSETS.md keeps the original planning rows. A bundle manifest lets those rows
share one pointer without expanding every runtime output into another Markdown
row. Each worker-consumable output still owns an independent stable entry.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_generation_index import GenerationIndexError, check_index
from asset_stable_entry import (
    BUNDLE_FAMILIES,
    ENTRIES_ROOT,
    REFERENCE_LAYOUTS,
    SCHEMA_VERSION,
    StableEntryError,
    _load_json,
    entry_relative_path,
    is_schema_version,
    safe_identifier,
    validate_entry,
)

BUNDLES_ROOT = ".godotmaker/asset-generation/bundles"
ROOT_INDEX_PATH = ".godotmaker/asset-generation/manifest.json"
BUNDLE_KEYS = {
    "version",
    "tag",
    "bundle_id",
    "production_family",
    "asset_ids",
    "entries",
}


class AssetBundleManifestError(Exception):
    """Raised when a multi-output bundle cannot be handed off safely."""


def bundle_manifest_relative_path(tag: str, bundle_id: str) -> str:
    tag = safe_identifier(tag, "tag")
    bundle_id = safe_identifier(bundle_id, "bundle_id")
    return f"{BUNDLES_ROOT}/{tag}/{bundle_id}.json"


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = _load_json(Path(path))
    except StableEntryError as exc:
        raise AssetBundleManifestError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise AssetBundleManifestError(f"{label} must be a JSON object: {path}")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise AssetBundleManifestError(f"{label} must be a non-empty list")
    result: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise AssetBundleManifestError(f"{label}[{index}] must be a non-empty string")
        if item in seen:
            raise AssetBundleManifestError(f"{label} contains a duplicate: {item}")
        seen.add(item)
        result.append(item)
    return result


def _registered_entry_paths(project_root: Path) -> set[str]:
    index_path = project_root / ROOT_INDEX_PATH
    try:
        check_index(index_path, project_root=project_root, check_entries=True)
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (GenerationIndexError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AssetBundleManifestError(f"Generated root index is invalid: {exc}") from exc
    return {item["entry_path"] for item in data["entries"]}


def validate_bundle_manifest(
    data: Any,
    *,
    project_root: Path,
    check_files: bool = True,
    check_registered: bool = True,
) -> dict[str, Any]:
    """Validate a bundle manifest and every child stable entry it references."""
    if not isinstance(data, dict):
        raise AssetBundleManifestError("Bundle manifest must be a JSON object")
    extra = set(data) - BUNDLE_KEYS
    missing = BUNDLE_KEYS - set(data)
    if extra or missing:
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        if extra:
            details.append(f"unexpected: {', '.join(sorted(extra))}")
        raise AssetBundleManifestError(
            "Bundle manifest must contain only the v1 fields (" + "; ".join(details) + ")"
        )
    if not is_schema_version(data.get("version")):
        raise AssetBundleManifestError(
            f"Bundle manifest version must be integer {SCHEMA_VERSION}"
        )
    try:
        tag = safe_identifier(data["tag"], "bundle manifest tag")
        bundle_id = safe_identifier(data["bundle_id"], "bundle manifest bundle_id")
    except StableEntryError as exc:
        raise AssetBundleManifestError(str(exc)) from exc
    family = data["production_family"]
    if family not in BUNDLE_FAMILIES:
        raise AssetBundleManifestError(
            f"production_family must be a bundle family: {', '.join(sorted(BUNDLE_FAMILIES))}"
        )
    asset_ids = _string_list(data["asset_ids"], "asset_ids")
    for asset_id in asset_ids:
        try:
            safe_identifier(asset_id, "asset_ids item")
        except StableEntryError as exc:
            raise AssetBundleManifestError(str(exc)) from exc
    pointers = _string_list(data["entries"], "entries")
    registered = _registered_entry_paths(Path(project_root)) if check_registered else set()

    normalized_entries: list[str] = []
    for pointer in pointers:
        parts = pointer.split("/")
        prefix = ENTRIES_ROOT.split("/")
        if (
            "\\" in pointer
            or any(part in {"", ".", ".."} for part in parts)
            or len(parts) != len(prefix) + 2
            or parts[: len(prefix)] != prefix
            or not parts[-1].endswith(".json")
            or parts[-1] == ".json"
        ):
            raise AssetBundleManifestError(
                "bundle child entry must use the canonical "
                "entries/<tag>/<asset_id>.json shape"
            )
        path = Path(project_root).resolve() / Path(pointer)
        entry = _load_object(path, "bundle child entry")
        try:
            entry = validate_entry(
                entry, project_root=Path(project_root), check_files=check_files
            )
        except StableEntryError as exc:
            raise AssetBundleManifestError(f"{pointer}: {exc}") from exc
        canonical = entry_relative_path(entry["tag"], entry["asset_id"])
        if pointer != canonical:
            raise AssetBundleManifestError(
                f"bundle child entry pointer must be canonical: {canonical}"
            )
        if check_registered and pointer not in registered:
            raise AssetBundleManifestError(
                f"bundle child entry is not registered in {ROOT_INDEX_PATH}: {pointer}"
            )
        if entry["tag"] != tag:
            raise AssetBundleManifestError(
                f"bundle child {entry['asset_id']} has tag {entry['tag']!r}; expected {tag!r}"
            )
        if entry["production_family"] != family:
            raise AssetBundleManifestError(
                f"bundle child {entry['asset_id']} has family "
                f"{entry['production_family']!r}; expected {family!r}"
            )
        if entry.get("bundle_id") != bundle_id:
            raise AssetBundleManifestError(
                f"bundle child {entry['asset_id']} is not owned by bundle {bundle_id!r}"
            )
        if entry["processing_status"] != "ready":
            raise AssetBundleManifestError(
                f"bundle child {entry['asset_id']} is {entry['processing_status']!r}; "
                "every child must be ready"
            )
        if entry["source_layout"]["type"] in REFERENCE_LAYOUTS:
            raise AssetBundleManifestError(
                f"bundle child {entry['asset_id']} is reference-only"
            )
        normalized_entries.append(pointer)

    return {
        "version": SCHEMA_VERSION,
        "tag": tag,
        "bundle_id": bundle_id,
        "production_family": family,
        "asset_ids": asset_ids,
        "entries": normalized_entries,
    }


def _expected_bundle_entries(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Rebuild the authoritative child set from the validated family handoff."""
    request = _load_object(request_path, "bundle request")
    family = request.get("asset_type")
    if family in {"ui-kit", "card-kit"}:
        from asset_ui_card_entry_draft import (
            UICardEntryDraftError,
            build_ui_card_entry_drafts,
        )

        try:
            return build_ui_card_entry_drafts(
                request_path,
                result_path,
                tag=tag,
                project_root=project_root,
                check_files=True,
            )
        except UICardEntryDraftError as exc:
            raise AssetBundleManifestError(
                f"bundle request/result handoff is invalid: {exc}"
            ) from exc
    if family == "compact-prop-pack":
        from asset_compact_prop_pack_entry_draft import (
            CompactPropPackEntryDraftError,
            build_compact_prop_pack_entry_drafts,
        )

        try:
            return build_compact_prop_pack_entry_drafts(
                request_path,
                result_path,
                tag=tag,
                project_root=project_root,
                check_files=True,
            )
        except CompactPropPackEntryDraftError as exc:
            raise AssetBundleManifestError(
                f"bundle request/result handoff is invalid: {exc}"
            ) from exc
    if family == "platform-strip":
        from asset_platform_strip_entry_draft import (
            PlatformStripEntryDraftError,
            build_platform_strip_entry_drafts,
        )

        try:
            return build_platform_strip_entry_drafts(
                request_path,
                result_path,
                tag=tag,
                project_root=project_root,
                check_files=True,
            )
        except PlatformStripEntryDraftError as exc:
            raise AssetBundleManifestError(
                f"bundle request/result handoff is invalid: {exc}"
            ) from exc
    raise AssetBundleManifestError(
        "bundle request asset_type must be ui-kit, card-kit, compact-prop-pack, "
        "or platform-strip"
    )


def build_bundle_manifest(
    entry_paths: list[Path],
    *,
    asset_ids: list[str],
    request_path: Path,
    result_path: Path,
    project_root: Path,
) -> dict[str, Any]:
    if not entry_paths:
        raise AssetBundleManifestError("at least one --entry-file is required")
    entries: list[dict[str, Any]] = []
    pointers: list[str] = []
    for path in entry_paths:
        entry = _load_object(Path(path), "stable entry")
        try:
            entry = validate_entry(entry, project_root=project_root, check_files=True)
        except StableEntryError as exc:
            raise AssetBundleManifestError(f"{path}: {exc}") from exc
        canonical = entry_relative_path(entry["tag"], entry["asset_id"])
        if Path(path).resolve() != (Path(project_root) / canonical).resolve():
            raise AssetBundleManifestError(f"{path} must be the canonical entry path {canonical}")
        entries.append(entry)
        pointers.append(canonical)

    first = entries[0]
    bundle_id = first.get("bundle_id")
    if not isinstance(bundle_id, str):
        raise AssetBundleManifestError("stable entries do not declare a bundle_id")
    if any(entry["processing_status"] != "ready" for entry in entries):
        raise AssetBundleManifestError("every child must be ready")
    expected_entries = _expected_bundle_entries(
        request_path,
        result_path,
        tag=first["tag"],
        project_root=Path(project_root),
    )
    expected_by_pointer = {
        entry_relative_path(entry["tag"], entry["asset_id"]): entry
        for entry in expected_entries
    }
    actual_by_pointer = dict(zip(pointers, entries, strict=True))
    if len(actual_by_pointer) != len(entries):
        raise AssetBundleManifestError("stable entry paths must not be repeated")
    missing = set(expected_by_pointer) - set(actual_by_pointer)
    unexpected = set(actual_by_pointer) - set(expected_by_pointer)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append(f"missing: {', '.join(sorted(missing))}")
        if unexpected:
            details.append(f"unexpected: {', '.join(sorted(unexpected))}")
        raise AssetBundleManifestError(
            "stable entries must exactly match the validated request/result child set ("
            + "; ".join(details)
            + ")"
        )
    for pointer, expected in expected_by_pointer.items():
        if actual_by_pointer[pointer] != expected:
            raise AssetBundleManifestError(
                f"stable entry does not match the validated request/result: {pointer}"
            )
    candidate = {
        "version": SCHEMA_VERSION,
        "tag": first["tag"],
        "bundle_id": bundle_id,
        "production_family": first["production_family"],
        "asset_ids": asset_ids,
        "entries": list(expected_by_pointer),
    }
    return validate_bundle_manifest(candidate, project_root=project_root)


def write_bundle_manifest(
    entry_paths: list[Path],
    *,
    asset_ids: list[str],
    request_path: Path,
    result_path: Path,
    project_root: Path,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    request_path = Path(request_path)
    result_path = Path(result_path)
    if not request_path.is_absolute():
        request_path = root / request_path
    if not result_path.is_absolute():
        result_path = root / result_path
    manifest = build_bundle_manifest(
        entry_paths,
        asset_ids=asset_ids,
        request_path=request_path,
        result_path=result_path,
        project_root=root,
    )
    relative = bundle_manifest_relative_path(manifest["tag"], manifest["bundle_id"])
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(target.parent),
        suffix=".json",
        mode="w",
        encoding="utf-8",
    ) as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"ok": True, "path": relative, "manifest": manifest}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Write one pointer-only manifest for a ready asset bundle"
    )
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument(
        "--request",
        required=True,
        type=Path,
        help="Validated production request that declares the complete child set",
    )
    parser.add_argument(
        "--result",
        required=True,
        type=Path,
        help="Validated production result bound to the complete child set",
    )
    parser.add_argument("--entry-file", action="append", required=True, type=Path)
    parser.add_argument(
        "--asset-id",
        action="append",
        required=True,
        help="Existing ASSETS.md planning row satisfied by this bundle",
    )
    args = parser.parse_args()
    try:
        result = write_bundle_manifest(
            args.entry_file,
            asset_ids=args.asset_id,
            request_path=args.request,
            result_path=args.result,
            project_root=args.project_root,
        )
    except AssetBundleManifestError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
