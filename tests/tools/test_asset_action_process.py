import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_process import (  # noqa: E402
    ActionProcessError,
    ActionRegenerationRequired,
    process_action_sheet,
)


def animation_args():
    return {
        "action_name": "idle",
        "fps": 8,
        "loop": False,
        "frame_durations": [1, 1, 1, 1],
    }


def make_action_sheet(path: Path, *, missing_last: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (80, 80), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    boxes = [
        (10, 8, 30, 36),
        (52, 10, 68, 34),
        (8, 48, 32, 72),
        (50, 50, 70, 74),
    ]
    for index, box in enumerate(boxes):
        if missing_last and index == 3:
            continue
        draw.rectangle(box, fill=(40 + index * 20, 80, 220, 255))
        draw.rectangle(box, outline=(20, 20, 30, 255), width=2)
    image.save(path)


def make_edge_touch_action_sheet(path: Path, *, missing_last: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (80, 80), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    boxes = [
        ((0, 8, 30, 32) if missing_last else (8, 8, 30, 32)),
        (50, 8, 72, 32),
        (8, 50, 30, 72),
        (50, 50, 79, 79),
    ]
    for index, box in enumerate(boxes):
        if missing_last and index == 3:
            continue
        draw.rectangle(box, fill=(40 + index * 20, 80, 220, 255))
    image.save(path)


def test_process_action_sheet_outputs_runtime_bundle(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source)

    result = process_action_sheet(
        source,
        tmp_path / "processed",
        grid="2x2",
        names="idle_01,idle_02,idle_03,idle_04",
        asset_id="player_idle",
        tag="v0.1.0",
        final_dir=tmp_path / "assets" / "sprites",
        final_prefix="player_idle",
        **animation_args(),
    )

    assert result["ok"] is True
    assert result["frame_count"] == 4
    assert result["cell_size"] == 256
    assert result["align"] == "feet"
    assert result["shared_scale"] is True
    assert result["scale_reference"] == {"checked": False}
    assert Path(result["sheet_path"]).exists()
    assert Path(result["gif_path"]).exists()
    assert Path(result["report"]).exists()
    assert Path(result["curation_report_path"]).exists()
    assert len(result["final_frame_paths"]) == 4
    assert Path(result["final_sheet_path"]).exists()
    assert Path(result["final_gif_path"]).exists()
    assert Path(result["final_gif_path"]).name == "player_idle.gif"
    assert Path(result["final_sheet_path"]).name == "player_idle_sheet.png"
    assert [Path(path).name for path in result["final_frame_paths"]] == [
        "player_idle_idle_01.png",
        "player_idle_idle_02.png",
        "player_idle_idle_03.png",
        "player_idle_idle_04.png",
    ]
    sizes = {tuple(frame["output_size"]) for frame in result["frames"]}
    assert len(sizes) > 1
    bottom_edges = {
        frame["paste_position"][1] + frame["output_size"][1]
        for frame in result["frames"]
    }
    assert len(bottom_edges) == 1
    assert {Image.open(Path(path)).size for path in result["final_frame_paths"]} == {(256, 256)}
    meta = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    assert meta["frame_labels"] == ["idle_01", "idle_02", "idle_03", "idle_04"]
    assert meta["final_sheet_path"] == result["final_sheet_path"]


def test_process_action_sheet_rejects_missing_required_frame(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source, missing_last=True)

    with pytest.raises(ActionProcessError, match="Missing required frames"):
        process_action_sheet(
            source,
            tmp_path / "processed",
            grid="2x2",
            names="idle_01,idle_02,idle_03,idle_04",
            asset_id="player_idle",
            **animation_args(),
        )


def test_process_action_sheet_rejects_edge_touch_by_default(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_edge_touch_action_sheet(source)

    with pytest.raises(ActionProcessError, match="Missing required frames"):
        process_action_sheet(
            source,
            tmp_path / "processed",
            grid="2x2",
            names="idle_01,idle_02,idle_03,idle_04",
            asset_id="player_idle",
            **animation_args(),
        )


def test_process_action_sheet_recovers_edge_touch_with_history(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_edge_touch_action_sheet(source)
    original_bytes = source.read_bytes()

    result = process_action_sheet(
        source,
        tmp_path / "processed",
        grid="2x2",
        names="idle_01,idle_02,idle_03,idle_04",
        asset_id="player_idle",
        recover_edge_touch=True,
        recovery_timestamp="20260609-120000",
        final_dir=tmp_path / "assets" / "sprites",
        final_prefix="player_idle",
        **animation_args(),
    )

    recovery = result["source_recovery"]
    assert isinstance(recovery, dict)
    history_path = Path(str(recovery["archived_source_path"]))
    assert history_path.exists()
    assert history_path.name == "player_idle_source.20260609-120000.png"
    assert history_path.read_bytes() == original_bytes
    assert Path(str(recovery["active_source_path"])) == source
    assert source.read_bytes() != original_bytes
    assert recovery["method"] == "autoslice_repack"
    assert recovery["original_size"] == [80, 80]
    assert recovery["recovered_size"] == [92, 92]
    assert len(recovery["placements"]) == 4
    assert result["edge_touch_frames"] == []
    assert Path(result["initial_curation_report_path"]).exists()
    assert Path(result["curation_report_path"]).exists()
    assert Path(result["final_sheet_path"]).exists()


def test_process_action_sheet_recovery_requests_source_regeneration(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_edge_touch_action_sheet(source, missing_last=True)
    report = tmp_path / "reports" / "idle-process.json"

    with pytest.raises(
        ActionRegenerationRequired,
        match="Autoslice recovery found 3 frames; expected 4",
    ) as caught:
        process_action_sheet(
            source,
            tmp_path / "processed",
            grid="2x2",
            names="idle_01,idle_02,idle_03,idle_04",
            asset_id="player_idle",
            recover_edge_touch=True,
            recovery_timestamp="20260609-120000",
            report=report,
            **animation_args(),
        )
    diagnostic = caught.value.result
    assert diagnostic["status"] == "needs_regeneration"
    assert diagnostic["retryable"] is True
    assert diagnostic["found_frame_count"] == 3
    assert diagnostic["expected_frame_count"] == 4
    assert diagnostic["recommended_action"] == "regenerate_source"
    assert json.loads(report.read_text(encoding="utf-8")) == diagnostic
    assert not (source.parent / "history" / "player_idle_source.20260609-120000.png").exists()


def test_cli_reports_source_regeneration_as_an_intermediate_result(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_edge_touch_action_sheet(source, missing_last=True)
    report = tmp_path / "reports" / "idle-process.json"

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_action_process.py"),
            "--source", str(source),
            "--out-dir", str(tmp_path / "processed"),
            "--grid", "2x2",
            "--names", "idle_01,idle_02,idle_03,idle_04",
            "--kind", "body",
            "--recover-edge-touch",
            "--action-name", "idle",
            "--fps", "8",
            "--loop",
            "--frame-durations", "1,1,1,1",
            "--report", str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    diagnostic = json.loads(result.stdout)
    assert diagnostic["ok"] is False
    assert diagnostic["status"] == "needs_regeneration"
    assert diagnostic["retryable"] is True
    assert diagnostic["report"] == str(report)
    assert json.loads(report.read_text(encoding="utf-8")) == diagnostic


def test_process_action_sheet_rejects_body_scale_drift(tmp_path):
    source = tmp_path / "player_idle_source.png"
    reference_meta = tmp_path / "reference-meta.json"
    make_action_sheet(source)
    reference_meta.write_text(
        json.dumps(
            {
                "frames": [
                    {"output_size": [40, 40]},
                    {"output_size": [40, 40]},
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ActionProcessError, match="Body scale drift exceeds tolerance"):
        process_action_sheet(
            source,
            tmp_path / "processed",
            grid="2x2",
            names="idle_01,idle_02,idle_03,idle_04",
            asset_id="player_idle",
            scale_reference_metadata=reference_meta,
            **animation_args(),
        )


def test_process_action_sheet_matches_reference_scale_without_replacing_source_art(tmp_path):
    source = tmp_path / "player_idle_source.png"
    reference_meta = tmp_path / "reference-meta.json"
    make_action_sheet(source)
    reference_meta.write_text(
        json.dumps(
            {
                "frames": [
                    {"output_size": [80, 80]},
                    {"output_size": [80, 80]},
                ]
            }
        ),
        encoding="utf-8",
    )

    result = process_action_sheet(
        source,
        tmp_path / "processed",
        grid="2x2",
        names="idle_01,idle_02,idle_03,idle_04",
        asset_id="player_idle",
        fit_scale=0.5,
        scale_reference_metadata=reference_meta,
        match_scale_reference=True,
        **animation_args(),
    )

    normalization = result["scale_normalization"]
    assert isinstance(normalization, dict)
    assert normalization["mode"] == "reference_median_height"
    assert normalization["initial_fit_scale"] == 0.5
    assert result["scale_reference"]["ratio"] == pytest.approx(1.0)
    assert all(frame["candidate_path"] for frame in result["frames"])


def test_process_action_sheet_requires_reference_for_scale_matching(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source)

    with pytest.raises(ActionProcessError, match="requires --scale-reference-metadata"):
        process_action_sheet(
            source,
            tmp_path / "processed",
            grid="2x2",
            names="idle_01,idle_02,idle_03,idle_04",
            asset_id="player_idle",
            match_scale_reference=True,
            **animation_args(),
        )


def test_process_action_sheet_requires_final_prefix_with_final_dir(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source)

    with pytest.raises(ActionProcessError, match="--final-prefix is required"):
        process_action_sheet(
            source,
            tmp_path / "processed",
            grid="2x2",
            names="idle_01,idle_02,idle_03,idle_04",
            asset_id="player_idle",
            final_dir=tmp_path / "assets" / "sprites",
            **animation_args(),
        )


def test_process_action_sheet_does_not_double_prefix_runtime_frames(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source)

    result = process_action_sheet(
        source,
        tmp_path / "processed",
        grid="2x2",
        names="player_idle_01,player_idle_02,player_idle_03,player_idle_04",
        asset_id="player_idle",
        final_dir=tmp_path / "assets" / "sprites",
        final_prefix="player_idle",
        **animation_args(),
    )

    assert [Path(path).name for path in result["final_frame_paths"]] == [
        "player_idle_01.png",
        "player_idle_02.png",
        "player_idle_03.png",
        "player_idle_04.png",
    ]


def test_cli_outputs_json(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source)

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_action_process.py"),
            "--source",
            str(source),
            "--out-dir",
            str(tmp_path / "processed"),
            "--grid",
            "2x2",
            "--names",
            "idle_01,idle_02,idle_03,idle_04",
            "--kind",
            "body",
            "--asset-id",
            "player_idle",
            "--tag",
            "v0.1.0",
            "--final-dir",
            str(tmp_path / "assets" / "sprites"),
            "--final-prefix",
            "player_idle",
            "--action-name",
            "idle",
            "--fps",
            "8",
            "--no-loop",
            "--frame-durations",
            "1,1,1,1",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["frame_count"] == 4
    assert data["cell_size"] == 256
    assert Path(data["gif_path"]).exists()
    assert [Path(path).name for path in data["final_frame_paths"]] == [
        "player_idle_idle_01.png",
        "player_idle_idle_02.png",
        "player_idle_idle_03.png",
        "player_idle_idle_04.png",
    ]


@pytest.mark.parametrize(
    "flag, value, message",
    [
        ("--fps", "nan", "--fps must be a positive number"),
        ("--frame-durations", "1,inf,1,1", "--frame-durations values must be positive numbers"),
    ],
)
def test_cli_rejects_nonfinite_animation_timing(tmp_path, flag, value, message):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source)
    arguments = [
        sys.executable,
        str(TOOLS_DIR / "asset_action_process.py"),
        "--source", str(source),
        "--out-dir", str(tmp_path / "processed"),
        "--grid", "2x2",
        "--names", "idle_01,idle_02,idle_03,idle_04",
        "--kind", "body",
        "--action-name", "idle",
        "--fps", "8",
        "--no-loop",
        "--frame-durations", "1,1,1,1",
    ]
    arguments[arguments.index(flag) + 1] = value
    result = subprocess.run(arguments, capture_output=True, text=True, check=False)

    assert result.returncode == 1
    assert json.loads(result.stdout)["error"] == message


def test_process_action_sheet_rejects_a_non_power_of_two_runtime_canvas(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source)

    with pytest.raises(ActionProcessError, match="positive power of two"):
        process_action_sheet(
            source,
            tmp_path / "processed",
            grid="2x2",
            names="idle_01,idle_02,idle_03,idle_04",
            cell_size=192,
            **animation_args(),
        )
