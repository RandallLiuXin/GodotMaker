"""Fail-closed standalone execution tests for the formerly prose-only families."""

from __future__ import annotations

import sys
import json
from pathlib import Path

import pytest
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(REPO_ROOT / "skills" / "assets" / "_shared"),
    str(REPO_ROOT / "tools"),
]

from missing_family_standalone_validation import (  # noqa: E402
    MissingFamilySkillError,
    compile_and_validate,
)
from asset_validation import ProbeReport, ProbeResult  # noqa: E402
import missing_family_standalone_validation as runner  # noqa: E402


def _background_result(
    *, asset_type: str = "background-map", godot_type: str = "Texture2D"
) -> dict:
    return {
        "asset_type": asset_type,
        "outputs": [
            {
                "role": "runtime",
                "name": "sky",
                "path": "res://assets/generated/background-map/sky/sky.png",
                "godot_type": godot_type,
            }
        ],
        "sources": [
            {
                "path": "res://assets/generated/background-map/sky/sky.png",
                "layout": "single",
            }
        ],
        "previews": [],
        "validation": {
            "passed": True,
            "levels": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": True},
        },
    }


def test_background_runner_does_not_trust_a_forged_successful_validation(tmp_path):
    actual = compile_and_validate(
        {"asset_type": "background-map", "asset_id": "sky", "brief": "A blue sky."},
        _background_result(),
        project_root=tmp_path,
        godot_path="godot",
    )
    assert actual["validation"]["passed"] is False
    assert actual["validation"]["levels"] == {
        "L0": True,
        "L1": False,
        "L2": False,
        "L3": False,
        "L4": False,
    }


@pytest.mark.parametrize(
    "result",
    [
        pytest.param(
            _background_result(asset_type="platform-strip"), id="wrong-family"
        ),
        pytest.param(
            _background_result(godot_type="AtlasTexture"), id="wrong-godot-type"
        ),
    ],
)
def test_background_runner_fails_closed_before_l1_for_wrong_public_binding(
    tmp_path, result
):
    with pytest.raises(MissingFamilySkillError, match="L0 standalone contract failed"):
        compile_and_validate(
            {"asset_type": "background-map", "asset_id": "sky", "brief": "A blue sky."},
            result,
            project_root=tmp_path,
            godot_path="godot",
        )


def test_platform_atlas_requires_every_declared_logical_output(tmp_path):
    request = {
        "asset_type": "platform-strip",
        "asset_id": "bridge",
        "brief": "A bridge.",
        "spec": {"kind": "atlas", "segments": [{"name": "left"}, {"name": "middle"}]},
    }
    result = {
        "asset_type": "platform-strip",
        "outputs": [
            {
                "role": "runtime",
                "name": "left",
                "path": "res://assets/generated/platform-strip/bridge/left.tres",
                "godot_type": "AtlasTexture",
            }
        ],
        "sources": [
            {
                "path": "res://assets/generated/platform-strip/bridge/bridge.png",
                "layout": "region_atlas",
            }
        ],
        "previews": [],
        "validation": {"passed": True},
    }
    with pytest.raises(MissingFamilySkillError, match="every declared segment"):
        compile_and_validate(request, result, project_root=tmp_path, godot_path="godot")


def test_screen_reference_completes_at_l1_without_invoking_runtime_ladder(tmp_path):
    reference = tmp_path / "references" / "title.png"
    reference.parent.mkdir()
    Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(reference)
    result = compile_and_validate(
        {
            "asset_type": "screen-reference",
            "asset_id": "title",
            "brief": "A title scene.",
        },
        {
            "asset_type": "screen-reference",
            "outputs": [
                {"role": "reference", "name": "title", "path": "references/title.png"}
            ],
            "sources": [],
            "previews": [],
            "validation": {"passed": False},
        },
        project_root=tmp_path,
        godot_path="not-used",
    )
    assert result["validation"] == {"passed": True, "levels": {"L0": True, "L1": True}}


def test_background_executes_l2_to_l4_with_a_real_png_and_probe(monkeypatch, tmp_path):
    source = tmp_path / "assets/generated/background-map/sky/sky.png"
    source.parent.mkdir(parents=True)
    Image.new("RGBA", (2, 3), (1, 2, 3, 255)).save(source)

    class Probe:
        def __init__(self, _path):
            pass

        def probe(self, _root, requests):
            return ProbeReport(
                "fake",
                (
                    ProbeResult(
                        requests[0].res_path,
                        "Texture2D",
                        True,
                        "CompressedTexture2D",
                        True,
                        structure={"texture2d": {"width": 2, "height": 3}},
                    ),
                ),
            )

    monkeypatch.setattr(runner, "GodotProbe", Probe)
    actual = compile_and_validate(
        {"asset_type": "background-map", "asset_id": "sky", "brief": "A blue sky."},
        _background_result(),
        project_root=tmp_path,
        godot_path="fake",
    )
    assert actual["validation"]["levels"] == {
        level: True for level in ("L0", "L1", "L2", "L3", "L4")
    }


@pytest.mark.parametrize("source", [None, 5], ids=["missing", "wrong-type"])
def test_prop_slot_errors_fail_closed_at_l0(tmp_path, source):
    slot = {"name": "coin", "rect": [0, 0, 1, 1]}
    if source is not None:
        slot["source"] = source
    request = {
        "asset_type": "compact-prop-pack",
        "asset_id": "props",
        "brief": "props",
        "spec": {"version": 1, "atlas": {"width": 1, "height": 1}, "slots": [slot]},
    }
    result = {
        "asset_type": "compact-prop-pack",
        "outputs": [
            {
                "role": "runtime",
                "name": "coin",
                "path": "res://assets/generated/compact-prop-pack/props/coin.tres",
                "godot_type": "AtlasTexture",
            }
        ],
        "sources": [
            {
                "path": "res://assets/generated/compact-prop-pack/props/props.png",
                "layout": "region_atlas",
            }
        ],
        "previews": [],
        "validation": {"passed": False},
    }
    with pytest.raises(MissingFamilySkillError, match="L0 standalone contract failed"):
        compile_and_validate(request, result, project_root=tmp_path, godot_path="fake")


def test_prop_runner_never_rebuilds_or_overwrites_the_delivered_atlas(tmp_path):
    output = tmp_path / "assets/generated/compact-prop-pack/props"
    output.mkdir(parents=True)
    atlas = output / "props.png"
    Image.new("RGBA", (1, 1), (0, 0, 255, 255)).save(atlas)
    metadata = output / "props.json"
    metadata.write_text("not metadata", encoding="utf-8")
    before = (atlas.read_bytes(), metadata.read_bytes())
    request = {
        "asset_type": "compact-prop-pack",
        "asset_id": "props",
        "brief": "props",
        "spec": {
            "version": 1,
            "atlas": {"width": 1, "height": 1},
            "slots": [
                {"name": "coin", "rect": [0, 0, 1, 1], "source": "sources/coin.png"}
            ],
        },
    }
    result = {
        "asset_type": "compact-prop-pack",
        "outputs": [
            {
                "role": "runtime",
                "name": "coin",
                "path": "res://assets/generated/compact-prop-pack/props/coin.tres",
                "godot_type": "AtlasTexture",
            }
        ],
        "sources": [
            {
                "path": "res://assets/generated/compact-prop-pack/props/props.png",
                "layout": "region_atlas",
            }
        ],
        "previews": [],
        "validation": {"passed": True},
    }
    actual = compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )
    assert actual["validation"]["levels"]["L2"] is False
    assert (atlas.read_bytes(), metadata.read_bytes()) == before


def test_animated_bundle_checks_each_declared_sheet_at_l1(tmp_path):
    request = json.loads(
        (
            REPO_ROOT / "skills/assets/character-bundle/fixtures/valid-request.json"
        ).read_text(encoding="utf-8")
    )
    result = json.loads(
        (
            REPO_ROOT / "skills/assets/character-bundle/fixtures/valid-result.json"
        ).read_text(encoding="utf-8")
    )
    result["sources"].append(
        {
            "path": "res://assets/generated/character-bundle/player/never_written.png",
            "layout": "grid_sheet",
        }
    )
    output = tmp_path / "assets/generated/character-bundle/player"
    output.mkdir(parents=True)
    for path in ("player_idle_sheet.png", "preview_idle.png"):
        (output / path).write_bytes(b"x")
    for action in request["spec"]["actions"]:
        for frame in action["frame_names"]:
            (output / f"player_{action['name']}_{frame}.png").write_bytes(b"x")
    actual = compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )
    assert actual["validation"]["levels"]["L1"] is False
