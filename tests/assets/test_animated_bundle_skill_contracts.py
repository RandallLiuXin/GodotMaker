"""Public contract fixtures for standalone animated asset skills."""
import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(SHARED_DIR))

from asset_compiler import CompileRequest, CompilerError, sprite_frames  # noqa: E402
from asset_skill_contract_check import check_request, check_result  # noqa: E402


def _fixture(family: str, name: str) -> dict:
    path = REPO_ROOT / "skills" / "assets" / family / "fixtures" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_character_bundle_fixture_is_a_multi_action_standalone_contract():
    request = _fixture("character-bundle", "valid-request.json")
    result = _fixture("character-bundle", "valid-result.json")

    assert check_request(request)["asset_type"] == "character-bundle"
    assert check_result(result)["runtime_output_count"] == 1
    actions = request["spec"]["actions"]
    assert request["spec"]["required_actions"] == [action["name"] for action in actions]
    assert len(actions) == 2
    assert actions[1]["loop"] is False
    assert all(len(action["frame_names"]) == len(action["frame_durations"]) for action in actions)
    assert result["outputs"][0]["godot_type"] == "SpriteFrames"


def test_character_bundle_missing_required_action_is_rejected_by_shared_handoff(tmp_path):
    request = _fixture("character-bundle", "valid-request.json")
    action = request["spec"]["actions"][0]
    compiler_request = CompileRequest(
        production_family="character-bundle",
        asset_id="player",
        source_layout_type="grid_sheet",
        source_path="res://assets/generated/character-bundle/player/player_sheet.png",
        artifact_type="SpriteFrames",
        artifact_path="res://assets/generated/character-bundle/player/player.tres",
        project_root=tmp_path,
        spec={"required_actions": ["idle", "attack"], "actions": [
            {
                "name": action["name"], "loop": action["loop"], "fps": action["fps"],
                "frame_paths": ["res://assets/generated/character-bundle/player/idle_01.png"],
                "frame_durations": [action["frame_durations"][0]],
            }
        ]},
    )
    frame = tmp_path / "assets/generated/character-bundle/player/idle_01.png"
    frame.parent.mkdir(parents=True)
    frame.touch()
    with pytest.raises(CompilerError, match="missing required actions"):
        sprite_frames.action_spec(compiler_request)


def test_fx_fixtures_keep_static_and_animated_runtime_boundaries_separate():
    animated = _fixture("fx-bundle", "animated-request.json")
    animated_result = _fixture("fx-bundle", "animated-result.json")
    static_request = _fixture("fx-bundle", "static-request.json")
    static = _fixture("fx-bundle", "static-result.json")

    assert check_request(animated)["asset_type"] == "fx-bundle"
    assert check_result(animated_result)["runtime_output_count"] == 1
    assert check_request(static_request)["asset_type"] == "fx-bundle"
    assert check_result(static)["runtime_output_count"] == 1
    action = animated["spec"]["actions"]
    assert animated["spec"]["mode"] == "animated"
    assert len(action) == 1
    assert action[0]["loop"] is False
    assert len(action[0]["frame_names"]) == len(action[0]["frame_durations"])
    assert animated_result["outputs"][0]["godot_type"] == "SpriteFrames"
    assert static_request["spec"] == {"mode": "static"}
    assert static["outputs"][0]["godot_type"] == "Texture2D"
    assert static["sources"][0]["layout"] == "single"


@pytest.mark.parametrize("family", ["character-bundle", "fx-bundle"])
def test_animated_skills_are_standalone_and_do_not_claim_pipeline_or_scene_work(family):
    skill = (REPO_ROOT / "skills" / "assets" / family / "SKILL.md").read_text(encoding="utf-8")
    for forbidden in ("`ASSETS.md`", "generated manifests", "stable entries", "worker dispatch"):
        assert forbidden in skill
    assert "gm mode" not in skill.lower()


def test_fx_contract_rejects_a_missing_animated_frame():
    request = copy.deepcopy(_fixture("fx-bundle", "animated-request.json"))
    action = request["spec"]["actions"][0]
    action["frame_durations"].pop()
    compiler_request = CompileRequest(
        production_family="fx-bundle",
        asset_id="impact",
        source_layout_type="grid_sheet",
        source_path="res://assets/generated/fx-bundle/impact/impact_sheet.png",
        artifact_type="SpriteFrames",
        artifact_path="res://assets/generated/fx-bundle/impact/impact.tres",
        project_root=REPO_ROOT,
        spec={
            "required_actions": [action["name"]],
            "actions": [{
                "name": action["name"],
                "loop": action["loop"],
                "fps": action["fps"],
                "frame_paths": ["res://assets/generated/fx-bundle/impact/impact_01.png"],
                "frame_durations": action["frame_durations"],
            }],
        },
    )
    with pytest.raises(CompilerError, match="frame_durations"):
        sprite_frames.action_spec(compiler_request)
