"""Fail-closed standalone execution tests for the formerly prose-only families."""

from __future__ import annotations

import json
import importlib.util
import struct
import sys
import zlib
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


def _source_adapter(family: str):
    path = REPO_ROOT / "skills" / "assets" / family / "standalone_validation.py"
    spec = importlib.util.spec_from_file_location(f"{family}_adapter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_skill_local_adapters_reject_a_legal_request_for_another_family(tmp_path):
    request = {"asset_type": "background-map", "asset_id": "sky", "brief": "A blue sky."}
    for family in (
        "platform-strip", "screen-reference", "character-bundle", "fx-bundle",
        "compact-prop-pack", "scene-prop-set",
    ):
        with pytest.raises(MissingFamilySkillError, match="L0 standalone contract failed"):
            _source_adapter(family).compile_and_validate(
                request, _background_result(), project_root=tmp_path, godot_path="fake"
            )

    platform_request = {
        "asset_type": "platform-strip", "asset_id": "bridge", "brief": "A bridge.",
        "spec": {
            "kind": "single",
            "grid": {"columns": 3, "rows": 1, "cell_width": 8, "cell_height": 8},
            "segments": [
                {"name": "left", "role": "left_cap", "slot": [0, 0]},
                {"name": "middle", "role": "repeat_middle", "slot": [1, 0]},
                {"name": "right", "role": "right_cap", "slot": [2, 0]},
            ],
        },
    }
    platform_result = {
        "asset_type": "platform-strip",
        "outputs": [{"role": "runtime", "name": "middle", "path": "res://assets/generated/platform-strip/bridge/middle.png", "godot_type": "Texture2D"}],
        "sources": [{"path": "res://assets/generated/platform-strip/bridge/middle.png", "layout": "single"}],
        "previews": [], "validation": {"passed": False},
    }
    with pytest.raises(MissingFamilySkillError, match="L0 standalone contract failed"):
        _source_adapter("background-map").compile_and_validate(
            platform_request, platform_result, project_root=tmp_path, godot_path="fake"
        )


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


def test_background_runner_preserves_a_no_output_provider_or_reference_stop(tmp_path):
    result = {
        "asset_type": "background-map",
        "outputs": [],
        "sources": [],
        "previews": [],
        "validation": {"passed": False, "notes": "style reference is unreadable"},
    }

    actual = compile_and_validate(
        {
            "asset_type": "background-map",
            "asset_id": "sky",
            "brief": "A blue sky.",
            "references": [{"role": "style", "path": "res://references/missing.png"}],
            "provider": "codex",
        },
        result,
        project_root=tmp_path,
        godot_path="godot",
    )

    assert actual["outputs"] == []
    assert actual["sources"] == []
    assert actual["validation"] == {
        "passed": False,
        "levels": {"L0": True, "L1": False},
        "notes": "style reference is unreadable",
    }


def test_background_runner_rejects_an_unexplained_no_output_stop(tmp_path):
    result = {
        "asset_type": "background-map",
        "outputs": [],
        "sources": [],
        "previews": [],
        "validation": {"passed": False},
    }

    with pytest.raises(MissingFamilySkillError, match="must include a validation note"):
        compile_and_validate(
            {"asset_type": "background-map", "asset_id": "sky", "brief": "A blue sky."},
            result,
            project_root=tmp_path,
            godot_path="godot",
        )


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
        "spec": {
            "kind": "atlas",
            "grid": {"columns": 3, "rows": 1, "cell_width": 8, "cell_height": 8},
            "segments": [
                {"name": "left", "role": "left_cap", "slot": [0, 0]},
                {"name": "middle", "role": "repeat_middle", "slot": [1, 0]},
                {"name": "right", "role": "right_cap", "slot": [2, 0]},
            ],
        },
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


def test_platform_strip_rejects_an_unreadable_optional_reference_at_l1(tmp_path):
    root = "res://assets/generated/platform-strip/bridge"
    request = {
        "asset_type": "platform-strip",
        "asset_id": "bridge",
        "brief": "A bridge.",
        "references": [{"role": "style", "path": "references/missing.png"}],
        "spec": {
            "kind": "single",
            "grid": {"columns": 3, "rows": 1, "cell_width": 8, "cell_height": 8},
            "segments": [
                {"name": "left", "role": "left_cap", "slot": [0, 0]},
                {"name": "middle", "role": "repeat_middle", "slot": [1, 0]},
                {"name": "right", "role": "right_cap", "slot": [2, 0]},
            ],
        },
    }
    result = {
        "asset_type": "platform-strip",
        "outputs": [
            {"role": "runtime", "name": name, "path": f"{root}/{name}.png", "godot_type": "Texture2D"}
            for name in ("left", "middle", "right")
        ],
        "sources": [{"path": f"{root}/{name}.png", "layout": "single"} for name in ("left", "middle", "right")],
        "previews": [],
        "validation": {"passed": False},
    }
    raw_source = tmp_path / ".godotmaker/asset-generation/sources/bridge_source.png"
    raw_source.parent.mkdir(parents=True)
    Image.new("RGBA", (24, 8), (1, 2, 3, 255)).save(raw_source)

    actual = compile_and_validate(request, result, project_root=tmp_path, godot_path="fake")

    assert actual["validation"]["levels"] == {"L0": True, "L1": False, "L2": False, "L3": False, "L4": False}
    assert "platform-strip reference style" in actual["validation"]["notes"]


def test_screen_reference_completes_at_l1_without_invoking_runtime_ladder(tmp_path):
    reference = tmp_path / "references" / "title.png"
    reference.parent.mkdir()
    Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(reference)
    raw_source = tmp_path / ".godotmaker/asset-generation/sources/title_source.png"
    raw_source.parent.mkdir(parents=True)
    Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(raw_source)
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
            "sources": [
                {
                    "path": ".godotmaker/asset-generation/sources/title_source.png",
                    "layout": "single",
                }
            ],
            "previews": [],
            "validation": {"passed": False},
        },
        project_root=tmp_path,
        godot_path="not-used",
    )
    assert result["validation"] == {"passed": True, "levels": {"L0": True, "L1": True}}


def _screen_reference_request() -> dict:
    return {
        "asset_type": "screen-reference",
        "asset_id": "title",
        "brief": "A title scene.",
    }


def _screen_reference_result() -> dict:
    return {
        "asset_type": "screen-reference",
        "outputs": [
            {"role": "reference", "name": "title", "path": "references/title.png"}
        ],
        "sources": [
            {
                "path": ".godotmaker/asset-generation/sources/title_source.png",
                "layout": "single",
            }
        ],
        "previews": [],
        "validation": {"passed": True},
    }


def test_screen_reference_rejects_a_missing_deterministic_raw_source(tmp_path):
    reference = tmp_path / "references" / "title.png"
    reference.parent.mkdir()
    Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(reference)

    actual = compile_and_validate(
        _screen_reference_request(),
        _screen_reference_result(),
        project_root=tmp_path,
        godot_path="not-used",
    )

    assert actual["validation"] == {
        "passed": False,
        "levels": {"L0": True, "L1": False},
        "notes": (
            "raw screen-reference source is not a non-empty file: "
            ".godotmaker/asset-generation/sources/title_source.png"
        ),
    }


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _zero_width_png() -> bytes:
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 0, 1, 8, 6, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(b"")),
            _png_chunk(b"IEND", b""),
        )
    )


def _decompression_bomb_png() -> bytes:
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(
                b"IHDR", struct.pack(">IIBBBBB", 30000, 30000, 8, 6, 0, 0, 0)
            ),
            _png_chunk(b"IEND", b""),
        )
    )


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02",
            id="truncated-ihdr",
        ),
        pytest.param(b"not a png", id="non-png"),
        pytest.param(_zero_width_png(), id="zero-width"),
        pytest.param(_decompression_bomb_png(), id="decompression-bomb"),
    ],
)
def test_screen_reference_rejects_undecodable_pngs(tmp_path, payload):
    reference = tmp_path / "references" / "title.png"
    reference.parent.mkdir()
    reference.write_bytes(payload)

    actual = compile_and_validate(
        _screen_reference_request(),
        _screen_reference_result(),
        project_root=tmp_path,
        godot_path="not-used",
    )

    assert actual["validation"] == {
        "passed": False,
        "levels": {"L0": True, "L1": False},
        "notes": "reference image is not a decodable PNG: references/title.png",
    }
    assert str(tmp_path) not in actual["validation"]["notes"]


def test_screen_reference_rejects_png_with_bad_idat_crc(tmp_path):
    reference = tmp_path / "references" / "title.png"
    reference.parent.mkdir()
    Image.new("RGBA", (2, 2), (1, 2, 3, 255)).save(reference)
    payload = bytearray(reference.read_bytes())
    idat = payload.index(b"IDAT")
    payload[idat + 4] ^= 1
    reference.write_bytes(payload)

    actual = compile_and_validate(
        _screen_reference_request(),
        _screen_reference_result(),
        project_root=tmp_path,
        godot_path="not-used",
    )

    assert actual["validation"] == {
        "passed": False,
        "levels": {"L0": True, "L1": False},
        "notes": "reference image is not a decodable PNG: references/title.png",
    }


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"not a png", id="non-png"),
        pytest.param(_decompression_bomb_png(), id="decompression-bomb"),
    ],
)
def test_prop_atlas_rejects_bad_png_with_a_stable_source_path(tmp_path, payload):
    request, result = _prop_handoff("compact-prop-pack")
    _write_prop_delivery(tmp_path, request)
    atlas = tmp_path / "assets/generated/compact-prop-pack/market/market.png"
    atlas.write_bytes(payload)

    actual = compile_and_validate(
        request, result, project_root=tmp_path, godot_path="not-used"
    )

    assert actual["validation"] == {
        "passed": False,
        "levels": {level: level == "L0" for level in ("L0", "L1", "L2", "L3", "L4")},
        "notes": (
            "delivered atlas is not a decodable PNG: "
            "res://assets/generated/compact-prop-pack/market/market.png"
        ),
    }


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


@pytest.mark.parametrize("family", ["compact-prop-pack", "scene-prop-set"])
@pytest.mark.parametrize(
    ("slots", "message"),
    [
        pytest.param(
            [
                {"name": "left", "rect": [0, 0, 4, 4], "source": "left.png"},
                {"name": "right", "rect": [4, 0, 4, 4], "source": "right.png"},
            ],
            None,
            id="edge-touching-is-valid",
        ),
        pytest.param(
            [
                {"name": "left", "rect": [0, 0, 6, 6], "source": "left.png"},
                {"name": "right", "rect": [4, 4, 4, 4], "source": "right.png"},
            ],
            "overlaps another declared slot",
            id="partial-overlap",
        ),
        pytest.param(
            [
                {"name": "outer", "rect": [0, 0, 8, 8], "source": "outer.png"},
                {"name": "inner", "rect": [2, 2, 2, 2], "source": "inner.png"},
            ],
            "overlaps another declared slot",
            id="complete-containment",
        ),
        pytest.param(
            [
                {"name": "first", "rect": [0, 0, 4, 4], "source": "first.png"},
                {"name": "second", "rect": [0, 0, 4, 4], "source": "second.png"},
            ],
            "overlaps another declared slot",
            id="identical-rectangles",
        ),
        pytest.param(
            [
                {"name": "top_left", "rect": [0, 0, 4, 4], "source": "top_left.png"},
                {"name": "top_right", "rect": [4, 0, 4, 4], "source": "top_right.png"},
                {"name": "bottom", "rect": [0, 4, 8, 4], "source": "bottom.png"},
            ],
            None,
            id="valid-multi-slot-layout",
        ),
        pytest.param(
            [{"name": "outside", "rect": [6, 0, 3, 2], "source": "outside.png"}],
            "outside the declared atlas bounds",
            id="outside-atlas-bounds",
        ),
    ],
)
def test_prop_fixed_slot_geometry_fails_closed_at_l0(tmp_path, family, slots, message):
    root = f"res://assets/generated/{family}/props"
    request = {
        "asset_type": family,
        "asset_id": "props",
        "brief": "props",
        "spec": {"version": 1, "atlas": {"width": 8, "height": 8}, "slots": slots},
    }
    result = {
        "asset_type": family,
        "outputs": [
            {
                "role": "runtime",
                "name": slot["name"],
                "path": f"{root}/{slot['name']}.tres",
                "godot_type": "AtlasTexture",
            }
            for slot in slots
        ],
        "sources": [{"path": f"{root}/props.png", "layout": "region_atlas"}],
        "previews": [],
        "validation": {"passed": False},
    }

    if message is None:
        actual = compile_and_validate(
            request, result, project_root=tmp_path, godot_path="fake"
        )
        assert actual["validation"]["levels"]["L0"] is True
    else:
        with pytest.raises(MissingFamilySkillError, match=message):
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
    assert actual["validation"]["levels"]["L1"] is False
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


def _set_good_probe(monkeypatch, structures):
    class Probe:
        def __init__(self, _path):
            pass

        def probe(self, _root, requests):
            return ProbeReport(
                "fake",
                tuple(
                    ProbeResult(
                        item.res_path,
                        item.expected_type,
                        True,
                        item.expected_type,
                        True,
                        structure=structures[item.res_path],
                    )
                    for item in requests
                ),
            )

    monkeypatch.setattr(runner, "GodotProbe", Probe)


def _prop_handoff(family: str, asset_id: str = "market") -> tuple[dict, dict]:
    root = f"res://assets/generated/{family}/{asset_id}"
    slots = [
        {"name": "coin", "rect": [0, 0, 16, 16], "source": "sources/coin.png"},
        {"name": "chest", "rect": [16, 0, 16, 16], "source": "sources/chest.png"},
    ]
    request = {
        "asset_type": family,
        "asset_id": asset_id,
        "brief": "Two compact props.",
        "spec": {"version": 1, "atlas": {"width": 32, "height": 16}, "slots": slots},
    }
    result = {
        "asset_type": family,
        "outputs": [
            {
                "role": "runtime",
                "name": slot["name"],
                "path": f"{root}/{slot['name']}.tres",
                "godot_type": "AtlasTexture",
            }
            for slot in slots
        ],
        "sources": [{"path": f"{root}/{asset_id}.png", "layout": "region_atlas"}],
        "previews": [],
        "validation": {"passed": False},
    }
    return request, result


def _write_prop_delivery(
    root: Path, request: dict, *, extra_region: bool = False
) -> None:
    family, asset_id = request["asset_type"], request["asset_id"]
    output = root / "assets" / "generated" / family / asset_id
    output.mkdir(parents=True)
    atlas = request["spec"]["atlas"]
    Image.new("RGBA", (atlas["width"], atlas["height"]), (1, 2, 3, 255)).save(
        output / f"{asset_id}.png"
    )
    regions = [
        {
            "name": slot["name"],
            "rect": slot["rect"],
            "pivot": [0.5, 0.5],
            "nine_slice": None,
        }
        for slot in request["spec"]["slots"]
    ]
    if extra_region:
        regions.append(
            {
                "name": "ghost",
                "rect": [0, 0, 1, 1],
                "pivot": [0.5, 0.5],
                "nine_slice": None,
            }
        )
    (output / f"{asset_id}.json").write_text(
        json.dumps(
            {
                "version": 1,
                "atlas_path": f"res://assets/generated/{family}/{asset_id}/{asset_id}.png",
                "regions": regions,
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize("family", ["compact-prop-pack", "scene-prop-set"])
def test_prop_families_run_multi_slot_delivery_through_l4(
    monkeypatch, tmp_path, family
):
    request, result = _prop_handoff(family)
    _write_prop_delivery(tmp_path, request)
    root = f"res://assets/generated/{family}/market"
    _set_good_probe(
        monkeypatch,
        {
            f"{root}/coin.tres": {
                "atlas_texture": {
                    "has_atlas": True,
                    "atlas_path": f"{root}/market.png",
                    "region": [0, 0, 16, 16],
                    "margin": [0, 0, 0, 0],
                }
            },
            f"{root}/chest.tres": {
                "atlas_texture": {
                    "has_atlas": True,
                    "atlas_path": f"{root}/market.png",
                    "region": [16, 0, 16, 16],
                    "margin": [0, 0, 0, 0],
                }
            },
        },
    )

    actual = compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )

    assert actual["validation"]["levels"] == {
        level: True for level in ("L0", "L1", "L2", "L3", "L4")
    }


def test_compact_prop_multi_slot_delivery_runs_through_real_godot_l4(
    godot_project, godot_bin
):
    request, result = _prop_handoff("compact-prop-pack")
    _write_prop_delivery(godot_project, request)

    actual = compile_and_validate(
        request, result, project_root=godot_project, godot_path=godot_bin
    )

    assert actual["validation"]["levels"] == {
        level: True for level in ("L0", "L1", "L2", "L3", "L4")
    }


@pytest.mark.parametrize("mutation", ["rect", "extra-region", "dimensions"])
def test_prop_delivery_must_exactly_bind_declared_geometry(tmp_path, mutation):
    request, result = _prop_handoff("compact-prop-pack")
    _write_prop_delivery(tmp_path, request, extra_region=mutation == "extra-region")
    output = tmp_path / "assets/generated/compact-prop-pack/market"
    metadata = output / "market.json"
    if mutation == "rect":
        delivered = json.loads(metadata.read_text(encoding="utf-8"))
        delivered["regions"][0]["rect"] = [0, 0, 1, 1]
        metadata.write_text(json.dumps(delivered), encoding="utf-8")
    elif mutation == "dimensions":
        Image.new("RGBA", (64, 64), (1, 2, 3, 255)).save(output / "market.png")

    actual = compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )

    assert actual["validation"]["levels"] == {
        "L0": True,
        "L1": False,
        "L2": False,
        "L3": False,
        "L4": False,
    }


@pytest.mark.parametrize("kind", ["single", "atlas"])
def test_platform_strip_runs_each_supported_source_type_to_l4(
    monkeypatch, tmp_path, kind
):
    asset_id = "bridge"
    root = f"res://assets/generated/platform-strip/{asset_id}"
    request = {
        "asset_type": "platform-strip",
        "asset_id": asset_id,
        "brief": "A bridge.",
        "spec": {
            "kind": kind,
            "grid": {"columns": 3, "rows": 1, "cell_width": 8, "cell_height": 8},
            "segments": [
                {"name": "left", "role": "left_cap", "slot": [0, 0]},
                {"name": "middle", "role": "repeat_middle", "slot": [1, 0]},
                {"name": "right", "role": "right_cap", "slot": [2, 0]},
            ],
        },
    }
    if kind == "single":
        result = {
            "asset_type": "platform-strip",
            "outputs": [
                {
                    "role": "runtime",
                    "name": name,
                    "path": f"{root}/{name}.png",
                    "godot_type": "Texture2D",
                }
                for name in ("left", "middle", "right")
            ],
            "sources": [
                {"path": f"{root}/{name}.png", "layout": "single"}
                for name in ("left", "middle", "right")
            ],
            "previews": [],
            "validation": {"passed": False},
        }
        directory = tmp_path / "assets/generated/platform-strip/bridge"
        directory.mkdir(parents=True)
        for name in ("left", "middle", "right"):
            image = Image.new("RGBA", (8, 8), (1, 2, 3, 255))
            image.putpixel((0, 0), (0, 0, 0, 0))
            image.save(directory / f"{name}.png")
        structures = {
            f"{root}/{name}.png": {"texture2d": {"width": 8, "height": 8}}
            for name in ("left", "middle", "right")
        }
    else:
        result = {
            "asset_type": "platform-strip",
            "outputs": [
                {
                    "role": "runtime",
                    "name": name,
                    "path": f"{root}/{name}.tres",
                    "godot_type": "AtlasTexture",
                }
                for name in ("left", "middle", "right")
            ],
            "sources": [{"path": f"{root}/bridge.png", "layout": "region_atlas"}],
            "previews": [],
            "validation": {"passed": False},
        }
        directory = tmp_path / "assets/generated/platform-strip/bridge"
        directory.mkdir(parents=True)
        image = Image.new("RGBA", (24, 8), (1, 2, 3, 255))
        image.putpixel((0, 0), (0, 0, 0, 0))
        image.save(directory / "bridge.png")
        (directory / "bridge.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "atlas_path": f"{root}/bridge.png",
                    "regions": [
                        {
                            "name": "left",
                            "rect": [0, 0, 8, 8],
                            "pivot": [0.5, 1.0],
                            "nine_slice": None,
                        },
                        {
                            "name": "middle",
                            "rect": [8, 0, 8, 8],
                            "pivot": [0.5, 1.0],
                            "nine_slice": None,
                        },
                        {
                            "name": "right",
                            "rect": [16, 0, 8, 8],
                            "pivot": [0.5, 1.0],
                            "nine_slice": None,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        structures = {
            f"{root}/{name}.tres": {
                "atlas_texture": {
                    "has_atlas": True,
                    "atlas_path": f"{root}/bridge.png",
                    "region": rect,
                    "margin": [0, 0, 0, 0],
                }
            }
            for name, rect in (
                ("left", [0, 0, 8, 8]),
                ("middle", [8, 0, 8, 8]),
                ("right", [16, 0, 8, 8]),
            )
        }
    raw_source = tmp_path / ".godotmaker/asset-generation/sources/bridge_source.png"
    raw_source.parent.mkdir(parents=True)
    Image.new("RGBA", (24, 8), (1, 2, 3, 255)).save(raw_source)
    _set_good_probe(monkeypatch, structures)

    actual = compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )

    assert actual["validation"]["passed"] is True, actual["validation"]


@pytest.mark.parametrize(
    ("family", "request_name", "result_name"),
    [
        ("character-bundle", "valid-request.json", "valid-result.json"),
        ("fx-bundle", "animated-request.json", "animated-result.json"),
        ("fx-bundle", "static-request.json", "static-result.json"),
    ],
)
def test_bundles_run_declared_static_and_multi_action_outputs_to_l4(
    monkeypatch, tmp_path, family, request_name, result_name
):
    fixtures = REPO_ROOT / "skills/assets" / family / "fixtures"
    request = json.loads((fixtures / request_name).read_text(encoding="utf-8"))
    result = json.loads((fixtures / result_name).read_text(encoding="utf-8"))
    asset_id = request["asset_id"]
    output = tmp_path / "assets" / "generated" / family / asset_id
    output.mkdir(parents=True)
    for preview in result["previews"]:
        preview_file = tmp_path / preview["path"].removeprefix("res://")
        preview_file.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(preview_file)
    runtime = result["outputs"][0]
    if runtime["godot_type"] == "Texture2D":
        Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(output / f"{asset_id}.png")
        structures = {runtime["path"]: {"texture2d": {"width": 8, "height": 8}}}
    else:
        for source in result["sources"]:
            Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(
                output / Path(source["path"]).name
            )
        for action in request["spec"]["actions"]:
            for frame in action["frame_names"]:
                Image.new("RGBA", (1, 1), (1, 2, 3, 255)).save(
                    output / f"{asset_id}_{action['name']}_{frame}.png"
                )
        animations = [
            {
                "name": action["name"],
                "loop": action["loop"],
                "fps": action["fps"],
                "frame_paths": [
                    f"res://assets/generated/{family}/{asset_id}/{asset_id}_{action['name']}_{frame}.png"
                    for frame in action["frame_names"]
                ],
                "frame_count": len(action["frame_names"]),
                "frame_durations": action["frame_durations"],
            }
            for action in request["spec"]["actions"]
        ]
        structures = {runtime["path"]: {"spriteframes": {"animations": animations}}}
    _set_good_probe(monkeypatch, structures)

    actual = compile_and_validate(
        request, result, project_root=tmp_path, godot_path="fake"
    )

    assert actual["validation"]["passed"] is True, actual["validation"]
