"""Executable standalone L0-L4 validation for the UI and card Asset Skills."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from typing import Any

from asset_compiler import CompileRequest, CompilerError, build_default_registry, theme
from asset_compiler._asset_paths import RuntimeContractError, assert_within_output_dir, resolve_res_path
from asset_validation import GodotProbe, ProbeRequest, ValidationError, build_default_structures
from asset_validation._bridge import prefer_console_godot_path
from asset_validation.structure import StructureRequest
from asset_skill_contract_check import AssetContractError, check_result
from asset_ui_card_contract_check import UICardContractError, check_ui_card_handoff, validate_ui_reference_inputs
from asset_ui_stylebox_plan import UIStyleBoxPlanError, validate_stylebox_plan


class UICardSkillError(Exception):
    """Raised when a standalone UI/card request-result pair cannot enter L0."""


_LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")


def _mapped_result(result: Mapping[str, Any], levels: Mapping[str, bool], *, error: str | None = None) -> dict[str, Any]:
    mapped = deepcopy(dict(result))
    mapped["validation"] = {"passed": all(levels.values()), "levels": dict(levels)}
    if error:
        mapped["validation"]["notes"] = error
    try:
        check_result(mapped)
    except AssetContractError as exc:  # protected by L0
        raise UICardSkillError(f"cannot map standalone validation result: {exc}") from exc
    return mapped


def _failure(result: Mapping[str, Any], passed: list[str], level: str, error: Exception) -> dict[str, Any]:
    levels = {name: name in passed for name in _LEVELS}
    levels[level] = False
    return _mapped_result(result, levels, error=f"{level} failed: {error}")


def _artifact_request(
    *, request: Mapping[str, Any], output: Mapping[str, Any], kind: str, declaration: Mapping[str, Any], root: Path
) -> CompileRequest:
    if kind == "theme":
        return CompileRequest(
            production_family=request["asset_type"], asset_id=request["asset_id"],
            source_layout_type="theme_recipe", source_path=declaration["recipe_path"],
            artifact_type="Theme", artifact_path=output["path"], project_root=root,
            spec={
                "variation": declaration["variation"],
                "allowed_external_stylebox_paths": declaration["allowed_external_stylebox_paths"],
            },
        )
    if kind == "stylebox":
        return CompileRequest(
            production_family=request["asset_type"], asset_id=request["asset_id"],
            source_layout_type=declaration["layout"], source_path=declaration["source_path"],
            artifact_type="StyleBoxTexture", artifact_path=output["path"], project_root=root,
            spec=declaration["compiler_spec"],
        )
    return CompileRequest(
        production_family=request["asset_type"], asset_id=request["asset_id"],
        source_layout_type="region_atlas", source_path=declaration["source_path"],
        artifact_type="AtlasTexture", artifact_path=output["path"], project_root=root,
        spec={"metadata_path": declaration["metadata_path"], "logical_asset_id": declaration["logical_asset_id"]},
    )


def _l1_paths(spec: Mapping[str, Any]) -> list[str]:
    paths: list[str] = []
    theme_declaration = spec["theme"]
    if theme_declaration is not None:
        paths.append(theme_declaration["recipe_path"])
    if isinstance(spec.get("stylebox_plan_path"), str):
        paths.append(spec["stylebox_plan_path"])
    for box in spec["styleboxes"]:
        paths.append(box["source_path"])
    for region in spec["atlas_regions"]:
        paths.extend((region["source_path"], region["metadata_path"]))
    return paths


def _run_consumer_smoke(
    root: Path,
    godot_path: str,
    theme_path: str,
    styleboxes: list[Mapping[str, Any]],
) -> None:
    """Bind the generated Theme to representative Controls without creating art."""
    script = root / ".godotmaker" / "ui-card-consumer-smoke.gd"
    script.parent.mkdir(parents=True, exist_ok=True)
    for box in styleboxes:
        margins = box["compiler_spec"].get("content_margin", [])
        for width, height in box.get("preview_sizes", []):
            if margins[0] + margins[2] > width or margins[1] + margins[3] > height:
                raise ValidationError(
                    f"StyleBox content margins exceed preview size for {box['output_name']!r}"
                )
    script.write_text(
        "extends SceneTree\n"
        "func _initialize():\n"
        f"    var theme = load(\"{theme_path}\") as Theme\n"
        "    if theme == null:\n"
        "        push_error(\"UI consumer could not load Theme\")\n"
        "        quit(1)\n"
        "        return\n"
        "    var controls = [Button.new(), Panel.new(), PanelContainer.new(), LineEdit.new(), TextEdit.new(), ProgressBar.new(), TabBar.new(), TabContainer.new(), CheckBox.new(), CheckButton.new(), HSlider.new(), VSlider.new(), HScrollBar.new(), VScrollBar.new(), OptionButton.new()]\n"
        "    for control in controls:\n"
        "        control.theme = theme\n"
        "        root.add_child(control)\n"
        "        for target_size in [Vector2(240, 72), Vector2(520, 240)]:\n"
        "            control.custom_minimum_size = target_size\n"
        "            control.size = target_size\n"
        "        root.remove_child(control)\n"
        "        control.free()\n"
        "    print(\"UI_CARD_CONSUMER_SMOKE_OK\")\n"
        "    quit()\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [prefer_console_godot_path(godot_path), "--headless", "--path", str(root), "--script", str(script)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if completed.returncode != 0 or "UI_CARD_CONSUMER_SMOKE_OK" not in completed.stdout:
        details = (completed.stdout + "\n" + completed.stderr).strip()
        raise ValidationError(f"UI consumer smoke failed: {details or completed.returncode}")


def compile_and_validate(
    request: Mapping[str, Any], result: Mapping[str, Any], *, project_root: Path, godot_path: str,
    expected_family: str | None = None,
) -> dict[str, Any]:
    """Compile and validate every declared standalone UI/card resource.

    No runtime record, manifest, tag, or compiler receipt from another caller is
    used. The request owns all family declarations; this invocation builds its
    own registry and probes every runtime output returned to the caller.
    """
    try:
        handoff = check_ui_card_handoff(request, result)
        if expected_family is not None and (
            request["asset_type"] != expected_family
            or result["asset_type"] != expected_family
        ):
            raise UICardSkillError(
                f"standalone adapter requires asset_type {expected_family!r}"
            )
        spec = handoff["request"]["spec"]
        if not isinstance(spec, Mapping):
            raise UICardSkillError("family contract returned no normalized spec")
    except (UICardContractError, AssetContractError, UICardSkillError) as exc:
        raise UICardSkillError(f"L0 standalone contract failed: {exc}") from exc

    root = Path(project_root)
    passed = ["L0"]
    try:
        validate_ui_reference_inputs(request, root)
        for path in _l1_paths(spec):
            file_path = assert_within_output_dir(
                root, resolve_res_path(root, path, label="declared standalone source"),
                production_family=request["asset_type"], asset_id=request["asset_id"],
                label="declared standalone source",
            )
            if not file_path.is_file() or file_path.stat().st_size <= 0:
                raise ValidationError(f"declared standalone source is not a non-empty file: {path}")
        if request["asset_type"] == "ui-kit":
            plan_path = resolve_res_path(root, spec["stylebox_plan_path"], label="stylebox plan")
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            checked_plan = validate_stylebox_plan(
                plan, request["spec"]["styleboxes"], asset_id=request["asset_id"]
            )
            declared_sources = {
                source["path"] for source in result["sources"] if source.get("layout") == "region_atlas"
            }
            for atlas in checked_plan["inspected_atlases"]:
                if atlas["path"] not in declared_sources:
                    raise ValidationError(
                        f"inspected atlas is not a declared region_atlas source: {atlas['path']}"
                    )
    except (OSError, ValueError, RuntimeContractError, ValidationError, UICardContractError, UIStyleBoxPlanError) as exc:
        return _failure(result, passed, "L1", exc)

    passed.append("L1")
    runtime = {output["name"]: output for output in result["outputs"] if output["role"] == "runtime"}
    declarations: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
    declarations.extend(("stylebox", box, runtime[box["output_name"]]) for box in spec["styleboxes"])
    declarations.extend(("atlas", region, runtime[region["output_name"]]) for region in spec["atlas_regions"])
    theme_declaration = spec["theme"]
    if theme_declaration is not None:
        declarations.append((
            "theme",
            {
                **theme_declaration,
                "allowed_external_stylebox_paths": [
                    runtime[box["output_name"]]["path"] for box in spec["styleboxes"]
                ],
            },
            runtime[theme_declaration["output_name"]],
        ))
    compiled_requests: dict[str, CompileRequest] = {}
    try:
        registry = build_default_registry()
        theme.register_into(registry)
        for kind, declaration, output in declarations:
            compile_request = _artifact_request(
                request=request, output=output, kind=kind, declaration=declaration, root=root
            )
            compiled = registry.compile(compile_request)
            if compiled.godot_artifact.to_dict() != {"type": output["godot_type"], "path": output["path"]}:
                raise ValidationError(f"compiler output does not match declared runtime output {output['name']!r}")
            compiled_requests[output["path"]] = compile_request
    except (CompilerError, OSError, ValidationError) as exc:
        return _failure(result, passed, "L2", exc)

    passed.append("L2")
    structures = build_default_structures()
    theme.register_structure_into(structures)
    try:
        probe_requests = [
            ProbeRequest(res_path=output["path"], expected_type=output["godot_type"], checks=structures.checks_for(output["godot_type"]))
            for output in runtime.values()
        ]
        report = GodotProbe(godot_path).probe(root, probe_requests)
        loaded_by_path = {item.res_path: item for item in report.resources}
        for output in runtime.values():
            loaded = loaded_by_path.get(output["path"])
            if loaded is None or not loaded.loaded or not loaded.type_matches:
                raise ValidationError(
                    (loaded.error if loaded is not None else None)
                    or f"Godot did not load {output['path']} as {output['godot_type']}"
                )
    except ValidationError as exc:
        return _failure(result, passed, "L3", exc)

    passed.append("L3")
    try:
        for output in runtime.values():
            compiled = compiled_requests[output["path"]]
            structures.validate(
                StructureRequest(
                    production_family=compiled.production_family, asset_id=compiled.asset_id,
                    source_layout_type=compiled.source_layout_type, source_path=compiled.source_path,
                    artifact_type=compiled.artifact_type, artifact_path=compiled.artifact_path,
                    project_root=root, probe=loaded_by_path[output["path"]], spec=compiled.spec,
                )
            )
    except ValidationError as exc:
        return _failure(result, passed, "L4", exc)
    passed.append("L4")
    theme_declaration = spec["theme"]
    if theme_declaration is None:
        return _mapped_result(result, {level: True for level in _LEVELS if level != "L5"})
    try:
        _run_consumer_smoke(
            root,
            godot_path,
            runtime[theme_declaration["output_name"]]["path"],
            spec["styleboxes"],
        )
    except (OSError, subprocess.SubprocessError, ValidationError) as exc:
        return _failure(result, passed, "L5", exc)
    return _mapped_result(result, {level: True for level in _LEVELS})
