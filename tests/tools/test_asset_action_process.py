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
    _save_gif,
    _write_recovered_action_source,
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


def make_irregular_recovery_sheet(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (120, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 18, 28, 48), fill=(220, 40, 40, 255))
    draw.rectangle((72, 3, 90, 48), fill=(40, 220, 40, 255))
    draw.rectangle((90, 24, 116, 27), fill=(40, 220, 40, 255))
    draw.rectangle((6, 52, 24, 96), fill=(40, 40, 220, 255))
    draw.rectangle((76, 61, 96, 90), fill=(220, 180, 40, 255))
    image.save(path)


def gif_frame_durations(path: Path) -> list[int]:
    durations = []
    with Image.open(path) as image:
        for index in range(image.n_frames):
            image.seek(index)
            durations.append(image.info["duration"])
    return durations


def gif_loop(path: Path) -> int | None:
    with Image.open(path) as image:
        return image.info.get("loop")


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


def test_action_processing_uses_the_shared_magenta_cleanup_contract(tmp_path):
    source = tmp_path / "provider-action.png"
    image = Image.new("RGBA", (16, 16), (245, 2, 243, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 3, 11, 12), fill=(130, 20, 185, 255))
    draw.line((4, 2, 11, 2), fill=(205, 45, 60, 96), width=1)
    image.save(source)

    result = process_action_sheet(
        source,
        tmp_path / "processed",
        grid="1x1",
        names="prop",
        asset_id="prop",
        action_name="idle",
        fps=8,
        loop=False,
        frame_durations=[1],
    )

    with Image.open(tmp_path / "processed" / "candidates" / "prop.png") as candidate:
        rgba = candidate.convert("RGBA")
        assert sum(pixel == (130, 20, 185, 255) for pixel in rgba.get_flattened_data()) > 0
        assert not any(
            pixel[:3] == (255, 0, 255) and pixel[3] > 0
            for pixel in rgba.get_flattened_data()
        )
    assert result["frame_count"] == 1


def test_action_recovery_preserves_purple_and_semtransparent_edges(tmp_path):
    source = tmp_path / "purple-edge-source.png"
    image = Image.new("RGBA", (20, 20), (245, 2, 243, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 4, 9, 15), fill=(130, 20, 185, 255))
    draw.line((0, 3, 9, 3), fill=(205, 45, 60, 96), width=1)
    image.save(source)

    result = process_action_sheet(
        source,
        tmp_path / "processed",
        grid="1x1",
        names="prop",
        asset_id="prop",
        recover_edge_touch=True,
        recovery_timestamp="20260802-000000",
        action_name="idle",
        fps=8,
        loop=False,
        frame_durations=[1],
    )

    assert result["source_recovery"] is not None
    with Image.open(tmp_path / "processed" / "candidates" / "prop.png") as candidate:
        rgba = candidate.convert("RGBA")
        assert sum(pixel == (130, 20, 185, 255) for pixel in rgba.get_flattened_data()) > 0


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
    assert recovery["ordering_method"] == "grid_foreground_overlap"
    assert recovery["original_size"] == [80, 80]
    assert recovery["recovered_size"] == [92, 92]
    assert len(recovery["placements"]) == 4
    assert result["edge_touch_frames"] == []
    assert Path(result["initial_curation_report_path"]).exists()
    assert Path(result["curation_report_path"]).exists()
    assert Path(result["final_sheet_path"]).exists()


def test_recovery_reassigns_irregular_components_to_source_grid_order(tmp_path):
    source = tmp_path / "irregular-source.png"
    make_irregular_recovery_sheet(source)

    recovery = _write_recovered_action_source(
        source,
        output_dir=tmp_path / "processed",
        grid="2x2",
        frame_names=["top_left", "top_right", "bottom_left", "bottom_right"],
        background="transparent",
        align="feet",
        timestamp="20260730-120000",
    )

    assert [placement["name"] for placement in recovery["placements"]] == [
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
    ]
    assert [placement["source_cell"] for placement in recovery["placements"]] == [
        [0, 0],
        [1, 0],
        [0, 1],
        [1, 1],
    ]
    assert all(
        placement["source_cell"] == placement["target_cell"]
        for placement in recovery["placements"]
    )
    assert recovery["placements"][1]["source_bbox"] == [72, 3, 117, 49]
    assert recovery["placements"][1]["source_cell_overlap_pixels"] > 0
    assert recovery["placements"][1]["cell_scores"][0]["foreground_pixels"] == 0


def test_recovery_uses_foreground_ownership_for_a_weapon_crossing_a_cell_edge(tmp_path):
    source = tmp_path / "wide-weapon-source.png"
    image = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 12, 25, 50), fill=(220, 40, 40, 255))
    draw.rectangle((25, 25, 68, 28), fill=(220, 40, 40, 255))
    draw.rectangle((88, 4, 108, 50), fill=(40, 220, 40, 255))
    image.save(source)

    recovery = _write_recovered_action_source(
        source,
        output_dir=tmp_path / "processed",
        grid="2x1",
        frame_names=["wide_attack", "follow_up"],
        background="transparent",
        align="feet",
        timestamp="20260730-120000",
    )

    assert [placement["source_cell"] for placement in recovery["placements"]] == [
        [0, 0],
        [1, 0],
    ]
    wide_attack = recovery["placements"][0]
    assert wide_attack["source_bbox"][2] > 60
    assert wide_attack["cell_scores"][0]["score"] > wide_attack["cell_scores"][1]["score"]


def test_recovery_preserves_rows_when_component_bounding_boxes_overlap_vertically(tmp_path):
    source = tmp_path / "overlapping-rows-source.png"
    image = Image.new("RGBA", (120, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 8, 20, 58), fill=(220, 40, 40, 255))
    draw.rectangle((70, 1, 86, 48), fill=(40, 220, 40, 255))
    draw.rectangle((35, 45, 50, 96), fill=(40, 40, 220, 255))
    draw.rectangle((96, 40, 112, 94), fill=(220, 180, 40, 255))
    image.save(source)

    recovery = _write_recovered_action_source(
        source,
        output_dir=tmp_path / "processed",
        grid="2x2",
        frame_names=["top_left", "top_right", "bottom_left", "bottom_right"],
        background="transparent",
        align="feet",
        timestamp="20260730-120000",
    )

    assert [placement["source_cell"] for placement in recovery["placements"]] == [
        [0, 0],
        [1, 0],
        [0, 1],
        [1, 1],
    ]
    assert recovery["placements"][0]["source_bbox"][3] > 50
    assert recovery["placements"][2]["source_bbox"][1] < 50


def test_recovery_requests_regeneration_when_components_cannot_fill_the_grid(tmp_path):
    source = tmp_path / "ambiguous-source.png"
    image = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 8, 14, 30), fill=(220, 40, 40, 255))
    draw.rectangle((22, 8, 32, 30), fill=(40, 220, 40, 255))
    image.save(source)

    with pytest.raises(
        ActionRegenerationRequired,
        match="could not assign every frame to one source grid cell",
    ) as caught:
        _write_recovered_action_source(
            source,
            output_dir=tmp_path / "processed",
            grid="2x1",
            frame_names=["left", "right"],
            background="transparent",
            align="feet",
            timestamp="20260730-120000",
        )

    assert caught.value.result["reason"] == "recovery_cell_assignment_failed"
    assert caught.value.result["retryable"] is True


def test_recovery_requests_regeneration_for_a_low_positive_ownership_assignment(tmp_path):
    source = tmp_path / "low-ownership-source.png"
    image = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 2, 14, 8), fill=(220, 40, 40, 255))
    draw.rectangle((14, 4, 42, 5), fill=(220, 40, 40, 255))
    draw.rectangle((22, 12, 38, 34), fill=(40, 220, 40, 255))
    draw.rectangle((38, 20, 43, 22), fill=(40, 220, 40, 255))
    image.save(source)

    with pytest.raises(ActionRegenerationRequired) as caught:
        _write_recovered_action_source(
            source,
            output_dir=tmp_path / "processed",
            grid="2x1",
            frame_names=["left", "right"],
            background="transparent",
            align="feet",
            timestamp="20260730-120000",
        )

    diagnostic = caught.value.result
    assert diagnostic["reason"] == "recovery_cell_assignment_failed"
    assert 0 < diagnostic["ownership_ratio"] < 0.5


def test_process_action_sheet_gif_uses_runtime_frame_durations(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source)

    result = process_action_sheet(
        source,
        tmp_path / "processed",
        grid="2x2",
        names="idle_01,idle_02,idle_03,idle_04",
        asset_id="player_idle",
        action_name="idle",
        fps=10,
        loop=False,
        frame_durations=[1, 1.5, 2, 0.5],
    )

    assert gif_frame_durations(Path(result["gif_path"])) == [100, 150, 200, 50]
    assert gif_loop(Path(result["gif_path"])) is None


def test_process_action_sheet_looping_gif_repeats_forever(tmp_path):
    source = tmp_path / "player_idle_source.png"
    make_action_sheet(source)

    result = process_action_sheet(
        source,
        tmp_path / "processed",
        grid="2x2",
        names="idle_01,idle_02,idle_03,idle_04",
        asset_id="player_idle",
        action_name="idle",
        fps=10,
        loop=True,
        frame_durations=[1, 1, 1, 1],
    )

    assert gif_loop(Path(result["gif_path"])) == 0


def test_gif_combines_identical_frames_without_changing_total_playback_time(tmp_path):
    frames = [Image.new("RGBA", (16, 16), (220, 40, 40, 255)) for _ in range(3)]
    try:
        gif_path = tmp_path / "identical.gif"
        requested = _save_gif(
            frames,
            gif_path,
            fps=10,
            loop=False,
            frame_durations=[1, 1.5, 2],
        )

        assert requested == [100, 150, 200]
        assert gif_frame_durations(gif_path) == [450]
    finally:
        for frame in frames:
            frame.close()


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
