"""Fail-closed standalone execution tests for the formerly prose-only families."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(REPO_ROOT / "skills" / "assets" / "_shared"),
    str(REPO_ROOT / "tools"),
]

from missing_family_standalone_validation import (  # noqa: E402
    MissingFamilySkillError,
    compile_and_validate,
)


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
    reference.write_bytes(b"image")
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
