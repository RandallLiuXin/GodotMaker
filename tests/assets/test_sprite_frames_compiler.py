import sys
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_DIR = REPO_ROOT / "skills" / "assets" / "_shared"
sys.path.insert(0, str(SHARED_DIR))
sys.path.insert(0, str(REPO_ROOT / "tools"))

from asset_compiler import (  # noqa: E402
    CompileRequest,
    CompilerError,
    CompilerRegistry,
    build_default_registry,
    sprite_frames,
)
from asset_validation import (  # noqa: E402
    GodotProbe,
    ProbeRequest,
    ProbeResult,
    StructureRequest,
    build_default_structures,
)
from asset_action_process import ActionRegenerationRequired, process_action_sheet  # noqa: E402


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (2, 2), (255, 255, 255, 255)).save(path)


def _incomplete_edge_sheet(path: Path) -> None:
    image = Image.new("RGBA", (80, 80), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    for box, color in [
        ((0, 8, 30, 32), (220, 40, 40, 255)),
        ((50, 8, 72, 32), (40, 220, 40, 255)),
        ((8, 50, 30, 72), (40, 40, 220, 255)),
    ]:
        draw.rectangle(box, fill=color)
    image.save(path)


def _request(project: Path, actions: list[dict]) -> CompileRequest:
    root = project / "assets/generated/character-bundle/hero"
    _png(root / "hero_sheet.png")
    return CompileRequest(
        production_family="character-bundle",
        asset_id="hero",
        source_layout_type="grid_sheet",
        source_path="res://assets/generated/character-bundle/hero/hero_sheet.png",
        artifact_type="SpriteFrames",
        artifact_path="res://assets/generated/character-bundle/hero/hero.tres",
        project_root=project,
        spec={"required_actions": [action["name"] for action in actions], "actions": actions},
    )


def _action(name: str, *, loop: bool, fps: float, paths: list[str], durations: list[float]) -> dict:
    return {"name": name, "loop": loop, "fps": fps, "frame_paths": paths,
            "frame_durations": durations}


def test_compiles_multiple_explicit_actions_with_order_timing_and_loop(tmp_path):
    project = tmp_path
    root = project / "assets/generated/character-bundle/hero"
    idle = ["res://assets/generated/character-bundle/hero/idle_1.png",
            "res://assets/generated/character-bundle/hero/idle_2.png"]
    run = ["res://assets/generated/character-bundle/hero/run_1.png"]
    for path in idle + run:
        _png(project / path.removeprefix("res://"))
    actions = [_action("idle", loop=False, fps=8, paths=idle, durations=[1, 0.5]),
               _action("run", loop=True, fps=12, paths=run, durations=[2])]
    registry = build_default_registry()

    result = registry.compile(_request(project, actions))

    artifact = root / "hero.tres"
    text = artifact.read_text(encoding="utf-8")
    assert result.godot_artifact.type == "SpriteFrames"
    assert result.receipt.details["actions"] == actions
    assert '"loop": false' in text
    assert '"loop": true' in text
    assert text.index('"name": &"idle"') < text.index('"name": &"run"')
    assert text.index(idle[0]) < text.index(idle[1])


@pytest.mark.parametrize(
    "actions, message",
    [
        ([_action("idle", loop=False, fps=0, paths=[], durations=[])], "fps"),
        ([_action("idle", loop="false", fps=8, paths=[], durations=[])], "loop"),
        ([_action("idle", loop=False, fps=8, paths=[], durations=[])], "frame_paths"),
    ],
)
def test_rejects_illegal_explicit_action_timing_and_frames(tmp_path, actions, message):
    registry = CompilerRegistry()
    sprite_frames.register_into(registry)
    with pytest.raises(CompilerError, match=message):
        registry.compile(_request(tmp_path, actions))


def test_refuses_to_publish_when_a_required_action_is_missing(tmp_path):
    registry = CompilerRegistry()
    sprite_frames.register_into(registry)
    action = _action("idle", loop=False, fps=8, paths=["res://assets/generated/character-bundle/hero/idle.png"], durations=[1])
    _png(tmp_path / "assets/generated/character-bundle/hero/idle.png")
    request = _request(tmp_path, [action])
    object.__setattr__(request, "spec", {"required_actions": ["idle", "run"], "actions": [action]})
    with pytest.raises(CompilerError, match="missing required actions"):
        registry.compile(request)


def test_headless_godot_loads_spriteframes_and_reports_its_animation_structure(
    godot_bin, godot_project
):
    paths = ["res://assets/generated/character-bundle/hero/idle_1.png",
             "res://assets/generated/character-bundle/hero/idle_2.png"]
    for path in paths:
        _png(godot_project / path.removeprefix("res://"))
    action = _action("idle", loop=False, fps=12.3, paths=paths, durations=[0.1, 0.9])
    registry = CompilerRegistry()
    sprite_frames.register_into(registry)
    result = registry.compile(_request(godot_project, [action]))

    report = GodotProbe(godot_bin).probe(
        godot_project,
        [ProbeRequest(result.godot_artifact.path, "SpriteFrames", checks=("spriteframes",))],
    )
    structure = report.resources[0].structure["spriteframes"]
    assert report.resources[0].loaded is True
    assert report.resources[0].type_matches is True
    animation = structure["animations"][0]
    assert animation["name"] == "idle"
    assert animation["fps"] == 12.3
    assert animation["frame_paths"] == paths
    assert animation["frame_durations"] == pytest.approx([0.1, 0.9], abs=1e-6)
    assert build_default_structures().validate(StructureRequest(
        production_family="character-bundle", asset_id="hero", source_layout_type="grid_sheet",
        source_path=result.godot_artifact.path, artifact_type="SpriteFrames",
        artifact_path=result.godot_artifact.path, project_root=godot_project,
        probe=report.resources[0], spec={"actions": [action]},
    )) == {"animations": ["idle"]}


def test_fixed_grid_recovery_chain_compiles_and_loads_spriteframes(godot_project, godot_bin):
    source = godot_project / "missing-frame-source.png"
    recovered = godot_project / "recovered.png"
    report = godot_project / "recovery-report.json"
    output = godot_project / "assets/generated/character-bundle/player"
    _incomplete_edge_sheet(source)
    args = {
        "action_name": "idle", "fps": 8, "loop": False,
        "frame_durations": [1, 1, 1, 1],
    }

    with pytest.raises(ActionRegenerationRequired):
        process_action_sheet(
            source, godot_project / "strict", grid="2x2",
            names="idle_01,idle_02,idle_03,idle_04", asset_id="player",
            recover_edge_touch=True, **args,
        )
    recovery = subprocess.run(
        [
            sys.executable, str(REPO_ROOT / "tools/asset_connected_component_recovery.py"),
            "--source", str(source), "--output", str(recovered), "--grid", "2x2",
            "--background", "magenta", "--report", str(report),
        ],
        capture_output=True, text=True, check=False,
    )
    assert recovery.returncode == 2
    fallback = process_action_sheet(
        source, godot_project / "fallback", grid="2x2",
        names="idle_01,idle_02,idle_03,idle_04", asset_id="player",
        fixed_grid_fallback=True, final_dir=output, final_prefix="player",
        final_sheet_name="player_idle_sheet.png", **args,
    )
    frame_paths = [
        "res://" + Path(path).relative_to(godot_project).as_posix()
        for path in fallback["final_frame_paths"]
    ]
    compiled = build_default_registry().compile(
        CompileRequest(
            production_family="character-bundle", asset_id="player",
            source_layout_type="grid_sheet",
            source_path="res://assets/generated/character-bundle/player/player_idle_sheet.png",
            artifact_type="SpriteFrames",
            artifact_path="res://assets/generated/character-bundle/player/player.tres",
            project_root=godot_project,
            spec={"required_actions": ["idle"], "actions": [{
                "name": "idle", "fps": 8, "loop": False,
                "frame_paths": frame_paths, "frame_durations": [1, 1, 1, 1],
            }]},
        )
    )
    probe = GodotProbe(godot_bin).probe(
        godot_project,
        [ProbeRequest(compiled.godot_artifact.path, "SpriteFrames", checks=("spriteframes",))],
    )

    assert fallback["warnings"][0]["human_review_required"] is True
    assert probe.resources[0].loaded is True
    assert probe.resources[0].type_matches is True


def test_l4_validator_checks_the_explicit_timing_and_texture_contract(tmp_path):
    action = _action("idle", loop=False, fps=8,
                     paths=["res://assets/generated/character-bundle/hero/idle.png"],
                     durations=[0.5])
    structures = build_default_structures()
    request = StructureRequest(
        production_family="character-bundle", asset_id="hero", source_layout_type="grid_sheet",
        source_path="res://assets/generated/character-bundle/hero/hero_sheet.png",
        artifact_type="SpriteFrames", artifact_path="res://assets/generated/character-bundle/hero/hero.tres",
        project_root=tmp_path, spec={"actions": [action]},
        probe=ProbeResult(
            res_path="res://assets/generated/character-bundle/hero/hero.tres",
            expected_type="SpriteFrames", loaded=True, godot_class="SpriteFrames", type_matches=True,
            structure={"spriteframes": {"animations": [{
                "name": "idle", "fps": 8.0, "loop": False, "frame_count": 1,
                "frame_paths": action["frame_paths"], "frame_durations": [0.5],
            }]}},
        ),
    )
    assert structures.validate(request) == {"animations": ["idle"]}
