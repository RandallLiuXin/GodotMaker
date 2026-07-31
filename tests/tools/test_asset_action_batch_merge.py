import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_action_batch_merge import (  # noqa: E402
    ActionBatchMergeError,
    merge_action_batches,
)
from asset_action_process import process_action_sheet  # noqa: E402


def _source(path: Path, color: tuple[int, int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (80, 40), (255, 0, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 4, 28, 36), fill=color)
    draw.rectangle((50, 6, 72, 36), fill=color)
    image.save(path)


def _batch(
    source: Path,
    output: Path,
    names: str,
    action: str,
    *,
    scale_reference: Path | None = None,
) -> dict:
    return process_action_sheet(
        source,
        output,
        grid="2x1",
        names=names,
        asset_id="hero",
        action_name=action,
        fps=12,
        loop=False,
        frame_durations=[1, 1],
        scale_reference_metadata=scale_reference,
        match_scale_reference=scale_reference is not None,
    )


def _gif_frame_durations(path: Path) -> list[int]:
    durations = []
    with Image.open(path) as image:
        for index in range(image.n_frames):
            image.seek(index)
            durations.append(image.info["duration"])
    return durations


def _gif_loop(path: Path) -> int | None:
    with Image.open(path) as image:
        return image.info.get("loop")


def test_merge_action_batches_keeps_processed_frame_order_and_runtime_canvas(tmp_path):
    first_source = tmp_path / "raw/attack-a.png"
    second_source = tmp_path / "raw/attack-b.png"
    _source(first_source, (70, 120, 210, 255))
    _source(second_source, (20, 200, 20, 255))
    first = _batch(first_source, tmp_path / "work/batch-a", "attack_01,attack_02", "attack_batch_a")
    second = _batch(
        second_source,
        tmp_path / "work/batch-b",
        "attack_03,attack_04",
        "attack_batch_b",
        scale_reference=Path(first["report"]),
    )

    merged = merge_action_batches(
        [Path(first["report"]), Path(second["report"])],
        tmp_path / "work/merged",
        action_name="attack",
        grid="2x2",
        names="attack_01,attack_02,attack_03,attack_04",
        fps=12,
        loop=False,
        frame_durations=[1, 1, 1, 1],
        final_dir=tmp_path / "assets/generated/character-bundle/hero",
        final_prefix="hero_attack",
    )

    assert merged["cell_size"] == 256
    assert merged["frame_labels"] == ["attack_01", "attack_02", "attack_03", "attack_04"]
    assert [Path(path).name for path in merged["final_frame_paths"]] == [
        "hero_attack_attack_01.png",
        "hero_attack_attack_02.png",
        "hero_attack_attack_03.png",
        "hero_attack_attack_04.png",
    ]
    assert Image.open(Path(merged["final_sheet_path"])).size == (512, 512)
    persisted = json.loads(Path(merged["report"]).read_text(encoding="utf-8"))
    assert [batch["frame_labels"] for batch in persisted["source_batches"]] == [
        ["attack_01", "attack_02"],
        ["attack_03", "attack_04"],
    ]


def test_merge_action_batches_gif_uses_runtime_frame_durations(tmp_path):
    first_source = tmp_path / "raw/attack-a.png"
    second_source = tmp_path / "raw/attack-b.png"
    _source(first_source, (70, 120, 210, 255))
    _source(second_source, (20, 200, 20, 255))
    first = _batch(first_source, tmp_path / "work/batch-a", "attack_01,attack_02", "attack_batch_a")
    second = _batch(
        second_source,
        tmp_path / "work/batch-b",
        "attack_03,attack_04",
        "attack_batch_b",
        scale_reference=Path(first["report"]),
    )

    merged = merge_action_batches(
        [Path(first["report"]), Path(second["report"])],
        tmp_path / "work/merged",
        action_name="attack",
        grid="2x2",
        names="attack_01,attack_02,attack_03,attack_04",
        fps=10,
        loop=False,
        frame_durations=[1, 1.5, 2, 0.5],
        final_dir=tmp_path / "assets/generated/character-bundle/hero",
        final_prefix="hero_attack",
    )

    assert _gif_frame_durations(Path(merged["gif_path"])) == [100, 150, 200, 50]
    assert _gif_loop(Path(merged["gif_path"])) is None


def test_merge_action_batches_rejects_a_plan_that_reorders_frames(tmp_path):
    first_source = tmp_path / "raw/attack-a.png"
    second_source = tmp_path / "raw/attack-b.png"
    _source(first_source, (70, 120, 210, 255))
    _source(second_source, (20, 200, 20, 255))
    first = _batch(first_source, tmp_path / "work/batch-a", "attack_01,attack_02", "attack_batch_a")
    second = _batch(
        second_source,
        tmp_path / "work/batch-b",
        "attack_03,attack_04",
        "attack_batch_b",
        scale_reference=Path(first["report"]),
    )

    with pytest.raises(ActionBatchMergeError, match="exact order"):
        merge_action_batches(
            [Path(first["report"]), Path(second["report"])],
            tmp_path / "work/merged",
            action_name="attack",
            grid="2x2",
            names="attack_01,attack_03,attack_02,attack_04",
            fps=12,
            loop=False,
            frame_durations=[1, 1, 1, 1],
            final_dir=tmp_path / "assets/generated/character-bundle/hero",
            final_prefix="hero_attack",
        )


def test_merge_action_batches_rejects_an_unchecked_later_batch(tmp_path):
    first_source = tmp_path / "raw/attack-a.png"
    second_source = tmp_path / "raw/attack-b.png"
    _source(first_source, (70, 120, 210, 255))
    _source(second_source, (20, 200, 20, 255))
    first = _batch(
        first_source, tmp_path / "work/batch-a", "attack_01,attack_02", "attack_batch_a"
    )
    second = _batch(
        second_source, tmp_path / "work/batch-b", "attack_03,attack_04", "attack_batch_b"
    )

    with pytest.raises(ActionBatchMergeError, match="checked scale reference"):
        merge_action_batches(
            [Path(first["report"]), Path(second["report"])],
            tmp_path / "work/merged",
            action_name="attack",
            grid="2x2",
            names="attack_01,attack_02,attack_03,attack_04",
            fps=12,
            loop=False,
            frame_durations=[1, 1, 1, 1],
            final_dir=tmp_path / "assets/generated/character-bundle/hero",
            final_prefix="hero_attack",
        )


def test_merge_action_batches_rejects_an_inconsistent_scale_ratio(tmp_path):
    first_source = tmp_path / "raw/attack-a.png"
    second_source = tmp_path / "raw/attack-b.png"
    _source(first_source, (70, 120, 210, 255))
    _source(second_source, (20, 200, 20, 255))
    first = _batch(
        first_source, tmp_path / "work/batch-a", "attack_01,attack_02", "attack_batch_a"
    )
    second = _batch(
        second_source,
        tmp_path / "work/batch-b",
        "attack_03,attack_04",
        "attack_batch_b",
        scale_reference=Path(first["report"]),
    )
    second_report = Path(second["report"])
    payload = json.loads(second_report.read_text(encoding="utf-8"))
    payload["scale_reference"]["ratio"] = 99
    second_report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ActionBatchMergeError, match="ratio is inconsistent"):
        merge_action_batches(
            [Path(first["report"]), second_report],
            tmp_path / "work/merged",
            action_name="attack",
            grid="2x2",
            names="attack_01,attack_02,attack_03,attack_04",
            fps=12,
            loop=False,
            frame_durations=[1, 1, 1, 1],
            final_dir=tmp_path / "assets/generated/character-bundle/hero",
            final_prefix="hero_attack",
        )


def test_merge_referenced_action_batches_require_one_scale_reference(tmp_path):
    reference_source = tmp_path / "raw/idle.png"
    first_source = tmp_path / "raw/attack-a.png"
    second_source = tmp_path / "raw/attack-b.png"
    _source(reference_source, (180, 160, 80, 255))
    _source(first_source, (70, 120, 210, 255))
    _source(second_source, (20, 200, 20, 255))
    reference = _batch(
        reference_source, tmp_path / "work/reference", "idle_01,idle_02", "idle"
    )
    first = _batch(
        first_source,
        tmp_path / "work/batch-a",
        "attack_01,attack_02",
        "attack_batch_a",
        scale_reference=Path(reference["report"]),
    )
    second = _batch(
        second_source,
        tmp_path / "work/batch-b",
        "attack_03,attack_04",
        "attack_batch_b",
        scale_reference=Path(reference["report"]),
    )
    reports = [Path(first["report"]), Path(second["report"])]

    merged = merge_action_batches(
        reports,
        tmp_path / "work/merged",
        action_name="attack",
        grid="2x2",
        names="attack_01,attack_02,attack_03,attack_04",
        fps=12,
        loop=False,
        frame_durations=[1, 1, 1, 1],
        final_dir=tmp_path / "assets/generated/character-bundle/hero",
        final_prefix="hero_attack",
    )
    assert merged["scale_reference"]["checked"] is True
    assert all(
        batch["scale_reference"]["reference_metadata_path"] == reference["report"]
        for batch in merged["source_batches"]
    )

    second_payload = json.loads(reports[1].read_text(encoding="utf-8"))
    second_payload["scale_reference"]["reference_metadata_path"] = first["report"]
    reports[1].write_text(json.dumps(second_payload), encoding="utf-8")
    with pytest.raises(ActionBatchMergeError, match="same metadata path"):
        merge_action_batches(
            reports,
            tmp_path / "work/mismatched",
            action_name="attack",
            grid="2x2",
            names="attack_01,attack_02,attack_03,attack_04",
            fps=12,
            loop=False,
            frame_durations=[1, 1, 1, 1],
            final_dir=tmp_path / "assets/generated/character-bundle/mismatched",
            final_prefix="hero_attack",
        )
