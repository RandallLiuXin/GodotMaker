import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_runtime_resolver import (  # noqa: E402
    AssetRuntimeResolverError,
    resolve_assets_row,
    resolve_manifest_entry,
)
from asset_stable_entry import entry_relative_path, stable_output_dir  # noqa: E402

TAG = "v0.1.0"
ASSET_ID = "player_idle"
FAMILY = "character-bundle"


def source_relative(asset_id: str = ASSET_ID, family: str = FAMILY) -> str:
    return f"{stable_output_dir(family, asset_id)}/{asset_id}_source.png"


def artifact_relative(asset_id: str = ASSET_ID, family: str = FAMILY) -> str:
    return f"{stable_output_dir(family, asset_id)}/{asset_id}.tres"


def make_entry(**overrides):
    entry = {
        "version": 1,
        "asset_id": ASSET_ID,
        "tag": TAG,
        "production_family": FAMILY,
        "source_layout": {"type": "grid_sheet", "path": f"res://{source_relative()}"},
        "godot_artifact": {"type": "SpriteFrames", "path": f"res://{artifact_relative()}"},
        "processing_status": "ready",
    }
    entry.update(overrides)
    return entry


def write_entry(project_root: Path, entry: dict) -> str:
    pointer = entry_relative_path(entry["tag"], entry["asset_id"])
    path = project_root / pointer
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry), encoding="utf-8")
    return pointer


def touch(project_root: Path, relative: str) -> None:
    path = project_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"asset")


def write_ready_entry(project_root: Path, **overrides) -> tuple[dict, str]:
    entry = make_entry(**overrides)
    touch(project_root, entry["source_layout"]["path"].removeprefix("res://"))
    artifact = entry.get("godot_artifact")
    if artifact is not None:
        touch(project_root, artifact["path"].removeprefix("res://"))
    return entry, write_entry(project_root, entry)


def write_assets_md(project_root: Path, pointer: str, status: str = "generated") -> Path:
    path = project_root / "ASSETS.md"
    path.write_text(
        "| ID | Tag | Name | Type | Size | Generation Params | Path | Status |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"| 1 | {TAG} | {ASSET_ID} | sprite | 128x128 | prompt=hero; manifest_entry={pointer} | assets/generated/player.tres | {status} |\n",
        encoding="utf-8",
    )
    return path


def expected_snapshot() -> dict:
    return {
        "asset_id": ASSET_ID,
        "production_family": FAMILY,
        "source_layout": {"type": "grid_sheet", "path": f"res://{source_relative()}"},
        "godot_artifact": {"type": "SpriteFrames", "path": f"res://{artifact_relative()}"},
    }


def test_resolves_canonical_manifest_entry_to_minimal_stable_snapshot(tmp_path):
    _, pointer = write_ready_entry(tmp_path)

    assert resolve_manifest_entry(pointer, project_root=tmp_path) == expected_snapshot()
    assert list(resolve_manifest_entry(pointer, project_root=tmp_path)) == [
        "asset_id",
        "production_family",
        "source_layout",
        "godot_artifact",
    ]


def test_resolves_current_tag_assets_row_and_checks_pointer_identity(tmp_path):
    _, pointer = write_ready_entry(tmp_path)
    assets_md = write_assets_md(tmp_path, pointer)

    assert resolve_assets_row(
        assets_md, tag=TAG, asset_id=ASSET_ID, project_root=tmp_path
    ) == expected_snapshot()


@pytest.mark.parametrize("status", ["pending", "source_ready", "compiled", "failed"])
def test_rejects_non_ready_entries(tmp_path, status):
    entry = make_entry(processing_status=status)
    if status in {"pending", "source_ready", "failed"}:
        entry.pop("godot_artifact")
    _, pointer = write_ready_entry(tmp_path, **entry)

    with pytest.raises(AssetRuntimeResolverError, match=f"processing_status is {status}"):
        resolve_manifest_entry(pointer, project_root=tmp_path)


def test_reference_entry_cannot_appear_as_a_worker_runtime_asset(tmp_path):
    entry = {
        "version": 1,
        "asset_id": "scene_main",
        "tag": TAG,
        "production_family": "screen-reference",
        "source_layout": {"type": "reference", "path": "res://references/scene_main.png"},
        "processing_status": "ready",
    }
    touch(tmp_path, "references/scene_main.png")
    pointer = write_entry(tmp_path, entry)

    with pytest.raises(AssetRuntimeResolverError, match="reference-only"):
        resolve_manifest_entry(pointer, project_root=tmp_path)


def test_rejects_legacy_entry_before_returning_a_snapshot(tmp_path):
    entry = make_entry(runtime_artifact="grid_sheet")
    _, pointer = write_ready_entry(tmp_path, **entry)

    with pytest.raises(AssetRuntimeResolverError, match="Legacy runtime_artifact schema"):
        resolve_manifest_entry(pointer, project_root=tmp_path)


def test_rejects_missing_entry_and_runtime_files(tmp_path):
    with pytest.raises(AssetRuntimeResolverError, match="Entry file not found"):
        resolve_manifest_entry(entry_relative_path(TAG, ASSET_ID), project_root=tmp_path)

    entry, pointer = write_ready_entry(tmp_path)
    (tmp_path / entry["source_layout"]["path"].removeprefix("res://")).unlink()
    with pytest.raises(AssetRuntimeResolverError, match="source_layout.path not found"):
        resolve_manifest_entry(pointer, project_root=tmp_path)

    entry, pointer = write_ready_entry(tmp_path)
    (tmp_path / entry["godot_artifact"]["path"].removeprefix("res://")).unlink()
    with pytest.raises(AssetRuntimeResolverError, match="godot_artifact.path not found"):
        resolve_manifest_entry(pointer, project_root=tmp_path)


@pytest.mark.parametrize(
    "pointer",
    [
        "../entry.json",
        ".godotmaker/asset-generation/entries/v0.1.0/../player_idle.json",
        ".godotmaker\\asset-generation\\entries\\v0.1.0\\player_idle.json",
        "C:/outside/entry.json",
    ],
)
def test_rejects_out_of_bounds_manifest_entry_paths(tmp_path, pointer):
    with pytest.raises(AssetRuntimeResolverError):
        resolve_manifest_entry(pointer, project_root=tmp_path)


def test_rejects_noncanonical_pointer_and_assets_identity_mismatch(tmp_path):
    _, pointer = write_ready_entry(tmp_path)
    alternate = ".godotmaker/asset-generation/entries/v0.1.0/alias.json"
    alias = tmp_path / alternate
    alias.parent.mkdir(parents=True, exist_ok=True)
    alias.write_text((tmp_path / pointer).read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(AssetRuntimeResolverError, match="canonical entry path"):
        resolve_manifest_entry(alternate, project_root=tmp_path)

    other_entry = make_entry(
        asset_id="other_asset",
        source_layout={
            "type": "grid_sheet",
            "path": f"res://{source_relative('other_asset')}",
        },
        godot_artifact={
            "type": "SpriteFrames",
            "path": f"res://{artifact_relative('other_asset')}",
        },
    )
    _, other_pointer = write_ready_entry(tmp_path, **other_entry)
    assets_md = write_assets_md(tmp_path, other_pointer)
    with pytest.raises(AssetRuntimeResolverError, match="does not match ASSETS.md asset_id"):
        resolve_assets_row(assets_md, tag=TAG, asset_id=ASSET_ID, project_root=tmp_path)


def test_rejects_missing_or_unready_assets_row(tmp_path):
    _, pointer = write_ready_entry(tmp_path)
    assets_md = write_assets_md(tmp_path, pointer, status="MISSING")

    with pytest.raises(AssetRuntimeResolverError, match="expected 'generated'"):
        resolve_assets_row(assets_md, tag=TAG, asset_id=ASSET_ID, project_root=tmp_path)

    assets_md.write_text(
        assets_md.read_text(encoding="utf-8")
        .replace("manifest_entry=", "entry=")
        .replace("| MISSING |", "| generated |"),
        encoding="utf-8",
    )
    with pytest.raises(AssetRuntimeResolverError, match="missing manifest_entry"):
        resolve_assets_row(assets_md, tag=TAG, asset_id=ASSET_ID, project_root=tmp_path)


def test_cli_outputs_only_the_snapshot_json(tmp_path):
    _, pointer = write_ready_entry(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_runtime_resolver.py"),
            "--project-root",
            str(tmp_path),
            "--manifest-entry",
            pointer,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == expected_snapshot()
