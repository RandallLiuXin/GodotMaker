#!/usr/bin/env python3
"""Register validated Asset Skill results directly in ``ASSETS.md``.

``ASSETS.md`` is the only runtime asset authority.  A successful Asset Skill
result is consumed once, checked as a complete production unit, and then used
to atomically update every declared logical output row.  No stable entry,
manifest pointer, or family-specific adapter participates in this handoff.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from asset_build_record import (
    BuildRecordError,
    assert_validated_artifact,
    read_validation_record,
)
from asset_skill_contract_check import AssetContractError, check_request, check_result
from asset_family_registry import FamilyRegistryError, spec as family_spec, variant_for_request


RUNTIME_STATUS = "generated"
REFERENCE_STATUS = "source_ready"
RUNTIME_HEADERS = (
    "#",
    "Tag",
    "Name",
    "Type",
    "Size",
    "Generation Params",
    "Runtime Type",
    "Runtime Path",
    "Status",
)
_RES_PATH = re.compile(r"^res://(?!.*(?:^|/)\.\.?(/|$))[^/\s]+(?:/[^/\s]+)*$")


class AssetResultRegistrationError(Exception):
    """Raised when a result cannot safely become an ASSETS.md update."""


def _split_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _row(cells: list[str], newline: str) -> str:
    return "| " + " | ".join(cells) + f" |{newline}"


def _newline(line: str, default: str) -> str:
    return "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else default


def _runtime_header(lines: list[str]) -> tuple[int, dict[str, int]]:
    for index, line in enumerate(lines):
        cells = _split_row(line)
        if cells is None:
            continue
        if tuple(cells) == RUNTIME_HEADERS:
            return index, {name: offset for offset, name in enumerate(cells)}
    expected = " | ".join(RUNTIME_HEADERS)
    raise AssetResultRegistrationError(
        "ASSETS.md must contain the runtime table header: " + expected
    )


def _res_to_file(project_root: Path, resource_path: str) -> Path:
    if not isinstance(resource_path, str) or not _RES_PATH.fullmatch(resource_path):
        raise AssetResultRegistrationError(
            f"runtime path must be a clean project-local res:// path: {resource_path!r}"
        )
    candidate = (project_root / resource_path[len("res://") :]).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError as exc:
        raise AssetResultRegistrationError(
            f"runtime path resolves outside the project: {resource_path}"
        ) from exc
    if not candidate.is_file():
        raise AssetResultRegistrationError(f"runtime file is missing: {resource_path}")
    return candidate


def _reference_to_file(project_root: Path, reference_path: str) -> Path:
    """Resolve a reference-only result path without treating it as ``res://``."""
    if (
        not isinstance(reference_path, str)
        or not reference_path
        or reference_path.startswith("res://")
        or Path(reference_path).is_absolute()
    ):
        raise AssetResultRegistrationError(
            "reference path must be a project-local relative path: "
            f"{reference_path!r}"
        )
    candidate = (project_root / reference_path).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError as exc:
        raise AssetResultRegistrationError(
            f"reference path resolves outside the project: {reference_path}"
        ) from exc
    if not candidate.is_file():
        raise AssetResultRegistrationError(f"reference file is missing: {reference_path}")
    return candidate


def _logical_id(output: dict[str, Any], *, single: bool, request_asset_id: str | None) -> str:
    name = output.get("name")
    if isinstance(name, str) and name.strip():
        return name
    if single and isinstance(request_asset_id, str) and request_asset_id.strip():
        return request_asset_id
    raise AssetResultRegistrationError(
        "every output in a multi-output result must have a non-empty logical name"
    )


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AssetResultRegistrationError(f"cannot read {label}: {path}") from exc
    if not isinstance(data, dict):
        raise AssetResultRegistrationError(f"{label} must be a JSON object")
    return data


def _asset_outputs(
    result: dict[str, Any], *, request_asset_id: str | None
) -> dict[str, dict[str, str]]:
    try:
        check_result(result)
    except AssetContractError as exc:
        raise AssetResultRegistrationError(str(exc)) from exc
    if result["validation"].get("passed") is not True:
        raise AssetResultRegistrationError("Asset Skill result validation did not pass")

    try:
        reference_only = family_spec(result["asset_type"]).is_reference_only
    except FamilyRegistryError as exc:
        raise AssetResultRegistrationError(str(exc)) from exc

    # Runtime-family reference outputs are validated production evidence, not
    # logical assets. Reference-only families (currently screen-reference)
    # retain their reference output because it is the asset being registered.
    outputs = [
        output
        for output in result["outputs"]
        if output["role"] == "runtime" or reference_only
    ]
    records: dict[str, dict[str, str]] = {}
    for output in outputs:
        logical_id = _logical_id(
            output, single=len(outputs) == 1, request_asset_id=request_asset_id
        )
        if logical_id in records:
            raise AssetResultRegistrationError(f"duplicate logical output: {logical_id}")
        role = output["role"]
        path = output["path"]
        if role == "runtime":
            records[logical_id] = {
                "role": role,
                "type": output["godot_type"],
                "path": path,
            }
        else:
            records[logical_id] = {"role": role, "type": "reference", "path": path}
    if not records:
        raise AssetResultRegistrationError("a passed Asset Skill result has no outputs")
    return records


def _named_runtime_outputs(
    declarations: Any,
    *,
    family: str,
    declaration_label: str,
    name_key: str,
    godot_type: str,
) -> dict[str, dict[str, str]]:
    """Turn a family's native request declarations into a closed output set."""
    if not isinstance(declarations, list) or not declarations:
        raise AssetResultRegistrationError(
            f"{family} request must declare one or more {declaration_label}"
        )
    declared: dict[str, dict[str, str]] = {}
    for index, item in enumerate(declarations):
        if not isinstance(item, dict):
            raise AssetResultRegistrationError(
                f"{family} {declaration_label}[{index}] must be an object"
            )
        name = item.get(name_key)
        if not isinstance(name, str) or not name.strip():
            raise AssetResultRegistrationError(
                f"{family} {declaration_label}[{index}].{name_key} must be non-empty"
            )
        if name in declared:
            raise AssetResultRegistrationError(
                f"duplicate declared logical output: {name}"
            )
        declared[name] = {"role": "runtime", "type": godot_type}
    return declared


def _merge_declared_outputs(
    target: dict[str, dict[str, str]], source: dict[str, dict[str, str]]
) -> None:
    duplicates = sorted(set(target) & set(source))
    if duplicates:
        raise AssetResultRegistrationError(
            "duplicate declared logical output: " + ", ".join(duplicates)
        )
    target.update(source)


def _native_multi_output_contract(
    request: dict[str, Any], *, allowed_types: set[str]
) -> dict[str, dict[str, str]] | None:
    """Return output declarations already owned by a public family request.

    These families have a strict standalone schema.  Their resource
    declarations are the authoritative output set; adding a parallel
    ``spec.outputs`` list would make standalone validation and registration
    disagree.
    """
    family = request["asset_type"]
    if family not in {"ui-kit", "card-kit", "compact-prop-pack", "platform-strip"}:
        return None
    spec = request.get("spec")
    if not isinstance(spec, dict):
        raise AssetResultRegistrationError(f"{family} request.spec must be an object")
    if family in {"ui-kit", "card-kit"}:
        declared: dict[str, dict[str, str]] = {}
        _merge_declared_outputs(
            declared,
            _named_runtime_outputs(
                spec.get("styleboxes"),
                family=family,
                declaration_label="spec.styleboxes",
                name_key="output_name",
                godot_type="StyleBoxTexture",
            ),
        )
        _merge_declared_outputs(
            declared,
            _named_runtime_outputs(
                spec.get("atlas_regions"),
                family=family,
                declaration_label="spec.atlas_regions",
                name_key="output_name",
                godot_type="AtlasTexture",
            ),
        )
        theme = spec.get("theme")
        if theme is not None:
            if not isinstance(theme, dict):
                raise AssetResultRegistrationError(f"{family} spec.theme must be an object or null")
            _merge_declared_outputs(
                declared,
                _named_runtime_outputs(
                    [theme],
                    family=family,
                    declaration_label="spec.theme",
                    name_key="output_name",
                    godot_type="Theme",
                ),
            )
        return declared
    if family == "compact-prop-pack":
        return _named_runtime_outputs(
            spec.get("slots"),
            family=family,
            declaration_label="spec.slots",
            name_key="name",
            godot_type="AtlasTexture",
        )
    if family == "platform-strip":
        kind = spec.get("kind")
        type_for_kind = {"single": "Texture2D", "atlas": "AtlasTexture"}
        godot_type = type_for_kind.get(kind)
        if godot_type is None or godot_type not in allowed_types:
            raise AssetResultRegistrationError(
                "platform-strip spec.kind must select a supported output type"
            )
        return _named_runtime_outputs(
            spec.get("segments"),
            family=family,
            declaration_label="spec.segments",
            name_key="name",
            godot_type=godot_type,
        )
    return None


def _declared_outputs(request: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Return the complete, request-owned logical output contract.

    A result must never define its own registration set.  Families with native
    fixed-slot/resource declarations derive that set from their request. Other
    multi-output families declare ``spec.outputs`` explicitly.
    """
    family = request["asset_type"]
    try:
        variant = variant_for_request(request)
    except FamilyRegistryError as exc:
        raise AssetResultRegistrationError(str(exc)) from exc
    allowed_types = set(variant.artifact_types)
    output_cardinality = variant.runtime_outputs
    if family == "scene-prop-set":
        return {
            slot["name"]: {"role": "runtime", "type": "AtlasTexture"}
            for slot in request["spec"]["slots"]
        }
    native_contract = _native_multi_output_contract(request, allowed_types=allowed_types)
    if native_contract is not None:
        if "outputs" in request["spec"]:
            raise AssetResultRegistrationError(
                f"{family} derives logical outputs from its native spec; do not add spec.outputs"
            )
        return native_contract
    contract = request.get("spec", {}).get("outputs")
    if contract is None:
        # A single-output family has one unambiguous logical asset. Multi-output
        # families are deliberately not inferred from a result or ASSETS.md.
        if output_cardinality == "one":
            if len(allowed_types) != 1:
                raise AssetResultRegistrationError(
                    f"{family} request must declare output types in spec.outputs"
                )
            return {
                request["asset_id"]: {
                    "role": "runtime", "type": next(iter(allowed_types))
                }
            }
        if output_cardinality == "none":
            return {request["asset_id"]: {"role": "reference", "type": "reference"}}
        raise AssetResultRegistrationError(
            f"{family} request must declare every logical output in spec.outputs"
        )
    if not isinstance(contract, list) or not contract:
        raise AssetResultRegistrationError("request.spec.outputs must be a non-empty list")
    declared: dict[str, dict[str, str]] = {}
    for index, item in enumerate(contract):
        if not isinstance(item, dict):
            raise AssetResultRegistrationError(f"request.spec.outputs[{index}] must be an object")
        name, role = item.get("name"), item.get("role")
        if not isinstance(name, str) or not name.strip():
            raise AssetResultRegistrationError(f"request.spec.outputs[{index}].name must be non-empty")
        if name in declared:
            raise AssetResultRegistrationError(f"duplicate declared logical output: {name}")
        if role == "runtime":
            godot_type = item.get("godot_type")
            if not isinstance(godot_type, str) or godot_type not in allowed_types:
                raise AssetResultRegistrationError(
                    f"request.spec.outputs[{index}].godot_type is not allowed for {family}: {godot_type!r}"
                )
            declared[name] = {"role": role, "type": godot_type}
        elif role == "reference":
            declared[name] = {"role": role, "type": "reference"}
        else:
            raise AssetResultRegistrationError(
                f"request.spec.outputs[{index}].role must be runtime or reference"
            )
    return declared


_VALIDATION_RECORD_FAMILIES = frozenset({"background-map"})


def _assert_validation_record_matches(
    project_root: Path, request: dict[str, Any], outputs: dict[str, dict[str, str]]
) -> None:
    """Require record-writing families to register the exact L0-L4 bytes."""
    family = request["asset_type"]
    if family not in _VALIDATION_RECORD_FAMILIES:
        return
    try:
        record = read_validation_record(
            project_root, production_family=family, asset_id=request["asset_id"]
        )
        runtime_paths = [
            output["path"] for output in outputs.values() if output["role"] == "runtime"
        ]
        if len(runtime_paths) != 1:
            raise AssetResultRegistrationError(
                f"{family} validation record requires exactly one runtime output"
            )
        assert_validated_artifact(
            record, project_root=project_root, artifact_path=runtime_paths[0]
        )
    except BuildRecordError as exc:
        raise AssetResultRegistrationError(str(exc)) from exc


def _godot_loader(godot_path: str, project_root: Path, resource_path: str, expected: str) -> None:
    """Load one resource through Godot and prove its actual class is compatible."""
    import subprocess

    script_dir = project_root / ".godotmaker" / "asset-generation"
    script_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".gd", prefix="check_runtime_type_", dir=script_dir,
        delete=False,
    ) as temporary:
        script = Path(temporary.name)
        temporary.write(
            "extends SceneTree\n"
            "func _init():\n"
            f"    var resource = ResourceLoader.load({json.dumps(resource_path)})\n"
            "    if resource == null:\n"
            f"        push_error(\"could not load {resource_path}\")\n"
            "        quit(2)\n"
            f"    if not resource.is_class({json.dumps(expected)}):\n"
            f"        push_error(\"expected {expected}, got \" + resource.get_class())\n"
            "        quit(3)\n"
            "    quit(0)\n"
        )
    try:
        completed = subprocess.run(
            [godot_path, "--headless", "--path", str(project_root), "--script", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        script.unlink(missing_ok=True)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise AssetResultRegistrationError(
            f"Godot could not load {resource_path} as {expected}: {detail}"
        )


def register_result(
    assets_md: Path,
    result_path: Path,
    *,
    tag: str,
    request_path: Path,
    godot_path: str | None = None,
    loader: Callable[[Path, str, str], None] | None = None,
) -> dict[str, Any]:
    """Atomically record a whole successful result in the canonical table.

    All output identities, matching rows, paths, and (for runtime resources)
    Godot loads are checked before the temporary replacement file is created.
    """
    assets_md = Path(assets_md)
    if not assets_md.is_file():
        raise AssetResultRegistrationError(f"ASSETS.md not found: {assets_md}")
    if not isinstance(tag, str) or not tag.strip():
        raise AssetResultRegistrationError("tag must be a non-empty string")
    project_root = assets_md.parent.resolve()
    request = _load_json(Path(request_path), "Asset Skill request")
    try:
        check_request(request)
    except AssetContractError as exc:
        raise AssetResultRegistrationError(str(exc)) from exc
    request_asset_id = request["asset_id"]

    result = _load_json(Path(result_path), "Asset Skill result")
    outputs = _asset_outputs(result, request_asset_id=request_asset_id)
    if request["asset_type"] != result["asset_type"]:
        raise AssetResultRegistrationError("request and result asset_type do not match")
    expected_outputs = _declared_outputs(request)
    if set(outputs) != set(expected_outputs):
        raise AssetResultRegistrationError(
            "result output set does not match its request declaration: expected "
            + ", ".join(sorted(expected_outputs))
            + "; got "
            + ", ".join(sorted(outputs))
        )
    for logical_id, expected in expected_outputs.items():
        actual = outputs[logical_id]
        if actual["role"] != expected["role"]:
            raise AssetResultRegistrationError(
                f"result output {logical_id} role {actual['role']!r} does not match request {expected['role']!r}"
            )
        if expected["type"] and actual["type"] != expected["type"]:
            raise AssetResultRegistrationError(
                f"result output {logical_id} Godot type {actual['type']!r} does not match request {expected['type']!r}"
            )
    lines = assets_md.read_text(encoding="utf-8").splitlines(keepends=True)
    _, columns = _runtime_header(lines)
    default_newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"

    matches: dict[str, tuple[int, list[str]]] = {}
    for index, line in enumerate(lines):
        cells = _split_row(line)
        if cells is None or len(cells) != len(RUNTIME_HEADERS):
            continue
        if cells[columns["Tag"]] != tag or cells[columns["Name"]] not in outputs:
            continue
        logical_id = cells[columns["Name"]]
        if logical_id in matches:
            raise AssetResultRegistrationError(
                f"ASSETS.md has multiple runtime rows for {tag}/{logical_id}"
            )
        matches[logical_id] = (index, cells)
    missing = sorted(set(outputs) - set(matches))
    if missing:
        raise AssetResultRegistrationError(
            "ASSETS.md has no runtime row for result outputs: " + ", ".join(missing)
        )

    _assert_validation_record_matches(project_root, request, outputs)

    for logical_id, output in outputs.items():
        index, cells = matches[logical_id]
        if cells[columns["Status"]] not in {"MISSING", RUNTIME_STATUS, REFERENCE_STATUS}:
            raise AssetResultRegistrationError(
                f"ASSETS.md row {tag}/{logical_id} has non-promotable status "
                f"{cells[columns['Status']]!r}"
            )
        if output["role"] == "runtime":
            _res_to_file(project_root, output["path"])
            if loader is not None:
                loader(project_root, output["path"], output["type"])
            elif godot_path is None:
                raise AssetResultRegistrationError(
                    "--godot-path is required to register runtime outputs"
                )
            else:
                _godot_loader(godot_path, project_root, output["path"], output["type"])
        else:
            _reference_to_file(project_root, output["path"])

    rewritten = list(lines)
    updated: list[str] = []
    for logical_id, output in outputs.items():
        index, cells = matches[logical_id]
        cells[columns["Runtime Type"]] = output["type"]
        cells[columns["Runtime Path"]] = output["path"]
        cells[columns["Status"]] = (
            RUNTIME_STATUS if output["role"] == "runtime" else REFERENCE_STATUS
        )
        rewritten[index] = _row(cells, _newline(lines[index], default_newline))
        updated.append(logical_id)

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", dir=assets_md.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.writelines(rewritten)
    try:
        temporary.replace(assets_md)
    finally:
        temporary.unlink(missing_ok=True)
    return {"ok": True, "updated": updated, "tag": tag}


def runtime_snapshot(assets_md: Path, *, tag: str, asset_ids: list[str]) -> list[dict[str, Any]]:
    """Return the minimal worker handoff directly from generated ASSETS.md rows."""
    lines = Path(assets_md).read_text(encoding="utf-8").splitlines()
    _, columns = _runtime_header(lines)
    requested = set(asset_ids)
    snapshots: dict[str, dict[str, Any]] = {}
    for line in lines:
        cells = _split_row(line)
        if cells is None or len(cells) != len(RUNTIME_HEADERS):
            continue
        asset_id = cells[columns["Name"]]
        if cells[columns["Tag"]] != tag or asset_id not in requested:
            continue
        if asset_id in snapshots:
            raise AssetResultRegistrationError(f"ASSETS.md has multiple runtime rows for {tag}/{asset_id}")
        status = cells[columns["Status"]]
        runtime_type = cells[columns["Runtime Type"]]
        runtime_path = cells[columns["Runtime Path"]]
        if status != RUNTIME_STATUS:
            raise AssetResultRegistrationError(f"ASSETS.md row {tag}/{asset_id} is {status!r}; expected generated")
        if runtime_type in {"", "-", "reference"}:
            raise AssetResultRegistrationError(f"ASSETS.md row {tag}/{asset_id} is not a runtime resource")
        _res_to_file(Path(assets_md).parent.resolve(), runtime_path)
        snapshots[asset_id] = {"asset_id": asset_id, "godot_artifact": {"type": runtime_type, "path": runtime_path}}
    missing = sorted(requested - set(snapshots))
    if missing:
        raise AssetResultRegistrationError("ASSETS.md runtime rows not found: " + ", ".join(missing))
    return [snapshots[asset_id] for asset_id in asset_ids]


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-md", default="ASSETS.md", type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--godot-path")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--asset-id", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.snapshot:
            if args.result is not None or not args.asset_id:
                raise AssetResultRegistrationError("--snapshot requires --asset-id and does not accept --result")
            payload: Any = runtime_snapshot(args.assets_md, tag=args.tag, asset_ids=args.asset_id)
        else:
            if args.result is None or args.request is None:
                raise AssetResultRegistrationError("--result and --request are required when registering")
            payload = register_result(args.assets_md, args.result, tag=args.tag, request_path=args.request, godot_path=args.godot_path)
    except AssetResultRegistrationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
