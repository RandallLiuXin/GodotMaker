import json
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_runtime_resolver import (  # noqa: E402
    AssetRuntimeResolverError,
    ROOT_INDEX_PATH,
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


def make_entry(asset_id: str = ASSET_ID, tag: str = TAG, **overrides) -> dict:
    entry = {
        "version": 1,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": FAMILY,
        "source_layout": {
            "type": "grid_sheet",
            "path": f"res://{source_relative(asset_id)}",
        },
        "godot_artifact": {
            "type": "SpriteFrames",
            "path": f"res://{artifact_relative(asset_id)}",
        },
        "processing_status": "ready",
    }
    entry.update(overrides)
    return entry


def touch_declared_files(project_root: Path, entry: dict) -> None:
    paths = [entry["source_layout"]["path"]]
    artifact = entry.get("godot_artifact")
    if artifact is not None:
        paths.append(artifact["path"])
    for res_path in paths:
        target = project_root / res_path.removeprefix("res://")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"asset")


def write_entry(project_root: Path, entry: dict) -> str:
    pointer = entry_relative_path(entry["tag"], entry["asset_id"])
    path = project_root / pointer
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry), encoding="utf-8")
    return pointer


def write_index(project_root: Path, entries: list[dict]) -> None:
    path = project_root / ROOT_INDEX_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "asset_id": entry["asset_id"],
                        "tag": entry["tag"],
                        "entry_path": entry_relative_path(entry["tag"], entry["asset_id"]),
                    }
                    for entry in entries
                ],
            }
        ),
        encoding="utf-8",
    )


def write_assets_md(project_root: Path, rows: list[tuple[str, str, str, str, str]]) -> Path:
    path = project_root / "ASSETS.md"
    body = [
        "| ID | Tag | Name | Type | Size | Generation Params | Path | Status |\n",
        "| --- | --- | --- | --- | --- | --- | --- | --- |\n",
    ]
    for index, (tag, asset_id, pointer, status, params) in enumerate(rows, start=1):
        generation_params = params or f"prompt=hero; manifest_entry={pointer}"
        body.append(
            f"| {index} | {tag} | {asset_id} | sprite | 128x128 | {generation_params} | assets/generated/{asset_id}.tres | {status} |\n"
        )
    path.write_text("".join(body), encoding="utf-8")
    return path


def register(project_root: Path, entry: dict, *, assets: bool = False) -> tuple[dict, str]:
    touch_declared_files(project_root, entry)
    pointer = write_entry(project_root, entry)
    write_index(project_root, [entry])
    if assets:
        write_assets_md(project_root, [(entry["tag"], entry["asset_id"], pointer, "generated", "")])
    return entry, pointer


def expected_snapshot() -> dict:
    return {
        "asset_id": ASSET_ID,
        "production_family": FAMILY,
        "source_layout": {"type": "grid_sheet", "path": f"res://{source_relative()}"},
        "godot_artifact": {"type": "SpriteFrames", "path": f"res://{artifact_relative()}"},
    }


def test_resolves_registered_canonical_entry_to_minimal_stable_snapshot(tmp_path):
    _, pointer = register(tmp_path, make_entry(), assets=True)

    snapshot = resolve_manifest_entry(
        pointer, project_root=tmp_path, assets_md=tmp_path / "ASSETS.md"
    )
    assert snapshot == expected_snapshot()
    assert list(snapshot) == [
        "asset_id",
        "production_family",
        "source_layout",
        "godot_artifact",
    ]


def test_resolves_assets_row_and_direct_cli_with_the_same_handoff_gates(tmp_path):
    _, pointer = register(tmp_path, make_entry(), assets=True)

    assert resolve_assets_row(
        tmp_path / "ASSETS.md", tag=TAG, asset_id=ASSET_ID, project_root=tmp_path
    ) == expected_snapshot()
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


@pytest.mark.parametrize("status", ["pending", "source_ready", "compiled", "failed"])
def test_rejects_non_ready_entries_even_when_registered(tmp_path, status):
    entry = make_entry(processing_status=status)
    if status in {"pending", "source_ready", "failed"}:
        entry.pop("godot_artifact")
    _, pointer = register(tmp_path, entry, assets=True)

    with pytest.raises(AssetRuntimeResolverError, match=f"processing_status is {status}"):
        resolve_manifest_entry(pointer, project_root=tmp_path, assets_md=tmp_path / "ASSETS.md")


def test_reference_entry_cannot_appear_as_a_worker_runtime_asset(tmp_path):
    entry = {
        "version": 1,
        "asset_id": "scene_main",
        "tag": TAG,
        "production_family": "screen-reference",
        "source_layout": {"type": "reference", "path": "res://references/scene_main.png"},
        "processing_status": "ready",
    }
    _, pointer = register(tmp_path, entry, assets=True)

    with pytest.raises(AssetRuntimeResolverError, match="reference-only"):
        resolve_manifest_entry(pointer, project_root=tmp_path, assets_md=tmp_path / "ASSETS.md")


def test_rejects_legacy_entry_before_returning_a_snapshot(tmp_path):
    entry = make_entry(runtime_artifact="grid_sheet")
    touch_declared_files(tmp_path, entry)
    pointer = write_entry(tmp_path, entry)
    write_assets_md(tmp_path, [(TAG, ASSET_ID, pointer, "generated", "")])

    with pytest.raises(AssetRuntimeResolverError, match="Legacy runtime_artifact schema"):
        resolve_manifest_entry(pointer, project_root=tmp_path, assets_md=tmp_path / "ASSETS.md")


def test_rejects_unregistered_or_missing_runtime_files(tmp_path):
    entry = make_entry()
    touch_declared_files(tmp_path, entry)
    pointer = write_entry(tmp_path, entry)
    write_index(tmp_path, [])
    write_assets_md(tmp_path, [(TAG, ASSET_ID, pointer, "generated", "")])
    with pytest.raises(AssetRuntimeResolverError, match="not registered"):
        resolve_manifest_entry(pointer, project_root=tmp_path, assets_md=tmp_path / "ASSETS.md")

    entry, pointer = register(tmp_path, make_entry(), assets=True)
    (tmp_path / entry["source_layout"]["path"].removeprefix("res://")).unlink()
    with pytest.raises(AssetRuntimeResolverError, match="source_layout.path not found"):
        resolve_manifest_entry(pointer, project_root=tmp_path, assets_md=tmp_path / "ASSETS.md")


@pytest.mark.parametrize(
    ("pointer", "message"),
    [
        ("../entry.json", "must not contain"),
        (".godotmaker/asset-generation/entries/v0.1.0/../player_idle.json", "must not contain"),
        (".godotmaker\\asset-generation\\entries\\v0.1.0\\player_idle.json", "forward slashes"),
        ("C:/outside/entry.json", "canonical entries"),
        ("some/other.json", "canonical entries"),
    ],
)
def test_rejects_noncanonical_or_out_of_bounds_manifest_entry_paths(tmp_path, pointer, message):
    with pytest.raises(AssetRuntimeResolverError, match=message):
        resolve_manifest_entry(pointer, project_root=tmp_path, assets_md=tmp_path / "ASSETS.md")


def test_rejects_tag_and_asset_identity_mismatches(tmp_path):
    _, pointer = register(tmp_path, make_entry(), assets=True)

    with pytest.raises(AssetRuntimeResolverError, match="does not match ASSETS.md tag"):
        resolve_manifest_entry(
            pointer,
            project_root=tmp_path,
            assets_md=tmp_path / "ASSETS.md",
            expected_tag="v9.9.9",
        )
    with pytest.raises(AssetRuntimeResolverError, match="does not match ASSETS.md asset_id"):
        resolve_manifest_entry(
            pointer,
            project_root=tmp_path,
            assets_md=tmp_path / "ASSETS.md",
            expected_asset_id="other",
        )


def test_assets_row_rejects_missing_unready_duplicate_and_ambiguous_pointers(tmp_path):
    _, pointer = register(tmp_path, make_entry())
    assets_md = write_assets_md(tmp_path, [(TAG, ASSET_ID, pointer, "MISSING", "")])
    with pytest.raises(AssetRuntimeResolverError, match="expected 'generated'"):
        resolve_assets_row(assets_md, tag=TAG, asset_id=ASSET_ID, project_root=tmp_path)

    assets_md = write_assets_md(tmp_path, [(TAG, ASSET_ID, pointer, "generated", "prompt=x")])
    with pytest.raises(AssetRuntimeResolverError, match="missing manifest_entry"):
        resolve_assets_row(assets_md, tag=TAG, asset_id=ASSET_ID, project_root=tmp_path)

    assets_md = write_assets_md(
        tmp_path,
        [(TAG, ASSET_ID, pointer, "generated", "manifest_entry=; prompt=x")],
    )
    with pytest.raises(AssetRuntimeResolverError, match="must not be empty"):
        resolve_assets_row(assets_md, tag=TAG, asset_id=ASSET_ID, project_root=tmp_path)

    assets_md = write_assets_md(
        tmp_path,
        [(TAG, ASSET_ID, pointer, "generated", f"manifest_entry={pointer}; manifest_entry={pointer}")],
    )
    with pytest.raises(AssetRuntimeResolverError, match="exactly one manifest_entry"):
        resolve_assets_row(assets_md, tag=TAG, asset_id=ASSET_ID, project_root=tmp_path)

    assets_md = write_assets_md(
        tmp_path,
        [(TAG, ASSET_ID, pointer, "generated", ""), (TAG, ASSET_ID, pointer, "generated", "")],
    )
    with pytest.raises(AssetRuntimeResolverError, match="multiple rows"):
        resolve_assets_row(assets_md, tag=TAG, asset_id=ASSET_ID, project_root=tmp_path)


def test_direct_mode_requires_the_matching_generated_assets_row(tmp_path):
    _, pointer = register(tmp_path, make_entry(), assets=True)
    assets_md = tmp_path / "ASSETS.md"
    assets_md.write_text(assets_md.read_text(encoding="utf-8").replace("generated", "MISSING"), encoding="utf-8")
    with pytest.raises(AssetRuntimeResolverError, match="expected 'generated'"):
        resolve_manifest_entry(pointer, project_root=tmp_path, assets_md=assets_md)

    assets_md.unlink()
    with pytest.raises(AssetRuntimeResolverError, match="Cannot read ASSETS.md"):
        resolve_manifest_entry(pointer, project_root=tmp_path, assets_md=assets_md)


def test_rejects_assets_file_from_another_project_root(tmp_path, tmp_path_factory):
    _, pointer = register(tmp_path, make_entry())
    other_root = tmp_path_factory.mktemp("other-project")
    other_assets = write_assets_md(other_root, [(TAG, ASSET_ID, pointer, "generated", "")])

    with pytest.raises(AssetRuntimeResolverError, match="project root"):
        resolve_manifest_entry(pointer, project_root=tmp_path, assets_md=other_assets)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--manifest-entry", ""], "manifest_entry must be a non-empty path"),
        (["--tag", TAG, "--asset-id", ASSET_ID], "Cannot read ASSETS.md"),
    ],
)
def test_cli_failures_use_machine_readable_json(tmp_path, args, message):
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_runtime_resolver.py"),
            "--project-root",
            str(tmp_path),
            *args,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert message in payload["error"]
