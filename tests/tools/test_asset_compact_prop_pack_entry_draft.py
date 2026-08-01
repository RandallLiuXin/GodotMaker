import json
import sys
from pathlib import Path

import pytest
from PIL import Image


TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_compact_prop_pack_entry_draft import (  # noqa: E402
    CompactPropPackEntryDraftError,
    build_compact_prop_pack_entry_drafts,
    write_compact_prop_pack_entry_drafts,
)


def _documents(tmp_path: Path) -> tuple[Path, Path]:
    root = "res://assets/generated/compact-prop-pack/market"
    request = {
        "asset_type": "compact-prop-pack",
        "asset_id": "market",
        "brief": "A compact market prop pack.",
        "spec": {
            "version": 1,
            "atlas": {"width": 32, "height": 16},
            "slots": [
                {"name": "coin", "rect": [0, 0, 16, 16], "source": "assets/generated/compact-prop-pack/market/normalized/coin.png"},
                {"name": "lantern", "rect": [16, 0, 16, 16], "source": "assets/generated/compact-prop-pack/market/normalized/lantern.png"},
            ],
        },
    }
    result = {
        "asset_type": "compact-prop-pack",
        "outputs": [
            {"role": "runtime", "name": "coin", "path": f"{root}/coin.tres", "godot_type": "AtlasTexture"},
            {"role": "runtime", "name": "lantern", "path": f"{root}/lantern.tres", "godot_type": "AtlasTexture"},
        ],
        "sources": [{"path": f"{root}/market.png", "layout": "region_atlas"}],
        "previews": [],
        "validation": {"passed": True, "levels": {level: True for level in ("L0", "L1", "L2", "L3", "L4")}},
    }
    output = tmp_path / "assets/generated/compact-prop-pack/market"
    output.mkdir(parents=True)
    Image.new("RGBA", (32, 16), (0, 0, 0, 0)).save(output / "market.png")
    (output / "market.json").write_text(
        json.dumps(
            {
                "version": 1,
                "atlas_path": f"{root}/market.png",
                "regions": [
                    {"name": "coin", "rect": [0, 0, 16, 16]},
                    {"name": "lantern", "rect": [16, 0, 16, 16]},
                ],
            }
        ),
        encoding="utf-8",
    )
    for name in ("coin", "lantern"):
        (output / f"{name}.tres").write_text("[gd_resource type=\"AtlasTexture\"]")
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result_path.write_text(json.dumps(result), encoding="utf-8")
    return request_path, result_path


def test_builds_one_ready_entry_per_logical_prop_with_shared_bundle(tmp_path):
    request_path, result_path = _documents(tmp_path)

    entries = build_compact_prop_pack_entry_drafts(
        request_path, result_path, tag="v0.1.0", project_root=tmp_path
    )

    assert [entry["asset_id"] for entry in entries] == ["market--coin", "market--lantern"]
    assert {entry["bundle_id"] for entry in entries} == {"market"}
    assert {entry["source_layout"]["path"] for entry in entries} == {
        "res://assets/generated/compact-prop-pack/market/market.png"
    }
    assert {entry["godot_artifact"]["path"] for entry in entries} == {
        "res://assets/generated/compact-prop-pack/market/coin.tres",
        "res://assets/generated/compact-prop-pack/market/lantern.tres",
    }


def test_writer_serializes_each_logical_draft_and_rejects_incomplete_ladder(tmp_path):
    request_path, result_path = _documents(tmp_path)
    output = tmp_path / "drafts"
    written = write_compact_prop_pack_entry_drafts(
        request_path, result_path, tag="v0.1.0", project_root=tmp_path, out_dir=output
    )
    assert written["count"] == 2
    assert {Path(path).name for path in written["drafts"]} == {
        "market--coin.json",
        "market--lantern.json",
    }

    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["validation"]["levels"]["L4"] = False
    result["validation"]["passed"] = False
    result_path.write_text(json.dumps(result), encoding="utf-8")
    with pytest.raises(CompactPropPackEntryDraftError, match="passed L0-L4"):
        build_compact_prop_pack_entry_drafts(
            request_path, result_path, tag="v0.1.0", project_root=tmp_path
        )


def test_entry_drafts_reject_tampered_metadata_and_unsafe_logical_names(tmp_path):
    request_path, result_path = _documents(tmp_path)
    metadata_path = tmp_path / "assets/generated/compact-prop-pack/market/market.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["regions"][1]["rect"] = [0, 0, 16, 16]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(CompactPropPackEntryDraftError, match="exactly match"):
        build_compact_prop_pack_entry_drafts(
            request_path, result_path, tag="v0.1.0", project_root=tmp_path
        )

    metadata["regions"][1]["rect"] = [16, 0, 16, 16]
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["spec"]["slots"][0]["name"] = "../outside"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    with pytest.raises(CompactPropPackEntryDraftError, match="safe path segment"):
        build_compact_prop_pack_entry_drafts(
            request_path, result_path, tag="v0.1.0", project_root=tmp_path
        )
