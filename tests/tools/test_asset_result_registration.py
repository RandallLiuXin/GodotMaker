"""Direct result-to-ASSETS.md registration regressions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_result_registration import (  # noqa: E402
    AssetResultRegistrationError,
    register_result,
    runtime_snapshot,
)
from asset_build_record import write_validation_record  # noqa: E402


TAG = "v0.1.0"


def _assets_md(path: Path, names: list[str]) -> None:
    rows = "\n".join(
        f"| {index} | {TAG} | {name} | prop | 64x64 | family=scene-prop-set | - | - | MISSING |"
        for index, name in enumerate(names, 1)
    )
    path.write_text(
        "# Assets\n\n"
        "| # | Tag | Name | Type | Size | Generation Params | Runtime Type | Runtime Path | Status |\n"
        "|---|-----|------|------|------|-------------------|--------------|--------------|--------|\n"
        + rows
        + "\n",
        encoding="utf-8",
    )


def _result(path: Path, outputs: list[dict[str, str]]) -> None:
    path.write_text(
        json.dumps(
            {
                "asset_type": "scene-prop-set",
                "outputs": outputs,
                "sources": [{"path": "res://assets/atlas.png", "layout": "region_atlas"}],
                "previews": [],
                "validation": {"passed": True, "levels": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": True}},
            }
        ),
        encoding="utf-8",
    )


def _request(path: Path, names: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "asset_type": "scene-prop-set",
                "asset_id": "market",
                "brief": "market props",
                "spec": {
                    "version": 1,
                    "atlas": {"width": 256, "height": 256},
                    "slots": [
                        {
                            "name": name,
                            "rect": [index * 64, 0, 64, 64],
                            "source": f"tmp/{name}.png",
                        }
                        for index, name in enumerate(names)
                    ],
                },
            }
        ),
        encoding="utf-8",
    )


def _runtime(name: str) -> dict[str, str]:
    return {
        "role": "runtime",
        "name": name,
        "path": f"res://assets/generated/scene-prop-set/market/{name}.tres",
        "godot_type": "AtlasTexture",
    }


def _touch_runtime(root: Path, name: str) -> None:
    target = root / "assets" / "generated" / "scene-prop-set" / "market" / f"{name}.tres"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[gd_resource type=\"AtlasTexture\" format=3]\n", encoding="utf-8")


def _loader(root: Path, path: str, expected: str) -> None:
    assert (root / path.removeprefix("res://")).is_file()
    assert expected == "AtlasTexture"


def test_scene_prop_set_registers_every_output_atomically_and_snapshots_them(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    names = ["market_stall", "lantern_post", "barrel"]
    _assets_md(assets_md, names)
    for name in names:
        _touch_runtime(tmp_path, name)
    result = tmp_path / "result.json"
    _result(result, [_runtime(name) for name in names])
    request = tmp_path / "request.json"
    _request(request, names)

    registered = register_result(
        assets_md, result, tag=TAG, request_path=request, loader=_loader
    )

    assert registered["updated"] == names
    text = assets_md.read_text(encoding="utf-8")
    for name in names:
        assert f"| {name} | prop | 64x64 | family=scene-prop-set | AtlasTexture | res://assets/generated/scene-prop-set/market/{name}.tres | generated |" in text
    snapshot = runtime_snapshot(assets_md, tag=TAG, asset_ids=names)
    assert [item["asset_id"] for item in snapshot] == names
    assert all(item["godot_artifact"]["type"] == "AtlasTexture" for item in snapshot)


@pytest.mark.parametrize(
    "outputs",
    [
        [_runtime("market_stall"), _runtime("lantern_post")],
        [_runtime("market_stall"), _runtime("market_stall"), _runtime("barrel")],
        [_runtime("market_stall"), _runtime("lantern_post"), _runtime("barrel"), _runtime("unknown")],
    ],
)
def test_result_mismatches_fail_before_any_assets_md_row_is_changed(tmp_path, outputs):
    assets_md = tmp_path / "ASSETS.md"
    names = ["market_stall", "lantern_post", "barrel"]
    _assets_md(assets_md, names)
    for name in {entry["name"] for entry in outputs}:
        _touch_runtime(tmp_path, name)
    result = tmp_path / "result.json"
    _result(result, outputs)
    request = tmp_path / "request.json"
    _request(request, names)
    original = assets_md.read_text(encoding="utf-8")

    with pytest.raises(AssetResultRegistrationError):
        register_result(
            assets_md, result, tag=TAG, request_path=request, loader=_loader
        )

    assert assets_md.read_text(encoding="utf-8") == original


def test_reference_row_completes_without_entering_worker_runtime_snapshot(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    _assets_md(assets_md, ["screen_ref"])
    reference = tmp_path / "references" / "screen_ref.png"
    reference.parent.mkdir()
    reference.write_bytes(b"png")
    result = tmp_path / "reference-result.json"
    result.write_text(
        json.dumps(
            {
                "asset_type": "screen-reference",
                "outputs": [{"role": "reference", "name": "screen_ref", "path": "res://references/screen_ref.png"}],
                "sources": [],
                "previews": [],
                "validation": {"passed": True},
            }
        ),
        encoding="utf-8",
    )
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps({"asset_type": "screen-reference", "asset_id": "screen_ref", "brief": "reference"}),
        encoding="utf-8",
    )

    register_result(assets_md, result, tag=TAG, request_path=request, loader=_loader)

    assert "| reference | res://references/screen_ref.png | source_ready |" in assets_md.read_text(encoding="utf-8")
    with pytest.raises(AssetResultRegistrationError, match="expected generated"):
        runtime_snapshot(assets_md, tag=TAG, asset_ids=["screen_ref"])


def test_missing_runtime_file_or_failed_godot_check_keeps_the_whole_unit_missing(tmp_path):
    assets_md = tmp_path / "ASSETS.md"
    names = ["market_stall", "lantern_post", "barrel"]
    _assets_md(assets_md, names)
    for name in names[:2]:
        _touch_runtime(tmp_path, name)
    result = tmp_path / "result.json"
    _result(result, [_runtime(name) for name in names])
    request = tmp_path / "request.json"
    _request(request, names)
    original = assets_md.read_text(encoding="utf-8")

    with pytest.raises(AssetResultRegistrationError, match="runtime file is missing"):
        register_result(assets_md, result, tag=TAG, request_path=request, loader=_loader)
    assert assets_md.read_text(encoding="utf-8") == original

    _touch_runtime(tmp_path, "barrel")
    with pytest.raises(AssetResultRegistrationError, match="actual type mismatch"):
        register_result(
            assets_md,
            result,
            tag=TAG,
            request_path=request,
            loader=lambda *_: (_ for _ in ()).throw(AssetResultRegistrationError("actual type mismatch")),
        )
    assert assets_md.read_text(encoding="utf-8") == original


def test_background_registration_requires_the_l0_l4_recorded_artifact_bytes(tmp_path):
    asset_id = "sunset"
    assets_md = tmp_path / "ASSETS.md"
    _assets_md(assets_md, [asset_id])
    artifact_path = "res://assets/generated/background-map/sunset.png"
    artifact = tmp_path / artifact_path.removeprefix("res://")
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"validated background")
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps({
            "asset_type": "background-map", "asset_id": asset_id,
            "brief": "a validated sunset background",
        }),
        encoding="utf-8",
    )
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps({
            "asset_type": "background-map",
            "outputs": [{
                "role": "runtime", "path": artifact_path, "godot_type": "Texture2D",
            }],
            "sources": [], "previews": [], "validation": {"passed": True},
        }),
        encoding="utf-8",
    )

    with pytest.raises(AssetResultRegistrationError, match="no validation record"):
        register_result(assets_md, result, tag=TAG, request_path=request, loader=lambda *_: None)

    write_validation_record(
        tmp_path,
        production_family="background-map",
        asset_id=asset_id,
        artifact_path=artifact_path,
    )
    register_result(assets_md, result, tag=TAG, request_path=request, loader=lambda *_: None)

    artifact.write_bytes(b"regenerated without L0-L4")
    with pytest.raises(AssetResultRegistrationError, match="changed since it passed L0-L4"):
        register_result(assets_md, result, tag=TAG, request_path=request, loader=lambda *_: None)


@pytest.mark.parametrize(
    ("family", "godot_type", "suffix"),
    [
        ("character-bundle", "SpriteFrames", ".tres"),
        ("tileset", "TileSet", ".tres"),
        ("fx-bundle", "SpriteFrames", ".tres"),
    ],
)
def test_runtime_families_register_their_final_declared_godot_artifact(
    tmp_path, family, godot_type, suffix
):
    asset_id = "runtime_asset"
    assets_md = tmp_path / "ASSETS.md"
    _assets_md(assets_md, [asset_id])
    artifact = tmp_path / "assets" / "generated" / family / f"{asset_id}{suffix}"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"artifact")
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "asset_type": family,
                "asset_id": asset_id,
                "brief": "runtime asset",
                    **({"spec": {"mode": "animated"}} if family == "fx-bundle" else {}),
            }
        ),
        encoding="utf-8",
    )
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "asset_type": family,
                "outputs": [
                    {
                        "role": "runtime",
                        "path": "res://" + artifact.relative_to(tmp_path).as_posix(),
                        "godot_type": godot_type,
                    }
                ],
                "sources": [],
                "previews": [],
                "validation": {"passed": True},
            }
        ),
        encoding="utf-8",
    )

    register_result(
        assets_md,
        result,
        tag=TAG,
        request_path=request,
        loader=lambda root, path, expected: expected == godot_type,
    )

    snapshot = runtime_snapshot(assets_md, tag=TAG, asset_ids=[asset_id])
    assert snapshot == [
        {
            "asset_id": asset_id,
            "godot_artifact": {
                "type": godot_type,
                "path": "res://" + artifact.relative_to(tmp_path).as_posix(),
            },
        }
    ]


def _native_multi_output_request(family: str, names: list[str]) -> tuple[dict, dict[str, str]]:
    if family in {"ui-kit", "card-kit"}:
        return (
            {
                "styleboxes": [{"output_name": names[0]}],
                "atlas_regions": [{"output_name": names[1]}],
                "theme": None,
            },
            {names[0]: "StyleBoxTexture", names[1]: "AtlasTexture"},
        )
    if family == "compact-prop-pack":
        return (
            {
                "version": 1,
                "atlas": {"width": 32, "height": 16},
                "slots": [
                    {"name": name, "rect": [index * 16, 0, 16, 16], "source": f"sources/{name}.png"}
                    for index, name in enumerate(names)
                ],
            },
            {name: "AtlasTexture" for name in names},
        )
    if family == "platform-strip":
        return (
            {
                "kind": "single",
                "grid": {"columns": len(names), "rows": 1, "cell_width": 8, "cell_height": 8},
                "segments": [
                    {"name": name, "role": role, "slot": [index, 0]}
                    for index, (name, role) in enumerate(zip(names, ("left_cap", "right_cap"), strict=True))
                ],
            },
            {name: "Texture2D" for name in names},
        )
    raise AssertionError(f"unexpected family: {family}")


@pytest.mark.parametrize("family", ["compact-prop-pack", "platform-strip", "ui-kit", "card-kit"])
@pytest.mark.parametrize("case", ["missing", "duplicate", "unknown", "wrong_type"])
def test_multi_output_families_use_request_owned_output_contracts(
    tmp_path, family, case
):
    names = ["first", "second"]
    assets_md = tmp_path / "ASSETS.md"
    _assets_md(assets_md, names)
    spec, expected_types = _native_multi_output_request(family, names)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "asset_type": family,
                "asset_id": "bundle",
                "brief": "two independently consumable assets",
                "spec": spec,
            }
        ),
        encoding="utf-8",
    )
    actual_names = names if case != "missing" else ["first"]
    if case == "duplicate":
        actual_names = ["first", "first", "second"]
    if case == "unknown":
        actual_names = ["first", "second", "unexpected"]
    outputs = []
    for name in actual_names:
        artifact = tmp_path / "assets" / "generated" / family / f"{name}.tres"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"artifact")
        outputs.append(
            {
                "role": "runtime",
                "name": name,
                "path": "res://" + artifact.relative_to(tmp_path).as_posix(),
                "godot_type": "SpriteFrames" if case == "wrong_type" else expected_types.get(name, next(iter(expected_types.values()))),
            }
        )
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "asset_type": family,
                "outputs": outputs,
                "sources": [],
                "previews": [],
                "validation": {"passed": True},
            }
        ),
        encoding="utf-8",
    )
    original = assets_md.read_text(encoding="utf-8")

    with pytest.raises(AssetResultRegistrationError):
        register_result(assets_md, result, tag=TAG, request_path=request, loader=lambda *_: None)

    assert assets_md.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("family", "selector", "selected", "declared", "actual"),
    [
        ("platform-strip", "kind", "atlas", "AtlasTexture", "Texture2D"),
        ("fx-bundle", "mode", "static", "Texture2D", "SpriteFrames"),
        ("fx-bundle", "mode", "animated", "SpriteFrames", "Texture2D"),
    ],
)
def test_variant_contract_rejects_a_sibling_variants_godot_type(
    tmp_path, family, selector, selected, declared, actual
):
    asset_id = "variant_asset"
    assets_md = tmp_path / "ASSETS.md"
    _assets_md(assets_md, [asset_id])
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "asset_type": family,
                "asset_id": asset_id,
                "brief": "variant type must stay fail closed",
                "spec": {
                    selector: selected,
                    "outputs": [{"name": asset_id, "role": "runtime", "godot_type": declared}],
                },
            }
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "assets" / "generated" / family / f"{asset_id}.tres"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"artifact")
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "asset_type": family,
                "outputs": [{
                    "role": "runtime", "name": asset_id,
                    "path": "res://" + artifact.relative_to(tmp_path).as_posix(),
                    "godot_type": actual,
                }],
                "sources": [], "previews": [], "validation": {"passed": True},
            }
        ),
        encoding="utf-8",
    )
    original = assets_md.read_text(encoding="utf-8")

    with pytest.raises(AssetResultRegistrationError):
        register_result(assets_md, result, tag=TAG, request_path=request, loader=lambda *_: None)

    assert assets_md.read_text(encoding="utf-8") == original
