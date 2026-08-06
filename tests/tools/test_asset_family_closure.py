"""Registration closure for every public family route.

The request/result pair for a registration test is a handoff from that
family's standalone validator.  Fixtures that the validator would reject are
not valid registration fixtures: they cannot occur on the production route.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "skills" / "assets" / "_shared")]

from asset_family_registry import routes, variant_for_request  # noqa: E402
from asset_build_record import write_validation_record  # noqa: E402
from asset_result_registration import register_result, runtime_snapshot  # noqa: E402
from asset_skill_contract_check import check_request, check_result  # noqa: E402


TAG = "v0.1.0"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _props(family: str) -> tuple[dict, dict]:
    asset_id = "market"
    root = f"res://assets/generated/{family}/{asset_id}"
    slots = [
        {"name": "crate", "rect": [0, 0, 16, 16], "source": "source/crate.png"},
        {"name": "lamp", "rect": [16, 0, 16, 16], "source": "source/lamp.png"},
    ]
    return (
        {
            "asset_type": family,
            "asset_id": asset_id,
            "brief": "Two clearly separated scene props.",
            "spec": {"version": 1, "atlas": {"width": 32, "height": 16}, "slots": slots},
        },
        {
            "asset_type": family,
            "outputs": [
                {"role": "runtime", "name": slot["name"], "path": f"{root}/{slot['name']}.tres", "godot_type": "AtlasTexture"}
                for slot in slots
            ],
            "sources": [{"path": f"{root}/{asset_id}.png", "layout": "region_atlas"}],
            "previews": [],
            "validation": {"passed": True, "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")}},
        },
    )


def _platform(kind: str) -> tuple[dict, dict]:
    asset_id = "bridge"
    root = f"res://assets/generated/platform-strip/{asset_id}"
    segments = [
        {"name": "left", "role": "left_cap", "slot": [0, 0]},
        {"name": "middle", "role": "repeat_middle", "slot": [1, 0]},
        {"name": "right", "role": "right_cap", "slot": [2, 0]},
    ]
    suffix, godot_type, layout = (".png", "Texture2D", "single") if kind == "single" else (".tres", "AtlasTexture", "region_atlas")
    source = f"{root}/{asset_id}.png" if kind == "atlas" else None
    return (
        {"asset_type": "platform-strip", "asset_id": asset_id, "brief": "A three-piece bridge.", "spec": {"kind": kind, "grid": {"columns": 3, "rows": 1, "cell_width": 16, "cell_height": 16}, "segments": segments}},
        {
            "asset_type": "platform-strip",
            "outputs": [{"role": "runtime", "name": item["name"], "path": f"{root}/{item['name']}{suffix}", "godot_type": godot_type} for item in segments],
            "sources": ([{"path": source, "layout": layout}] if source else [{"path": f"{root}/{item['name']}.png", "layout": layout} for item in segments]),
            "previews": [],
            "validation": {"passed": True, "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")}},
        },
    )


def _background() -> tuple[dict, dict]:
    asset_id = "sunset"
    path = f"res://assets/generated/background-map/{asset_id}/{asset_id}.png"
    return (
        {"asset_type": "background-map", "asset_id": asset_id, "brief": "A quiet sunset background."},
        {"asset_type": "background-map", "outputs": [{"role": "runtime", "name": asset_id, "path": path, "godot_type": "Texture2D"}], "sources": [{"path": path, "layout": "single"}], "previews": [], "validation": {"passed": True, "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")}}},
    )


def _screen_reference() -> tuple[dict, dict]:
    return _json(ROOT / "skills/assets/_shared/samples/request/screen-reference.json"), _json(ROOT / "skills/assets/_shared/samples/result/screen-reference.json")


def _fixture(family: str, request_name: str, result_name: str) -> tuple[dict, dict]:
    fixtures = ROOT / "skills" / "assets" / family / "fixtures"
    return _json(fixtures / request_name), _json(fixtures / result_name)


def _handoff(family: str, variant: str) -> tuple[dict, dict]:
    if family == "background-map":
        return _background()
    if family == "screen-reference":
        return _screen_reference()
    if family in {"compact-prop-pack", "scene-prop-set"}:
        return _props(family)
    if family == "platform-strip":
        return _platform(variant)
    if family == "fx-bundle":
        return _fixture(family, f"{variant}-request.json", f"{variant}-result.json")
    if family == "character-bundle":
        return _fixture(family, "valid-resolved-request.json", "valid-result.json")
    if family in {"ui-kit", "card-kit"}:
        return _fixture(family, "representative-request.json", "representative-result.json")
    if family == "tileset":
        recipe = _json(ROOT / "skills/assets/tileset/fixtures/orthogonal-square-recipe.json")
        request = {"asset_type": "tileset", "asset_id": "grassland", "brief": "A square grass tileset.", "spec": recipe}
        return request, _json(ROOT / "skills/assets/tileset/fixtures/representative-result.json")
    raise AssertionError(f"no closure handoff for {family}/{variant}")


def _character_handoff(user_canonical: bool) -> tuple[dict, dict]:
    request, result = _fixture("character-bundle", "valid-resolved-request.json", "valid-result.json")
    if user_canonical:
        return request, result
    request.pop("references")
    asset_id = request["asset_id"]
    result["outputs"].append(
        {
            "role": "reference",
            "name": "canonical",
            "path": f"res://assets/generated/character-bundle/{asset_id}/{asset_id}_canonical.png",
            "godot_type": "Texture2D",
        }
    )
    return request, result


def _assets_md(path: Path, request: dict, result: dict) -> list[str]:
    runtime = [output for output in result["outputs"] if output["role"] == "runtime"]
    names = [output.get("name", request["asset_id"]) for output in runtime]
    if not runtime:
        names = [request["asset_id"]]
    rows = "\n".join(
        f"| {index} | {TAG} | {name} | prop | 64x64 | family={request['asset_type']} | - | - | MISSING |"
        for index, name in enumerate(names, 1)
    )
    path.write_text(
        "# Assets\n\n"
        "| # | Tag | Name | Type | Size | Generation Params | Runtime Type | Runtime Path | Status |\n"
        "|---|-----|------|------|------|-------------------|--------------|--------------|--------|\n"
        + rows + "\n",
        encoding="utf-8",
    )
    return names


@pytest.mark.parametrize("family,variant", [(item.family, route.variant) for item, route in routes()])
def test_every_validated_family_route_closes_into_a_snapshot(tmp_path, family, variant):
    request, result = _handoff(family, variant)
    # Keep the handoff at the same public boundary as standalone validation.
    check_request(request)
    check_result(result)
    assert result["validation"]["passed"] is True
    assert variant_for_request(request).variant == variant

    assets_md = tmp_path / "ASSETS.md"
    names = _assets_md(assets_md, request, result)
    for output in result["outputs"]:
        file_path = tmp_path / output["path"].removeprefix("res://")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"validated fixture")
    for source in result["sources"]:
        if source["path"].startswith("res://"):
            file_path = tmp_path / source["path"].removeprefix("res://")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"validated source")
    if family == "background-map":
        write_validation_record(
            tmp_path,
            production_family=family,
            asset_id=request["asset_id"],
            artifact_path=result["outputs"][0]["path"],
        )

    request_path, result_path = tmp_path / "request.json", tmp_path / "result.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result_path.write_text(json.dumps(result), encoding="utf-8")
    registered = register_result(assets_md, result_path, tag=TAG, request_path=request_path, loader=lambda *_: None)

    assert registered["updated"] == names
    if family == "screen-reference":
        assert "| reference | references/main_menu.png | source_ready |" in assets_md.read_text(encoding="utf-8")
    else:
        snapshot = runtime_snapshot(assets_md, tag=TAG, asset_ids=names)
        assert [entry["asset_id"] for entry in snapshot] == names


@pytest.mark.parametrize("user_canonical", [True, False], ids=["user-canonical", "generated-canonical"])
def test_character_canonical_handoffs_close_without_registering_reference_evidence(
    tmp_path, user_canonical
):
    request, result = _character_handoff(user_canonical)
    check_request(request)
    check_result(result)
    assets_md = tmp_path / "ASSETS.md"
    names = _assets_md(assets_md, request, result)
    for output in result["outputs"]:
        file_path = tmp_path / output["path"].removeprefix("res://")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"validated fixture")
    request_path, result_path = tmp_path / "request.json", tmp_path / "result.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result_path.write_text(json.dumps(result), encoding="utf-8")

    registered = register_result(assets_md, result_path, tag=TAG, request_path=request_path, loader=lambda *_: None)

    assert registered["updated"] == names == [request["asset_id"]]
    assert "canonical" not in assets_md.read_text(encoding="utf-8")
