"""Public contracts and real SpriteFrames handoff for animated bundle skills."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(SHARED_DIR))

from asset_animated_bundle_contract_check import (  # noqa: E402
    AnimatedBundleContractError,
    build_spriteframes_spec,
    check_bundle_handoff,
    check_bundle_request,
    check_bundle_result,
)
from asset_compiler import CompileRequest, build_default_registry  # noqa: E402


def _fixture(family: str, name: str) -> dict:
    path = REPO_ROOT / "skills" / "assets" / family / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _character_request() -> dict:
    return _fixture("character-bundle", "valid-request.json")


def _resolved_character_request() -> dict:
    return _fixture("character-bundle", "valid-resolved-request.json")


def _fx_request() -> dict:
    return _fixture("fx-bundle", "animated-request.json")


def test_character_fixture_has_a_valid_high_level_public_contract():
    request = _character_request()
    result = _fixture("character-bundle", "valid-result.json")

    assert check_bundle_request(request)["asset_type"] == "character-bundle"
    assert check_bundle_result(result)["asset_type"] == "character-bundle"
    assert check_bundle_handoff(request, result)["kind"] == "handoff"
    assert [action["name"] for action in request["spec"]["actions"]] == ["idle", "attack"]
    assert "required_actions" not in request["spec"]
    assert "frame_names" not in request["spec"]["actions"][0]
    assert request["spec"]["actions"][1]["loop"] is False


def test_character_resolved_request_retains_the_compiler_boundary():
    request = _resolved_character_request()

    assert check_bundle_request(request)["asset_type"] == "character-bundle"
    assert request["spec"]["required_actions"] == ["idle", "attack"]
    assert request["spec"]["frame_canvas_px"] == 256
    assert request["spec"]["actions"][1]["intent"] == _character_request()["spec"]["actions"][1]["intent"]


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d["spec"].pop("actions"), id="missing-actions"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(intent=""), id="empty-intent"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frames=8), id="caller-frame-count"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(fps=8), id="caller-fps"),
        pytest.param(lambda d: d["spec"].update(frame_canvas_px=192), id="non-power-of-two-canvas"),
    ],
)
def test_character_public_request_keeps_animation_resolution_inside_the_skill(mutate):
    request = _character_request()
    mutate(request)
    with pytest.raises(AnimatedBundleContractError):
        check_bundle_request(request)


def test_family_contract_checker_cli_validates_the_public_fixture(tmp_path):
    fixture = REPO_ROOT / "skills/assets/fx-bundle/fixtures/animated-request.json"
    process = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/asset_animated_bundle_contract_check.py"),
            str(fixture),
            "--kind",
            "request",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0
    assert json.loads(process.stdout)["asset_type"] == "fx-bundle"

    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    result_path.write_text(
        (REPO_ROOT / "skills/assets/fx-bundle/fixtures/animated-result.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    handoff = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/asset_animated_bundle_contract_check.py"),
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert handoff.returncode == 0
    assert json.loads(handoff.stdout)["kind"] == "handoff"


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d["spec"].pop("required_actions"), id="missing-required-actions"),
        pytest.param(lambda d: d["spec"].update(required_actions=["idle", "idle"]), id="duplicate-required-action"),
        pytest.param(lambda d: d["spec"]["actions"][1].update(name="idle"), id="duplicate-action-name"),
        pytest.param(lambda d: d["spec"]["actions"][1].update(name="walk"), id="unexpected-action"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frame_names=[]), id="missing-frames"),
        pytest.param(lambda d: d["spec"]["actions"][0].pop("grid"), id="missing-grid"),
        pytest.param(lambda d: d["spec"]["actions"][0].pop("intent"), id="missing-intent"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(grid={"columns": 3, "rows": 1}), id="grid-frame-mismatch"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frame_names=["idle", "idle"]), id="duplicate-frame-name"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(fps=0), id="non-positive-fps"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(loop="true"), id="non-boolean-loop"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frame_durations=[1]), id="duration-count-mismatch"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frame_durations=[1, 0]), id="non-positive-duration"),
        pytest.param(lambda d: d["spec"].update(extra=True), id="unknown-spec-field"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(extra=True), id="unknown-action-field"),
    ],
)
def test_character_request_rejects_every_declared_action_boundary(mutate):
    request = _resolved_character_request()
    mutate(request)
    with pytest.raises(AnimatedBundleContractError):
        check_bundle_request(request)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d["outputs"][0].update(godot_type="Texture2D"), id="no-spriteframes"),
        pytest.param(lambda d: d["outputs"].append({"role": "runtime", "path": "res://assets/generated/character-bundle/player/other.tres", "godot_type": "SpriteFrames"}), id="two-spriteframes"),
        pytest.param(lambda d: [source.update(layout="single") for source in d["sources"]], id="non-grid-sheet-source"),
    ],
)
def test_character_result_rejects_an_ambiguous_runtime_handoff(mutate):
    result = _fixture("character-bundle", "valid-result.json")
    mutate(result)
    with pytest.raises(AnimatedBundleContractError):
        check_bundle_result(result)


def test_fx_fixture_reaches_the_real_spriteframes_compiler_through_public_handoff(tmp_path):
    request = _fx_request()
    action = request["spec"]["actions"][0]
    output = tmp_path / "assets/generated/fx-bundle/impact"
    output.mkdir(parents=True)
    (output / "impact_sheet.png").touch()
    frame_paths = []
    for frame_name in action["frame_names"]:
        frame = output / f"{frame_name}.png"
        frame.touch()
        frame_paths.append(f"res://assets/generated/fx-bundle/impact/{frame.name}")

    spec = build_spriteframes_spec(request, {"impact": frame_paths})
    compiled = build_default_registry().compile(
        CompileRequest(
            production_family="fx-bundle",
            asset_id="impact",
            source_layout_type="grid_sheet",
            source_path="res://assets/generated/fx-bundle/impact/impact_sheet.png",
            artifact_type="SpriteFrames",
            artifact_path="res://assets/generated/fx-bundle/impact/impact.tres",
            project_root=tmp_path,
            spec=spec,
        )
    )

    assert spec["required_actions"] == ["impact"]
    assert compiled.godot_artifact.type == "SpriteFrames"
    assert '"loop": false' in (output / "impact.tres").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d["spec"].pop("mode"), id="missing-mode"),
        pytest.param(lambda d: d["spec"].update(mode="looping"), id="unknown-mode"),
        pytest.param(lambda d: d["spec"].pop("required_actions"), id="missing-required-actions"),
        pytest.param(lambda d: d["spec"].update(required_actions=["impact", "flash"]), id="multiple-required-actions"),
        pytest.param(lambda d: d["spec"]["actions"].append(copy.deepcopy(d["spec"]["actions"][0])), id="multiple-actions"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(name="flash"), id="mismatched-action-name"),
        pytest.param(lambda d: d["spec"]["actions"][0].pop("grid"), id="missing-grid"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(grid={"columns": 2, "rows": 1}), id="grid-frame-mismatch"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frame_names=[]), id="missing-frames"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frame_names=["impact", "impact"]), id="duplicate-frame-name"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(fps=0), id="non-positive-fps"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(loop="false"), id="non-boolean-loop"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frame_durations=[1]), id="duration-count-mismatch"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frame_durations=[1, 0, 1]), id="non-positive-duration"),
        pytest.param(lambda d: d["spec"].update(extra=True), id="unknown-spec-field"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(extra=True), id="unknown-action-field"),
    ],
)
def test_animated_fx_request_rejects_every_declared_action_boundary(mutate):
    request = _fx_request()
    mutate(request)
    with pytest.raises(AnimatedBundleContractError):
        check_bundle_request(request)


def test_static_fx_rejects_animation_fields_and_keeps_its_texture_result_boundary():
    request = _fixture("fx-bundle", "static-request.json")
    result = _fixture("fx-bundle", "static-result.json")
    assert check_bundle_request(request)["asset_type"] == "fx-bundle"
    assert check_bundle_result(result)["asset_type"] == "fx-bundle"
    assert check_bundle_handoff(request, result)["kind"] == "handoff"

    request["spec"]["actions"] = []
    with pytest.raises(AnimatedBundleContractError, match="not allowed for a static"):
        check_bundle_request(request)


def test_fx_skill_keeps_static_autoslice_and_animated_grid_paths_separate():
    skill = (REPO_ROOT / "skills/assets/fx-bundle/SKILL.md").read_text(encoding="utf-8")

    assert "--snap-mode autoslice" in skill
    assert "Do not supply\n`--grid` to autoslice" in skill
    assert "semantically form one effect" in skill
    assert "needs_regeneration" in skill
    assert "Animation\nnever uses autoslice" in skill
    assert "--align center" in skill


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d["outputs"].append(copy.deepcopy(d["outputs"][0])), id="multiple-runtime-outputs"),
        pytest.param(lambda d: d["outputs"][0].update(godot_type="Theme"), id="unsupported-runtime-type"),
        pytest.param(lambda d: d["sources"][0].update(layout="grid_sheet"), id="static-layout-mismatch"),
    ],
)
def test_fx_result_rejects_unsupported_or_ambiguous_runtime_handoff(mutate):
    result = _fixture("fx-bundle", "static-result.json")
    mutate(result)
    with pytest.raises(AnimatedBundleContractError):
        check_bundle_result(result)


@pytest.mark.parametrize(
    ("request_name", "result_name", "mutate"),
    [
        pytest.param(
            "animated-request.json",
            "animated-result.json",
            lambda d: (
                d["outputs"][0].update(godot_type="Texture2D", path="res://assets/generated/fx-bundle/impact/impact.png"),
                d["sources"][0].update(path="res://assets/generated/fx-bundle/impact/impact.png", layout="single"),
            ),
            id="animated-to-texture2d",
        ),
        pytest.param(
            "static-request.json",
            "static-result.json",
            lambda d: (
                d["outputs"][0].update(godot_type="SpriteFrames", path="res://assets/generated/fx-bundle/pickup/pickup.tres"),
                d["sources"][0].update(path="res://assets/generated/fx-bundle/pickup/pickup_sheet.png", layout="grid_sheet"),
            ),
            id="static-to-spriteframes",
        ),
    ],
)
def test_fx_handoff_rejects_result_that_bypasses_request_mode(request_name, result_name, mutate):
    request = _fixture("fx-bundle", request_name)
    result = _fixture("fx-bundle", result_name)
    mutate(result)
    with pytest.raises(AnimatedBundleContractError):
        check_bundle_handoff(request, result)


@pytest.mark.parametrize(
    "validation",
    [
        pytest.param(
            {"passed": False, "levels": {"L0": True, "L1": True, "L2": True, "L3": False, "L4": False}},
            id="passed-false",
        ),
        pytest.param({"passed": True}, id="missing-levels"),
        pytest.param(
            {"passed": False, "levels": {"L0": True, "L1": True, "L2": True, "L3": False, "L4": True}},
            id="l3-false",
        ),
        pytest.param(
            {"passed": False, "levels": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": False}},
            id="l4-false",
        ),
    ],
)
def test_runtime_handoff_rejects_non_ready_l0_to_l4_validation(validation):
    request = _fx_request()
    result = _fixture("fx-bundle", "animated-result.json")
    result["validation"] = validation
    with pytest.raises(AnimatedBundleContractError):
        check_bundle_handoff(request, result)


@pytest.mark.parametrize(
    "validation",
    [
        pytest.param({"passed": False, "levels": {"L0": False}}, id="passed-false"),
        pytest.param({"passed": True}, id="missing-levels"),
        pytest.param({"passed": False, "levels": {"L3": False}}, id="l3-false"),
        pytest.param({"passed": False, "levels": {"L4": False}}, id="l4-false"),
    ],
)
def test_handoff_cli_rejects_non_ready_validation(tmp_path, validation):
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(_fx_request()), encoding="utf-8")
    result = _fixture("fx-bundle", "animated-result.json")
    result["validation"] = validation
    result_path.write_text(json.dumps(result), encoding="utf-8")

    process = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools/asset_animated_bundle_contract_check.py"),
            "--request",
            str(request_path),
            "--result",
            str(result_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 1
    assert json.loads(process.stdout)["ok"] is False


@pytest.mark.parametrize("family", ["character-bundle", "fx-bundle"])
def test_animated_skills_name_the_callable_family_validation_path(family):
    skill = (REPO_ROOT / "skills" / "assets" / family / "SKILL.md").read_text(encoding="utf-8")
    assert "asset_animated_bundle_contract_check.py" in skill
    assert "ASSETS.md" in skill
    assert "manifests" in skill
