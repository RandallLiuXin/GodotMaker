"""One representative delivery per public Asset Skill *route*.

Each builder here materializes the files a validated result names and then runs
that route's *real* deterministic entry-draft builder over them. The result is
the set of stable entries `/gm-asset` Step 5 would register, so the closure test
can carry them the rest of the way — root index, ASSETS.md, and the runtime
resolver — without re-implementing any adapter.

The table is keyed by `(family, variant)` from `tools/asset_family_registry.py`,
not by family. A Skill that accepts more than one request shape has one
registration chain per shape: `platform-strip` publishes per-segment `Texture2D`
files for `kind: "single"` and cut `AtlasTexture` regions for `kind: "atlas"`,
and `fx-bundle` compiles a `Texture2D` for a static effect and a `SpriteFrames`
for an animated one. Driving only one variant would let the other's missing
adapter pass every family-level assertion.

A route declared in the registry with no delivery here fails
`test_asset_family_closure.py` rather than being skipped, which is the whole
point: no route may enter a release without being driven end to end.

Every route is driven through its production entry-draft builder. A new public
route without a delivery here fails the closure suite instead of being skipped.
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
    build_fx_bundle_entry_draft,
    write_character_bundle_entry_draft,
    write_fx_bundle_entry_draft,
)
from asset_build_record import write_validation_record  # noqa: E402
from asset_compact_prop_pack_entry_draft import (  # noqa: E402
    build_compact_prop_pack_entry_drafts,
)
from asset_curation_entry_draft import write_fx_static_entry_draft  # noqa: E402
from asset_family_registry import FAMILIES  # noqa: E402
from asset_finalize_entry_draft import build_finalize_entry_draft  # noqa: E402
from asset_platform_strip_entry_draft import (  # noqa: E402
    build_platform_strip_entry_drafts,
)
from asset_scene_prop_set_entry_draft import (  # noqa: E402
    build_scene_prop_set_entry_draft,
)
from asset_tileset_entry_draft import build_tileset_entry_draft  # noqa: E402
from asset_ui_card_entry_draft import build_ui_card_entry_drafts  # noqa: E402

TAG = "v0.1.0"
ASSETS_DIR = REPO_ROOT / "skills" / "assets"
LEVELS_PASSED = {level: True for level in ("L0", "L1", "L2", "L3", "L4")}


@dataclass
class Delivery:
    """What one validated route delivery produced, ready for registration."""

    family: str
    #: The existing ASSETS.md planning rows this one production satisfies.
    assets_rows: tuple[str, ...]
    #: Stable entries the route's deterministic builder drafted.
    entries: list[dict[str, Any]]
    request_path: Path | None = None
    result_path: Path | None = None
    #: Set for bundle families; the manifest writer needs the original request.
    bundle: bool = False
    variant: str = "default"


@dataclass(frozen=True)
class RouteFixture:
    """Test-only representative input for one declared route."""

    result: str
    request: str | None = None
    promotes_from_compiled: bool = False


ROUTE_FIXTURES: dict[tuple[str, str], RouteFixture] = {
    ("background-map", "default"): RouteFixture(
        result="skills/assets/background-map/fixtures/representative-result.json"
    ),
    ("card-kit", "default"): RouteFixture(
        request="skills/assets/card-kit/fixtures/representative-request.json",
        result="skills/assets/card-kit/fixtures/representative-result.json",
    ),
    ("character-bundle", "default"): RouteFixture(
        request="skills/assets/character-bundle/fixtures/valid-request.json",
        result="skills/assets/character-bundle/fixtures/valid-result.json",
        promotes_from_compiled=True,
    ),
    ("compact-prop-pack", "default"): RouteFixture(
        result="skills/assets/compact-prop-pack/fixtures/representative-result.json"
    ),
    ("fx-bundle", "static"): RouteFixture(
        request="skills/assets/fx-bundle/fixtures/static-request.json",
        result="skills/assets/fx-bundle/fixtures/static-result.json",
        promotes_from_compiled=True,
    ),
    ("fx-bundle", "animated"): RouteFixture(
        request="skills/assets/fx-bundle/fixtures/animated-request.json",
        result="skills/assets/fx-bundle/fixtures/animated-result.json",
        promotes_from_compiled=True,
    ),
    ("platform-strip", "single"): RouteFixture(
        request="skills/assets/platform-strip/fixtures/representative-single-request.json",
        result="skills/assets/platform-strip/fixtures/representative-single-result.json",
    ),
    ("platform-strip", "atlas"): RouteFixture(
        request="skills/assets/platform-strip/fixtures/representative-request.json",
        result="skills/assets/platform-strip/fixtures/representative-result.json",
    ),
    ("scene-prop-set", "default"): RouteFixture(
        result="skills/assets/scene-prop-set/fixtures/representative-result.json"
    ),
    ("screen-reference", "default"): RouteFixture(
        request="skills/assets/_shared/samples/request/screen-reference.json",
        result="skills/assets/screen-reference/fixtures/representative-result.json",
    ),
    ("tileset", "default"): RouteFixture(
        result="skills/assets/tileset/fixtures/representative-result.json"
    ),
    ("ui-kit", "default"): RouteFixture(
        request="skills/assets/ui-kit/fixtures/representative-request.json",
        result="skills/assets/ui-kit/fixtures/representative-result.json",
    ),
}


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


def route_fixture(family: str, variant: str = "default") -> RouteFixture:
    return ROUTE_FIXTURES[(family, variant)]


def representative_result(family: str, variant: str = "default") -> dict[str, Any]:
    return read_fixture(route_fixture(family, variant).result)


def representative_request(family: str, variant: str = "default") -> dict[str, Any]:
    fixture = route_fixture(family, variant).request
    if fixture is None:
        raise AssertionError(f"{family}[{variant}] has no representative request")
    return read_fixture(fixture)


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
        request = representative_request(family)
        result = representative_result(family)
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


def _fx_static(root: Path) -> Delivery:
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
    request = representative_request("fx-bundle", "static")
    result = representative_result("fx-bundle", "static")
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
        variant="static",
    )


def _fx_animated(root: Path) -> Delivery:
    request = representative_request("fx-bundle", "animated")
    result = representative_result("fx-bundle", "animated")
    asset_id = request["asset_id"]
    action = request["spec"]["actions"][0]
    stable = f"assets/generated/fx-bundle/{asset_id}"
    frames = action["frame_names"]
    metadata = {
        "frame_count": len(frames),
        "final_sheet_path": f"{stable}/{asset_id}_sheet.png",
        "final_frame_paths": [
            f"{stable}/{asset_id}_{action['name']}_{frame}.png" for frame in frames
        ],
        "align": "center",
        "shared_scale": True,
        "action_name": action["name"],
        "fps": action["fps"],
        "loop": action["loop"],
        "frame_durations": action["frame_durations"],
        "edge_touch_frames": [],
        "scale_reference": {"checked": False},
        "cell_size": 256,
        "grid": {"cols": action["grid"]["columns"], "rows": action["grid"]["rows"]},
        "frame_labels": frames,
    }
    for relative in [metadata["final_sheet_path"], *metadata["final_frame_paths"]]:
        write_png(root, relative)
    request_path = write_json(root, "ASSET_REQUEST.json", request)
    metadata_path = write_json(
        root,
        f".godotmaker/asset-generation/work/{action['name']}/pipeline-meta.json",
        metadata,
    )
    result_path = write_json(root, "fx-animated-result.json", result)
    out = root / ".godotmaker/asset-generation/work/entries/fx.json"

    # Compiles first, so the entry is drafted `compiled` and the passing result
    # promotes that exact build on a second run.
    write_fx_bundle_entry_draft(
        metadata_path,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=root,
        out=out,
    )
    promoted = build_fx_bundle_entry_draft(
        metadata_path,
        request_path=request_path,
        asset_id=asset_id,
        tag=TAG,
        project_root=root,
        result_path=result_path,
    )
    return Delivery(
        "fx-bundle",
        (asset_id,),
        [promoted["entry"]],
        request_path=request_path,
        result_path=result_path,
        variant="animated",
    )


# --------------------------------------------------------------------------
# open families: the delivery validates, the registration chain refuses
# --------------------------------------------------------------------------


def _background_map(root: Path) -> Delivery:
    """A validated background registered from the image L0-L4 examined.

    Source and artifact are the same PNG: Godot's default import already is the
    `Texture2D`, so nothing wraps it in a `.tres`. The builder binds the passing
    result to the validation record the family's standalone runner wrote, which
    is what stops a later regeneration at the same stable path from registering
    a build no ladder ever saw.
    """
    asset_id = "forest_dawn"
    relative = f"assets/generated/background-map/{asset_id}/{asset_id}.png"
    write_png(root, relative, (16, 9))
    report = _finalize_report(root, asset_id=asset_id, relative=relative)
    result = representative_result("background-map")
    # The fixture is written against its own asset id; retarget it at this
    # delivery's stable path rather than inventing a second result shape.
    result = json.loads(
        json.dumps(result).replace(
            "assets/generated/background-map/forest_dawn/forest_dawn.png", relative
        )
    )
    result_path = write_json(root, "background-result.json", result)
    write_validation_record(
        root,
        production_family="background-map",
        asset_id=asset_id,
        artifact_path=f"res://{relative}",
    )

    entry = build_finalize_entry_draft(
        report,
        asset_id=asset_id,
        tag=TAG,
        production_family="background-map",
        project_root=root,
        result_path=result_path,
    )
    return Delivery(
        "background-map",
        (asset_id,),
        [entry],
        result_path=result_path,
    )


def _platform_strip(variant: str) -> Callable[[Path], Delivery]:
    """Register every validated segment through the platform-strip builder."""

    def build(root: Path) -> Delivery:
        request = representative_request("platform-strip", variant)
        result = representative_result("platform-strip", variant)
        declared = FAMILIES["platform-strip"].variant(variant)
        _materialize_result_files(root, result)
        assert {item["godot_type"] for item in result["outputs"]} == set(
            declared.artifact_types
        )
        request_path = root / f"{variant}-platform-strip-request.json"
        result_path = root / f"{variant}-platform-strip-result.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        result_path.write_text(json.dumps(result), encoding="utf-8")
        entries = build_platform_strip_entry_drafts(
            request_path, result_path, tag=TAG, project_root=root
        )
        return Delivery(
            "platform-strip",
            tuple(item["name"] for item in result["outputs"]),
            entries,
            request_path=request_path,
            result_path=result_path,
            bundle=True,
            variant=variant,
        )

    return build


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

DELIVERIES: dict[tuple[str, str], Callable[[Path], Delivery]] = {
    ("background-map", "default"): _background_map,
    ("card-kit", "default"): _kit("card-kit"),
    ("character-bundle", "default"): _character_bundle,
    ("compact-prop-pack", "default"): _compact_prop_pack,
    ("fx-bundle", "static"): _fx_static,
    ("fx-bundle", "animated"): _fx_animated,
    ("platform-strip", "single"): _platform_strip("single"),
    ("platform-strip", "atlas"): _platform_strip("atlas"),
    ("scene-prop-set", "default"): _scene_prop_set,
    ("screen-reference", "default"): _screen_reference,
    ("tileset", "default"): _tileset,
    ("ui-kit", "default"): _kit("ui-kit"),
}
