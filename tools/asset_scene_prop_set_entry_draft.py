#!/usr/bin/env python3
"""Build the ready v1 entry for one compiled scene-prop-set atlas.

``scene-prop-set`` produces one physical region atlas and several independent
``AtlasTexture`` resources. The stable-entry v1 contract deliberately remains
one source layout plus one Godot artifact, so this builder records the complete
atlas set with a deterministic primary region while mechanically proving that
every declared region resource exists. The atlas metadata remains the inventory
for the other independently usable ``AtlasTexture`` files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asset_skill_contract_check import AssetContractError, check_result
from asset_stable_entry import (
    SCHEMA_VERSION,
    StableEntryError,
    stable_output_dir,
    validate_entry,
)

FAMILY = "scene-prop-set"
LEVELS = ("L0", "L1", "L2", "L3", "L4")


class ScenePropSetEntryDraftError(Exception):
    """Raised when a scene-prop-set result cannot become a ready entry."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report a concise CLI failure
        raise ScenePropSetEntryDraftError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ScenePropSetEntryDraftError(f"{label} must be a JSON object: {path}")
    return value


def _stable_paths(asset_id: str) -> tuple[str, str, str]:
    directory = stable_output_dir(FAMILY, asset_id)
    return (
        f"res://{directory}/{asset_id}.png",
        f"res://{directory}/{asset_id}.json",
        directory,
    )


def _slot_names(declaration: dict[str, Any]) -> list[str]:
    if set(declaration) != {"version", "atlas", "slots"}:
        raise ScenePropSetEntryDraftError(
            "declaration must contain exactly version, atlas, and slots"
        )
    if declaration.get("version") != 1 or not isinstance(declaration.get("slots"), list):
        raise ScenePropSetEntryDraftError("declaration must be a v1 slot declaration")
    names: list[str] = []
    for index, slot in enumerate(declaration["slots"]):
        if not isinstance(slot, dict) or not isinstance(slot.get("name"), str):
            raise ScenePropSetEntryDraftError(
                f"declaration slots[{index}].name must be a non-empty string"
            )
        name = slot["name"].strip()
        if not name or name in names:
            raise ScenePropSetEntryDraftError(
                "declaration slots must have unique non-empty names"
            )
        names.append(name)
    if not names:
        raise ScenePropSetEntryDraftError("declaration must contain at least one slot")
    return names


def _assert_file(project_root: Path, res_path: str, label: str) -> None:
    if not res_path.startswith("res://"):
        raise ScenePropSetEntryDraftError(f"{label} must be a res:// path")
    target = project_root / res_path[len("res://"):]
    if not target.is_file() or target.stat().st_size <= 0:
        raise ScenePropSetEntryDraftError(f"{label} is missing or empty: {res_path}")


def _validate_metadata(project_root: Path, metadata_path: str, atlas_path: str, names: list[str]) -> None:
    metadata = _load_object(project_root / metadata_path[len("res://"):], "atlas metadata")
    regions = metadata.get("regions")
    if metadata.get("version") != 1 or metadata.get("atlas_path") != atlas_path:
        raise ScenePropSetEntryDraftError("atlas metadata does not bind the stable atlas path")
    canonical_names = sorted(names)
    if not isinstance(regions, list) or [item.get("name") for item in regions if isinstance(item, dict)] != canonical_names:
        raise ScenePropSetEntryDraftError(
            "atlas metadata regions must exactly match the canonical declaration slot order"
        )


def build_scene_prop_set_entry_draft(
    result_path: Path,
    declaration_path: Path,
    *,
    asset_id: str,
    tag: str,
    primary_output: str,
    project_root: Path,
) -> dict[str, Any]:
    """Validate a complete scene-prop-set delivery and build its ready entry."""
    if not asset_id.strip() or not tag.strip() or not primary_output.strip():
        raise ScenePropSetEntryDraftError(
            "--asset-id, --tag, and --primary-output must be non-empty strings"
        )
    result = _load_object(result_path, "asset Skill result")
    declaration = _load_object(declaration_path, "slot declaration")
    if result.get("asset_type") != FAMILY:
        raise ScenePropSetEntryDraftError(f"result.asset_type must be {FAMILY}")
    validation = result.get("validation")
    if not isinstance(validation, dict) or validation.get("passed") is not True:
        raise ScenePropSetEntryDraftError("result must be a passed validation result")
    levels = validation.get("levels")
    if not isinstance(levels, dict) or any(levels.get(level) is not True for level in LEVELS):
        raise ScenePropSetEntryDraftError("result must record passed L0 through L4")
    try:
        check_result(result)
    except AssetContractError as exc:
        raise ScenePropSetEntryDraftError(str(exc)) from exc

    names = _slot_names(declaration)
    if primary_output not in names:
        raise ScenePropSetEntryDraftError("primary output must be a declared slot name")
    atlas_path, metadata_path, _ = _stable_paths(asset_id)
    if result.get("sources") != [{"path": atlas_path, "layout": "region_atlas"}]:
        raise ScenePropSetEntryDraftError("result must expose the one stable region_atlas source")

    outputs = result.get("outputs")
    if not isinstance(outputs, list):
        raise ScenePropSetEntryDraftError("result.outputs must be a list")
    expected = [
        {
            "name": name,
            "role": "runtime",
            "godot_type": "AtlasTexture",
            "path": f"res://{stable_output_dir(FAMILY, asset_id)}/{name}.tres",
        }
        for name in sorted(names)
    ]
    if outputs != expected:
        raise ScenePropSetEntryDraftError(
            "result runtime outputs must exactly match declared scene prop slots"
        )

    _assert_file(project_root, atlas_path, "stable atlas")
    _assert_file(project_root, metadata_path, "atlas metadata")
    _validate_metadata(project_root, metadata_path, atlas_path, names)
    for output in outputs:
        _assert_file(project_root, output["path"], f"runtime output {output['name']}")

    entry = {
        "version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": FAMILY,
        "source_layout": {"type": "region_atlas", "path": atlas_path},
        "godot_artifact": {
            "type": "AtlasTexture",
            "path": f"res://{stable_output_dir(FAMILY, asset_id)}/{primary_output}.tres",
        },
        "processing_status": "ready",
    }
    try:
        validate_entry(entry, project_root=project_root, check_files=True)
    except StableEntryError as exc:
        raise ScenePropSetEntryDraftError(str(exc)) from exc
    return entry


def write_scene_prop_set_entry_draft(
    result_path: Path,
    declaration_path: Path,
    *,
    asset_id: str,
    tag: str,
    primary_output: str,
    project_root: Path,
    out: Path,
) -> dict[str, Any]:
    entry = build_scene_prop_set_entry_draft(
        result_path,
        declaration_path,
        asset_id=asset_id,
        tag=tag,
        primary_output=primary_output,
        project_root=project_root,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "draft": str(out), "entry": entry}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a ready v1 stable-entry draft for a scene-prop-set atlas"
    )
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--declaration", required=True, type=Path)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--primary-output", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = write_scene_prop_set_entry_draft(
            args.result,
            args.declaration,
            asset_id=args.asset_id,
            tag=args.tag,
            primary_output=args.primary_output,
            project_root=args.project_root,
            out=args.out,
        )
    except ScenePropSetEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
