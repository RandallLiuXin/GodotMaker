#!/usr/bin/env python3
"""Build ready v1 entries for one validated ui-kit or card-kit delivery.

A UI or card kit compiles one physical production into many independently
worker-consumable resources: a `Theme`, one `StyleBoxTexture` per declared
frame/state, and one `AtlasTexture` per declared region. Each of those is bound
by a different node, so each receives its own stable entry rather than hiding
behind a single primary artifact a worker would have to guess paths around.

The entries share the kit's physical directory, so they carry the kit's
`bundle_id` and a `<bundle_id>--<output_name>` `asset_id`, exactly as a compact
prop bundle does.

`check_ui_card_handoff` owns the request-to-result binding: it proves every
declared stylebox and region became a runtime output of the right Godot type,
that each one's source is really in the result, that a declared Theme compiled
to the kit's stable Theme path, and that the result publishes nothing
undeclared. This adapter adds what registration needs on top: a passing L0-L4
ladder, real files, and one v1 entry per runtime output.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from asset_stable_entry import (
    SCHEMA_VERSION,
    StableEntryError,
    safe_identifier,
    stable_output_dir,
    validate_entry,
)
from asset_ui_card_contract_check import (
    UICardContractError,
    check_ui_card_handoff,
    check_ui_card_request,
)

FAMILIES = ("ui-kit", "card-kit")
LEVELS = ("L0", "L1", "L2", "L3", "L4")

# ``theme_recipe`` is the only layout that compiles to a Theme, and an atlas
# region is always cut from a ``region_atlas``. A stylebox declares its own
# layout, which the stable-entry schema then checks against StyleBoxTexture.
ARTIFACT_LAYOUTS = {"Theme": "theme_recipe", "AtlasTexture": "region_atlas"}


class UICardEntryDraftError(Exception):
    """Raised when a ui-kit or card-kit result cannot become ready entries."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UICardEntryDraftError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise UICardEntryDraftError(f"{label} must be a JSON object: {path}")
    return value


def _assert_passed_ladder(result: dict[str, Any]) -> None:
    """Require an explicitly passing L0-L4 ladder.

    L5 is a consumer smoke the family runs only when it built a Theme, so it is
    read when present and never required: a card kit without a Theme legitimately
    reports no L5 at all.
    """
    validation = result["validation"]
    levels = validation.get("levels")
    if validation.get("passed") is not True or not isinstance(levels, dict):
        raise UICardEntryDraftError(
            "result must report explicit passing validation levels before ready "
            "entries are drafted"
        )
    missing = [level for level in LEVELS if levels.get(level) is not True]
    if missing:
        raise UICardEntryDraftError(
            "result must have passed L0-L4 before ready entries are drafted; "
            f"not passing: {', '.join(missing)}"
        )
    if levels.get("L5") is False:
        raise UICardEntryDraftError("result reports a failed L5 consumer check")


def _source_layout_by_output(request: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Map each declared runtime output name to its (layout type, source path)."""
    spec = request["spec"]
    layouts: dict[str, tuple[str, str]] = {}
    theme = spec.get("theme")
    if theme is not None:
        layouts[theme["output_name"]] = (
            ARTIFACT_LAYOUTS["Theme"],
            theme["recipe_path"],
        )
    for box in spec["styleboxes"]:
        layouts[box["output_name"]] = (box["layout"], box["source_path"])
    for region in spec["atlas_regions"]:
        layouts[region["output_name"]] = (
            ARTIFACT_LAYOUTS["AtlasTexture"],
            region["source_path"],
        )
    return layouts


def logical_outputs(request: dict[str, Any]) -> list[tuple[str, str]]:
    """Return every declared runtime output as ``(output_name, godot_type)``.

    The names come from the request, not from a finished result, so the manager
    can declare the ASSETS.md rows a kit will fill before its Skill runs. Order
    is declaration order: Theme, then styleboxes, then atlas regions.
    """
    try:
        check_ui_card_request(request)
    except UICardContractError as exc:
        raise UICardEntryDraftError(str(exc)) from exc
    spec = request["spec"]
    outputs: list[tuple[str, str]] = []
    theme = spec.get("theme")
    if theme is not None:
        outputs.append((theme["output_name"], "Theme"))
    outputs.extend((box["output_name"], "StyleBoxTexture") for box in spec["styleboxes"])
    outputs.extend(
        (region["output_name"], "AtlasTexture") for region in spec["atlas_regions"]
    )
    return outputs


def _assert_file(project_root: Path, res_path: str, label: str) -> None:
    target = Path(project_root) / res_path[len("res://"):]
    if not target.is_file() or target.stat().st_size <= 0:
        raise UICardEntryDraftError(f"{label} is missing or empty: {res_path}")


def build_ui_card_entry_drafts(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    project_root: Path,
    check_files: bool = True,
) -> list[dict[str, Any]]:
    """Return one ready entry per runtime output in a validated kit delivery."""
    request = _load_object(request_path, "request")
    result = _load_object(result_path, "asset Skill result")
    if request.get("asset_type") not in FAMILIES or result.get(
        "asset_type"
    ) != request.get("asset_type"):
        raise UICardEntryDraftError(
            "request and result must both be the same ui-kit or card-kit delivery"
        )
    try:
        check_ui_card_handoff(request, result)
    except UICardContractError as exc:
        raise UICardEntryDraftError(str(exc)) from exc
    if not isinstance(tag, str) or not tag.strip():
        raise UICardEntryDraftError("--tag must be a non-empty string")
    _assert_passed_ladder(result)

    family = request["asset_type"]
    bundle_id = request["asset_id"]
    directory = stable_output_dir(family, bundle_id)
    layouts = _source_layout_by_output(request)

    entries: list[dict[str, Any]] = []
    for output in result["outputs"]:
        if output.get("role") != "runtime":
            continue
        name = output["name"]
        try:
            safe_identifier(name, f"runtime output {name!r} name")
        except StableEntryError as exc:
            raise UICardEntryDraftError(str(exc)) from exc
        if name not in layouts:
            raise UICardEntryDraftError(
                f"runtime output {name!r} has no declared source in the request"
            )
        layout_type, source_path = layouts[name]
        artifact_path = output["path"]
        if not artifact_path.startswith(f"res://{directory}/"):
            raise UICardEntryDraftError(
                f"runtime output {name!r} must be published under res://{directory}/"
            )
        if check_files:
            _assert_file(project_root, source_path, f"{name} source")
            _assert_file(project_root, artifact_path, f"{name} runtime artifact")
        entry = {
            "version": SCHEMA_VERSION,
            "asset_id": f"{bundle_id}--{name}",
            "tag": tag,
            "production_family": family,
            "bundle_id": bundle_id,
            "source_layout": {"type": layout_type, "path": source_path},
            "godot_artifact": {"type": output["godot_type"], "path": artifact_path},
            "processing_status": "ready",
        }
        try:
            validate_entry(
                entry, project_root=Path(project_root), check_files=check_files
            )
        except StableEntryError as exc:
            raise UICardEntryDraftError(str(exc)) from exc
        entries.append(entry)

    if not entries:
        raise UICardEntryDraftError("result publishes no runtime output to register")
    return entries


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False, dir=str(path.parent), suffix=".json"
    ) as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_ui_card_entry_drafts(
    request_path: Path,
    result_path: Path,
    *,
    tag: str,
    project_root: Path,
    out_dir: Path,
    check_files: bool = True,
) -> dict[str, Any]:
    entries = build_ui_card_entry_drafts(
        request_path,
        result_path,
        tag=tag,
        project_root=project_root,
        check_files=check_files,
    )
    drafts: list[str] = []
    for entry in entries:
        path = Path(out_dir) / f"{entry['asset_id']}.json"
        _atomic_write_json(path, entry)
        drafts.append(str(path))
    return {"ok": True, "count": len(entries), "drafts": drafts}


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build ready stable-entry drafts for a ui-kit or card-kit delivery"
    )
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--no-check-files",
        action="store_true",
        help="Only validate declared paths; do not require sources and .tres files",
    )
    args = parser.parse_args()
    try:
        payload = write_ui_card_entry_drafts(
            args.request,
            args.result,
            tag=args.tag,
            project_root=args.project_root,
            out_dir=args.out_dir,
            check_files=not args.no_check_files,
        )
    except UICardEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
