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
    check_bundle_request,
    check_bundle_result,
)
from asset_compiler import CompileRequest, build_default_registry  # noqa: E402


def _fixture(family: str, name: str) -> dict:
    path = REPO_ROOT / "skills" / "assets" / family / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _character_request() -> dict:
    return _fixture("character-bundle", "valid-request.json")


def _fx_request() -> dict:
    return _fixture("fx-bundle", "animated-request.json")


def test_character_fixture_has_a_valid_multi_action_public_contract():
    request = _character_request()
    result = _fixture("character-bundle", "valid-result.json")

    assert check_bundle_request(request)["asset_type"] == "character-bundle"
    assert check_bundle_result(result)["asset_type"] == "character-bundle"
    assert request["spec"]["required_actions"] == ["idle", "attack"]
    assert request["spec"]["actions"][1]["loop"] is False


def test_family_contract_checker_cli_validates_the_public_fixture():
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


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d["spec"].pop("required_actions"), id="missing-required-actions"),
        pytest.param(lambda d: d["spec"].update(required_actions=["idle", "idle"]), id="duplicate-required-action"),
        pytest.param(lambda d: d["spec"]["actions"][1].update(name="idle"), id="duplicate-action-name"),
        pytest.param(lambda d: d["spec"]["actions"][1].update(name="walk"), id="unexpected-action"),
        pytest.param(lambda d: d["spec"]["actions"][0].update(frame_names=[]), id="missing-frames"),
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
    request = _character_request()
    mutate(request)
    with pytest.raises(AnimatedBundleContractError):
        check_bundle_request(request)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda d: d["outputs"][0].update(godot_type="Texture2D"), id="no-spriteframes"),
        pytest.param(lambda d: d["outputs"].append({"role": "runtime", "path": "res://assets/generated/character-bundle/player/other.tres", "godot_type": "SpriteFrames"}), id="two-spriteframes"),
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

    request["spec"]["actions"] = []
    with pytest.raises(AnimatedBundleContractError, match="not allowed for a static"):
        check_bundle_request(request)


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


@pytest.mark.parametrize("family", ["character-bundle", "fx-bundle"])
def test_animated_skills_name_the_callable_family_validation_path(family):
    skill = (REPO_ROOT / "skills" / "assets" / family / "SKILL.md").read_text(encoding="utf-8")
    assert "asset_animated_bundle_contract_check.py" in skill
    assert "ASSETS.md" in skill
    assert "generated manifests" in skill
