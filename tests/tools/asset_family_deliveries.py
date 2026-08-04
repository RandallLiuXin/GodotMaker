"""One representative delivery per public first-class Asset Skill family.

Each builder here materializes the files a family's validated result names and
then runs that family's *real* deterministic entry-draft builder over them. The
result is the set of stable entries `/gm-asset` Step 5 would register, so the
closure test can carry them the rest of the way — root index, ASSETS.md, and the
runtime resolver — without re-implementing any adapter.

The table is keyed by `tools/asset_family_registry.py`. A family declared there
with no delivery here fails `test_asset_family_closure.py` rather than being
skipped, which is the whole point: a family may not enter a release with a
registration chain nobody ever drove end to end.

Families whose chain is still open (`registration_closure="open"`) get a builder
too. Theirs raises `RegistrationGap`, carrying the concrete mechanical refusal
that proves the gap is real. When the adapter lands upstream the refusal stops
happening and the closure test fails until the registry is updated.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_action_entry_draft import (  # noqa: E402
    build_character_bundle_entry_draft,
    write_character_bundle_entry_draft,
)
from asset_assets_md_update import AssetsMdUpdateError, update_assets_md  # noqa: E402
from asset_compact_prop_pack_entry_draft import (  # noqa: E402
    build_compact_prop_pack_entry_drafts,
)
from asset_curation_entry_draft import write_fx_static_entry_draft  # noqa: E402
from asset_family_registry import FAMILIES  # noqa: E402
from asset_finalize_entry_draft import build_finalize_entry_draft  # noqa: E402
from asset_scene_prop_set_entry_draft import (  # noqa: E402
    build_scene_prop_set_entry_draft,
)
from asset_stable_entry import (  # noqa: E402
    StableEntryError,
    entry_relative_path,
    write_entry,
)
from asset_tileset_entry_draft import build_tileset_entry_draft  # noqa: E402
from asset_ui_card_entry_draft import build_ui_card_entry_drafts  # noqa: E402

TAG = "v0.1.0"
ASSETS_DIR = REPO_ROOT / "skills" / "assets"
LEVELS_PASSED = {level: True for level in ("L0", "L1", "L2", "L3", "L4")}


class RegistrationGap(Exception):
    """Raised by a family whose validated delivery cannot be registered today."""


@dataclass
class Delivery:
    """What one validated family delivery produced, ready for registration."""

    family: str
    #: The existing ASSETS.md planning rows this one production satisfies.
    assets_rows: tuple[str, ...]
    #: Stable entries the family's deterministic builder drafted.
    entries: list[dict[str, Any]]
    request_path: Path | None = None
    result_path: Path | None = None
    #: Set for bundle families; the manifest writer needs the original request.
    bundle: bool = False


# --------------------------------------------------------------------------
# file helpers
# --------------------------------------------------------------------------


def _relative(res_path: str) -> str:
    return res_path[len("res://"):] if res_path.startswith("res://") else res_path


def write_png(root: Path, path: str, size: tuple[int, int] = (8, 8)) -> Path:
    target = root / _relative(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", size, (255, 255, 255, 255)).save(target)
    return target


def write_text(root: Path, path: str, body: str = "stub") -> Path:
    target = root / _relative(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def write_json(root: Path, path: str, value: Any) -> Path:
    target = root / _relative(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return target


def read_fixture(relative: str) -> Any:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def representative_result(family: str) -> dict[str, Any]:
    return read_fixture(FAMILIES[family].representative_result)


def _materialize_result_files(root: Path, result: dict[str, Any]) -> None:
    """Create every file a result declares, matching its extension."""
    for item in [*result["outputs"], *result["sources"], *result["previews"]]:
        path = item["path"]
        if path.endswith(".png"):
            write_png(root, path)
        elif path.endswith(".json"):
            write_json(root, path, {"stub": True})
        else:
            write_text(root, path, '[gd_resource type="Resource"]\n')


def _finalize_report(root: Path, *, asset_id: str, relative: str) -> Path:
    """The exact report shape `asset_image_finalize.py --require-aspect` prints."""
    target = root / relative
    return write_json(
        root,
        f".godotmaker/asset-generation/reports/{asset_id}_finalize.json",
        {
            "ok": True,
            "source": f".godotmaker/asset-generation/sources/{asset_id}_source.png",
            "path": relative,
            "bytes": target.stat().st_size,
            "width": 16,
            "height": 9,
            "required_aspect": "16:9",
            "aspect_delta": 0.0,
            "aspect_tolerance": 0.03,
            "label": asset_id,
            "asset_id": asset_id,
        },
    )


# --------------------------------------------------------------------------
# closed families
# --------------------------------------------------------------------------


def _screen_reference(root: Path) -> Delivery:
    asset_id = "main_menu"
    relative = f"references/{asset_id}.png"
    write_png(root, relative, (16, 9))
    report = _finalize_report(root, asset_id=asset_id, relative=relative)

    entry = build_finalize_entry_draft(
        report,
        asset_id=asset_id,
        tag=TAG,
        production_family="screen-reference",
        project_root=root,
    )
    return Delivery("screen-reference", (asset_id,), [entry])


def _tileset(root: Path) -> Delivery:
    asset_id = "grassland"
    result = representative_result("tileset")
    request = {
        "asset_type": "tileset",
        "asset_id": asset_id,
        "brief": "A grassland tile atlas.",
        "provider": "codex",
        "spec": {
            "autotile_profile": "marching_squares_15",
            "tile_size": {"width": 16, "height": 16},
            "terrain": {
                "name": "grassland",
                "foreground_material": "dirt",
                "background_material": "grass",
            },
        },
    }
    _materialize_result_files(root, result)
    request_path = write_json(root, "ASSET_REQUEST.json", request)
    result_path = write_json(root, "tileset-result.json", result)

    entry = build_tileset_entry_draft(
        request_path, result_path, tag=TAG, project_root=root
    )
    return Delivery(
        "tileset",
        (asset_id,),
        [entry],
        request_path=request_path,
        result_path=result_path,
    )


def _kit(family: str) -> Callable[[Path], Delivery]:
    def build(root: Path) -> Delivery:
        spec = FAMILIES[family]
        request = read_fixture(spec.representative_request)
        result = read_fixture(spec.representative_result)
        _materialize_result_files(root, result)
        request_path = write_json(root, f"{family}-request.json", request)
        result_path = write_json(root, f"{family}-result.json", result)

        entries = build_ui_card_entry_drafts(
            request_path, result_path, tag=TAG, project_root=root
        )
        return Delivery(
            family,
            (request["asset_id"],),
            entries,
            request_path=request_path,
            result_path=result_path,
            bundle=True,
        )

    return build


def _compact_prop_pack(root: Path) -> Delivery:
    asset_id = "market-props"
    samples = ASSETS_DIR / "compact-prop-pack" / "samples"
    declaration = json.loads(
        (samples / "declaration" / "spec.json").read_text(encoding="utf-8")
    )
    result = representative_result("compact-prop-pack")
    stable = root / "assets" / "generated" / "compact-prop-pack" / asset_id
    stable.mkdir(parents=True)
    (stable / f"{asset_id}.png").write_bytes(
        (samples / "atlas" / f"{asset_id}.png").read_bytes()
    )
    (stable / f"{asset_id}.json").write_text(
        (samples / "atlas" / f"{asset_id}.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for slot in declaration["slots"]:
        (stable / f"{slot['name']}.tres").write_text(
            '[gd_resource type="AtlasTexture"]\n', encoding="utf-8"
        )
    request = {
        "asset_type": "compact-prop-pack",
        "asset_id": asset_id,
        "brief": "A compact market prop pack.",
        "provider": "codex",
        "spec": declaration,
    }
    request_path = write_json(root, "request.json", request)
    result_path = write_json(root, "result.json", result)

    entries = build_compact_prop_pack_entry_drafts(
        request_path, result_path, tag=TAG, project_root=root
    )
    return Delivery(
        "compact-prop-pack",
        (asset_id,),
        entries,
        request_path=request_path,
        result_path=result_path,
        bundle=True,
    )


def _scene_prop_set(root: Path) -> Delivery:
    asset_id = "market-scene"
    samples = ASSETS_DIR / "scene-prop-set" / "samples"
    declaration = json.loads(
        (samples / "declaration" / "spec.json").read_text(encoding="utf-8")
    )
    result = representative_result("scene-prop-set")
    stable = root / "assets" / "generated" / "scene-prop-set" / asset_id
    stable.mkdir(parents=True)
    (stable / f"{asset_id}.png").write_bytes(
        (samples / "atlas" / f"{asset_id}.png").read_bytes()
    )
    (stable / f"{asset_id}.json").write_text(
        (samples / "atlas" / f"{asset_id}.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for slot in declaration["slots"]:
        (stable / f"{slot['name']}.tres").write_text(
            '[gd_resource type="AtlasTexture"]\n', encoding="utf-8"
        )
    request = {
        "asset_type": "scene-prop-set",
        "asset_id": asset_id,
        "brief": "A painted market prop set.",
        "provider": "codex",
        "spec": declaration,
    }
    request_path = write_json(root, "request.json", request)
    result_path = write_json(root, "result.json", result)

    entry = build_scene_prop_set_entry_draft(
        request_path,
        result_path,
        tag=TAG,
        primary_output=declaration["slots"][0]["name"],
        project_root=root,
    )
    return Delivery(
        "scene-prop-set",
        (asset_id,),
        [entry],
        request_path=request_path,
        result_path=result_path,
    )


def _character_bundle(root: Path) -> Delivery:
    asset_id = "hero"
    stable = f"assets/generated/character-bundle/{asset_id}"
    actions = (("idle", ["idle_01", "idle_02"]), ("walk", ["walk_01", "walk_02"]))
    request = {
        "asset_type": "character-bundle",
        "asset_id": asset_id,
        "brief": "A non-pixel-art hero.",
        "provider": "native",
        "spec": {
            "required_actions": [name for name, _ in actions],
            "frame_canvas_px": 256,
            "actions": [
                {
                    "name": name,
                    "intent": f"A representative {name} cycle.",
                    "grid": {"columns": len(frames), "rows": 1},
                    "frame_names": frames,
                    "fps": 8,
                    "loop": True,
                    "frame_durations": [1] * len(frames),
                }
                for name, frames in actions
            ],
        },
    }
    request_path = write_json(root, "ASSET_REQUEST.json", request)

    baseline = ".godotmaker/asset-generation/work/idle/pipeline-meta.json"
    metadata_paths: list[Path] = []
    for index, (name, frames) in enumerate(actions):
        metadata = {
            "frame_count": len(frames),
            "final_sheet_path": f"{stable}/{asset_id}_{name}_sheet.png",
            "final_frame_paths": [
                f"{stable}/{asset_id}_{name}_{frame}.png" for frame in frames
            ],
            "align": "feet",
            "shared_scale": True,
            "action_name": name,
            "fps": 8,
            "loop": True,
            "frame_durations": [1.0] * len(frames),
            "edge_touch_frames": [],
            "scale_reference": (
                {"checked": False}
                if index == 0
                else {"checked": True, "reference_metadata_path": str(root / baseline)}
            ),
            "cell_size": 256,
            "grid": {"cols": len(frames), "rows": 1},
            "frame_labels": frames,
        }
        for relative in [metadata["final_sheet_path"], *metadata["final_frame_paths"]]:
            write_png(root, relative, (4, 4))
        metadata_paths.append(
            write_json(
                root,
                f".godotmaker/asset-generation/work/{name}/pipeline-meta.json",
                metadata,
            )
        )

    # The compiler runs before L0-L4 can look at what it produced, so the first
    # run drafts `compiled` and the second promotes that exact build to `ready`.
    write_character_bundle_entry_draft(
        metadata_paths,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=root,
        out=root / ".godotmaker/asset-generation/work/entries/compiled.json",
    )
    result = {
        "asset_type": "character-bundle",
        "outputs": [
            {
                "role": "runtime",
                "name": asset_id,
                "path": f"res://{stable}/{asset_id}.tres",
                "godot_type": "SpriteFrames",
            }
        ],
        "sources": [
            {"path": f"res://{stable}/{asset_id}_{name}_sheet.png", "layout": "grid_sheet"}
            for name, _ in actions
        ],
        "previews": [],
        "validation": {"passed": True, "levels": dict(LEVELS_PASSED)},
    }
    result_path = write_json(root, "ASSET_RESULT.json", result)
    built = build_character_bundle_entry_draft(
        metadata_paths,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=root,
        result_path=result_path,
    )
    return Delivery(
        "character-bundle",
        (asset_id,),
        [built["entry"]],
        request_path=request_path,
        result_path=result_path,
    )


def _fx_bundle(root: Path) -> Delivery:
    asset_id = "pickup"
    relative = f"assets/generated/fx-bundle/{asset_id}/{asset_id}.png"
    write_png(root, relative)
    report_path = write_json(
        root,
        f".godotmaker/asset-generation/curation/{asset_id}_source.json",
        {
            "version": 1,
            "asset_id": f"{asset_id}_source",
            "tag": TAG,
            "strategy": "transparent_autoslice",
            "status": "selected",
            "selected_count": 1,
            "rejected_count": 0,
            "candidates": [
                {
                    "candidate_id": f"fx.{asset_id}",
                    "name": asset_id,
                    "state": "selected",
                    "final_path": relative,
                }
            ],
        },
    )
    request = read_fixture(FAMILIES["fx-bundle"].representative_request)
    result = read_fixture(FAMILIES["fx-bundle"].representative_result)
    request_path = write_json(root, "fx-request.json", request)
    result_path = write_json(root, "fx-result.json", result)
    out = root / ".godotmaker/asset-generation/work/entries/fx.json"

    write_fx_static_entry_draft(
        report_path,
        candidate=asset_id,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=root,
        out=out,
    )
    write_fx_static_entry_draft(
        report_path,
        candidate=asset_id,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=root,
        out=out,
        result_path=result_path,
    )
    entry = json.loads(out.read_text(encoding="utf-8"))
    return Delivery(
        "fx-bundle",
        (asset_id,),
        [entry],
        request_path=request_path,
        result_path=result_path,
    )


# --------------------------------------------------------------------------
# open families: the delivery validates, the registration chain refuses
# --------------------------------------------------------------------------


def _background_map(root: Path) -> Delivery:
    """A validated Texture2D background that no adapter can promote to ready."""
    asset_id = "forest_dawn"
    relative = f"assets/generated/background-map/{asset_id}/{asset_id}.png"
    write_png(root, relative, (16, 9))
    report = _finalize_report(root, asset_id=asset_id, relative=relative)

    entry = build_finalize_entry_draft(
        report,
        asset_id=asset_id,
        tag=TAG,
        production_family="background-map",
        project_root=root,
    )
    if entry.get("godot_artifact") or entry["processing_status"] == "ready":
        raise AssertionError(
            "background-map now reaches a ready Texture2D entry; close its gap in "
            "tools/asset_family_registry.py"
        )
    # Prove the refusal at the point it actually bites: the row stays MISSING.
    write_entry(entry, project_root=root, check_files=True)
    assets_md = _planning_table(root, ["forest_dawn"])
    try:
        update_assets_md(
            assets_md, [root / entry_relative_path(TAG, asset_id)]
        )
    except AssetsMdUpdateError as exc:
        raise RegistrationGap(str(exc)) from exc
    raise AssertionError(
        "background-map now completes its ASSETS.md row; close its gap in "
        "tools/asset_family_registry.py"
    )


def _platform_strip(root: Path) -> Delivery:
    """Validated AtlasTexture segments the stable-entry schema cannot hold."""
    result = representative_result("platform-strip")
    _materialize_result_files(root, result)
    segment = result["outputs"][0]
    bundle_id = "wood_bridge"
    source = result["sources"][0]

    draft = {
        "version": 1,
        "asset_id": segment["name"],
        "tag": TAG,
        "production_family": "platform-strip",
        "bundle_id": bundle_id,
        "source_layout": {"type": "region_atlas", "path": source["path"]},
        "godot_artifact": {"type": segment["godot_type"], "path": segment["path"]},
        "processing_status": "ready",
    }
    try:
        write_entry(draft, project_root=root, check_files=True)
    except StableEntryError as exc:
        raise RegistrationGap(str(exc)) from exc
    raise AssertionError(
        "platform-strip now registers its segments; close its gap in "
        "tools/asset_family_registry.py"
    )


# --------------------------------------------------------------------------


def _planning_table(root: Path, rows: list[str], row_type: str = "runtime") -> Path:
    """Write the MISSING current-tag planning rows `/gm-asset` starts from."""
    lines = [
        "# Assets: Closure",
        "",
        "## Asset Table",
        "",
        "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |",
        "|---|-----|------|------|------|-------------------|-----------|--------|",
    ]
    for number, name in enumerate(rows, start=1):
        lines.append(f"| {number} | {TAG} | {name} | {row_type} | - | - | - | MISSING |")
    path = root / "ASSETS.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


planning_table = _planning_table

DELIVERIES: dict[str, Callable[[Path], Delivery]] = {
    "background-map": _background_map,
    "card-kit": _kit("card-kit"),
    "character-bundle": _character_bundle,
    "compact-prop-pack": _compact_prop_pack,
    "fx-bundle": _fx_bundle,
    "platform-strip": _platform_strip,
    "scene-prop-set": _scene_prop_set,
    "screen-reference": _screen_reference,
    "tileset": _tileset,
    "ui-kit": _kit("ui-kit"),
}
