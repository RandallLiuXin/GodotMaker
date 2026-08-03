"""Asset tools must run in the layout `/gm-asset` actually runs in.

`publish.py` puts `tools/` at the project root, flattens every family skill into
the adapter's skill root, and deploys the shared runtime once to
`.godotmaker/asset-runtime/`. A published game project therefore has no
`skills/assets/` directory at all.

A tool that resolves an import as `<parent>/skills/assets/...` works perfectly
from a framework checkout — which is where the test suite runs — and dies with
`ModuleNotFoundError` in the project. Every check here builds the real published
layout from `publish.py`'s own functions, so it cannot drift from what publish
actually deploys, and then executes the tools as documented.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import publish  # noqa: E402

TAG = "v0.1.0"

# Every asset tool the manager invokes by path. If one of these cannot even
# reach argparse in a published project, the pipeline step that documents it is
# dead on arrival.
ASSET_TOOLS = (
    "asset_action_entry_draft",
    "asset_assets_md_update",
    "asset_bundle_rows",
    "asset_compact_prop_pack_entry_draft",
    "asset_curation_entry_draft",
    "asset_generation_index",
    "asset_runtime_resolver",
    "asset_scene_prop_set_entry_draft",
    "asset_stable_entry",
    "asset_tileset_entry_draft",
    "asset_tileset_profile",
    "asset_ui_card_entry_draft",
)


@pytest.fixture(scope="module")
def published(tmp_path_factory) -> Path:
    """Deploy the real published layout with publish.py's own routines."""
    target = tmp_path_factory.mktemp("published-project")
    publish.publish_directory(ROOT / "tools", target / "tools", "tools/")
    publish.publish_skills(ROOT, target / ".claude" / "skills", agent="claude-code")
    publish.publish_asset_runtime(ROOT, target)
    (target / "project.godot").write_text("[application]\n", encoding="utf-8")
    return target


def _run(published: Path, tool: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(published / "tools" / f"{tool}.py"), *args],
        cwd=published,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_published_layout_really_has_no_skills_assets_tree(published: Path):
    # The premise of every check below. If publish ever starts shipping
    # skills/assets/, these tests stop proving anything and should be revisited.
    assert not (published / "skills").exists()
    assert (published / "tools").is_dir()
    assert (published / ".godotmaker" / "asset-runtime").is_dir()
    assert (published / ".claude" / "skills" / "tileset").is_dir()


@pytest.mark.parametrize("tool", ASSET_TOOLS)
def test_every_asset_tool_imports_in_a_published_project(published: Path, tool: str):
    completed = _run(published, tool, "--help")
    assert completed.returncode == 0, (
        f"{tool} cannot start in a published project:\n{completed.stderr}"
    )


def test_tileset_registration_runs_end_to_end_in_a_published_project(published: Path):
    """The documented tileset registration chain, executed where it must run."""
    asset_id = "grassland"
    stable = published / "assets" / "generated" / "tileset" / asset_id
    stable.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (16, 16), (1, 2, 3, 255)).save(stable / f"{asset_id}_atlas.png")
    (stable / f"{asset_id}.tres").write_text('[gd_resource type="TileSet"]', encoding="utf-8")

    root = f"res://assets/generated/tileset/{asset_id}"
    (published / "request.json").write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    (published / "result.json").write_text(
        json.dumps(
            {
                "asset_type": "tileset",
                "outputs": [
                    {
                        "role": "runtime",
                        "path": f"{root}/{asset_id}.tres",
                        "godot_type": "TileSet",
                    }
                ],
                "sources": [
                    {"path": f"{root}/{asset_id}_atlas.png", "layout": "tile_atlas"}
                ],
                "previews": [],
                "validation": {
                    "passed": True,
                    "levels": {
                        level: True for level in ("L0", "L1", "L2", "L3", "L4")
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (published / "ASSETS.md").write_text(
        "# Assets\n\n## Asset Table\n\n"
        "| # | Tag | Name | Type | Size | Generation Params | File Path | Status |\n"
        "|---|-----|------|------|------|-------------------|-----------|--------|\n"
        f"| 1 | {TAG} | {asset_id} | tileset | - | - | - | MISSING |\n",
        encoding="utf-8",
    )

    draft = "work/grassland.json"
    completed = _run(
        published,
        "asset_tileset_entry_draft",
        "--request", "request.json",
        "--result", "result.json",
        "--tag", TAG,
        "--project-root", ".",
        "--out", draft,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    entry = f".godotmaker/asset-generation/entries/{TAG}/{asset_id}.json"
    for tool, args in (
        ("asset_stable_entry", (draft, "--project-root", ".", "--write", "--check-files")),
        ("asset_generation_index", ("--project-root", ".", "--entry-file", entry)),
        ("asset_assets_md_update", ("--entry-file", entry)),
    ):
        step = _run(published, tool, *args)
        assert step.returncode == 0, f"{tool}: {step.stdout}{step.stderr}"

    snapshot = _run(
        published,
        "asset_runtime_resolver",
        "--project-root", ".",
        "--assets-md", "ASSETS.md",
        "--tag", TAG,
        "--asset-id", asset_id,
    )
    assert snapshot.returncode == 0, snapshot.stdout + snapshot.stderr
    assert json.loads(snapshot.stdout)["godot_artifact"] == {
        "type": "TileSet",
        "path": f"{root}/{asset_id}.tres",
    }
