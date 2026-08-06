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

from asset_skill_contract_check import AssetContractError, check_request, check_result


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

    outputs = result["outputs"]
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


def _declared_output_ids(request: dict[str, Any], outputs: dict[str, dict[str, str]]) -> set[str]:
    """Return the logical outputs explicitly enumerated by a request.

    A scene-prop-set slot declaration names every independently consumable
    resource. Other multi-output families deliberately leave naming to the
    Skill result, while a single-output request declares its ``asset_id``.
    """
    if request["asset_type"] == "scene-prop-set":
        return {slot["name"] for slot in request["spec"]["slots"]}
    if len(outputs) == 1:
        return {request["asset_id"]}
    return set(outputs)


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
    expected_outputs = _declared_output_ids(request, outputs)
    if set(outputs) != expected_outputs:
        raise AssetResultRegistrationError(
            "result output set does not match its request declaration: expected "
            + ", ".join(sorted(expected_outputs))
            + "; got "
            + ", ".join(sorted(outputs))
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

    for logical_id, output in outputs.items():
        _res_to_file(project_root, output["path"])
        index, cells = matches[logical_id]
        if cells[columns["Status"]] not in {"MISSING", RUNTIME_STATUS, REFERENCE_STATUS}:
            raise AssetResultRegistrationError(
                f"ASSETS.md row {tag}/{logical_id} has non-promotable status "
                f"{cells[columns['Status']]!r}"
            )
        if output["role"] == "runtime":
            if loader is not None:
                loader(project_root, output["path"], output["type"])
            elif godot_path is None:
                raise AssetResultRegistrationError(
                    "--godot-path is required to register runtime outputs"
                )
            else:
                _godot_loader(godot_path, project_root, output["path"], output["type"])

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
