import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_process import ActionProcessError, process_action_sheet  # noqa: E402


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
    )

    assert result["ok"] is True
    assert result["frame_count"] == 4
    assert result["align"] == "feet"
    assert result["shared_scale"] is True
    assert result["scale_reference"] == {"checked": False}
    assert Path(result["sheet_path"]).exists()
    assert Path(result["gif_path"]).exists()
    assert Path(result["report"]).exists()
    assert Path(result["curation_report_path"]).exists()
    assert len(result["final_frame_paths"]) == 4
    assert Path(result["final_sheet_path"]).exists()
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


def test_process_action_sheet_recovery_rejects_frame_count_mismatch(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_edge_touch_action_sheet(source, missing_last=True)

    with pytest.raises(ActionProcessError, match="Autoslice recovery found 3 frames; expected 4"):
        process_action_sheet(
            source,
            tmp_path / "processed",
            grid="2x2",
            names="idle_01,idle_02,idle_03,idle_04",
            asset_id="player_idle",
            recover_edge_touch=True,
            recovery_timestamp="20260609-120000",
        )
    assert not (source.parent / "history" / "player_idle_source.20260609-120000.png").exists()


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
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["ok"] is True
    assert data["frame_count"] == 4
    assert Path(data["gif_path"]).exists()
    assert [Path(path).name for path in data["final_frame_paths"]] == [
        "player_idle_idle_01.png",
        "player_idle_idle_02.png",
        "player_idle_idle_03.png",
        "player_idle_idle_04.png",
    ]
