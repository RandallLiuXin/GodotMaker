#!/usr/bin/env python3
"""Assemble already processed action-source batches into one action delivery.

This tool never invents or retouches artwork. It only copies real normalized
frames emitted by ``asset_action_process.py`` and creates the delivery sheet and
GIF preview required by the character-bundle runtime contract.
"""
from __future__ import annotations

import argparse
import json
from math import isfinite
from pathlib import Path
import shutil
import sys
from typing import Any

from asset_action_process import (
    ActionProcessError,
    _compose_sheet,
    _is_power_of_two,
    _load_rgba,
    _parse_grid,
    _parse_names,
    _save_gif,
    _write_atomic_json,
)


class ActionBatchMergeError(Exception):
    """Raised when processed source batches cannot form one action."""


def _read_report(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ActionBatchMergeError(f"batch report is not readable JSON: {path}") from exc
    if not isinstance(data, dict) or data.get("ok") is not True:
        raise ActionBatchMergeError(f"batch report is not a successful action report: {path}")
    return data


def _positive(value: Any, label: str) -> None:
    if type(value) not in (int, float) or isinstance(value, bool) or not isfinite(value) or value <= 0:
        raise ActionBatchMergeError(f"{label} must be a finite positive number")


def _batch_frame_paths(report: dict[str, Any], report_path: Path) -> list[Path]:
    labels = report.get("frame_labels")
    paths = report.get("frame_paths")
    if not isinstance(labels, list) or not all(isinstance(value, str) and value for value in labels):
        raise ActionBatchMergeError(f"batch report.frame_labels is invalid: {report_path}")
    if not isinstance(paths, list) or len(paths) != len(labels):
        raise ActionBatchMergeError(f"batch report.frame_paths does not match labels: {report_path}")
    checked: list[Path] = []
    for value in paths:
        if not isinstance(value, str) or not value:
            raise ActionBatchMergeError(f"batch report.frame_paths is invalid: {report_path}")
        path = Path(value)
        if not path.is_file():
            raise ActionBatchMergeError(f"processed batch frame is missing: {path}")
        checked.append(path)
    return checked


def merge_action_batches(
    reports: list[Path],
    output_dir: Path,
    *,
    action_name: str,
    grid: str,
    names: str,
    fps: float,
    loop: bool,
    frame_durations: list[float],
    final_dir: Path,
    final_prefix: str,
    report: Path | None = None,
) -> dict[str, object]:
    """Join ordered action batches without modifying their source artwork."""
    if not reports:
        raise ActionBatchMergeError("at least one --batch-report is required")
    if not isinstance(action_name, str) or not action_name.strip():
        raise ActionBatchMergeError("--action-name is required")
    if not isinstance(final_prefix, str) or not final_prefix.strip():
        raise ActionBatchMergeError("--final-prefix is required")
    _positive(fps, "--fps")
    if type(loop) is not bool:
        raise ActionBatchMergeError("--loop or --no-loop is required")
    columns, rows = _parse_grid(grid)
    names_list = _parse_names(names, columns * rows)
    if not isinstance(frame_durations, list) or len(frame_durations) != len(names_list):
        raise ActionBatchMergeError("--frame-durations must have one value per frame")
    for index, value in enumerate(frame_durations):
        _positive(value, f"--frame-durations[{index}]")

    loaded = [(Path(path), _read_report(Path(path))) for path in reports]
    cell_sizes = {item[1].get("cell_size") for item in loaded}
    if len(cell_sizes) != 1 or not all(type(value) is int and _is_power_of_two(value) for value in cell_sizes):
        raise ActionBatchMergeError("all batch reports must share one power-of-two cell_size")
    cell_size = next(iter(cell_sizes))
    if any(item[1].get("align") != "feet" for item in loaded):
        raise ActionBatchMergeError("all character batch reports must use feet alignment")
    if any(item[1].get("shared_scale") is not True for item in loaded):
        raise ActionBatchMergeError("all character batch reports must use shared_scale")
    if any(item[1].get("edge_touch_frames") not in ([], None) for item in loaded):
        raise ActionBatchMergeError("batch reports with edge-touch frames cannot be merged")

    source_labels: list[str] = []
    source_paths: list[Path] = []
    source_frames: list[dict[str, object]] = []
    for report_path, batch in loaded:
        labels = batch["frame_labels"]
        paths = _batch_frame_paths(batch, report_path)
        source_labels.extend(labels)
        source_paths.extend(paths)
        raw_frames = batch.get("frames")
        if isinstance(raw_frames, list):
            source_frames.extend(item for item in raw_frames if isinstance(item, dict))
    if source_labels != names_list:
        raise ActionBatchMergeError("batch frame labels must match --names in exact order")

    frames = [_load_rgba(path) for path in source_paths]
    try:
        if any(frame.size != (cell_size, cell_size) for frame in frames):
            raise ActionBatchMergeError("all processed batch frames must match the reported cell_size")
        output_dir = Path(output_dir)
        frame_dir = output_dir / "frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        merged_frame_paths: list[Path] = []
        final_dir = Path(final_dir)
        final_dir.mkdir(parents=True, exist_ok=True)
        final_frame_paths: list[str] = []
        for name, source_path, frame in zip(names_list, source_paths, frames):
            intermediate = frame_dir / f"{name}.png"
            frame.save(intermediate)
            merged_frame_paths.append(intermediate)
            target = final_dir / f"{final_prefix}_{name}.png"
            if target.exists():
                raise ActionBatchMergeError(f"merged runtime frame already exists: {target}")
            shutil.copy2(intermediate, target)
            final_frame_paths.append(str(target))

        sheet = _compose_sheet(frames, cols=columns, rows=rows, cell_size=cell_size)
        sheet_path = output_dir / "sheet-transparent.png"
        sheet.save(sheet_path)
        final_sheet = final_dir / f"{final_prefix}_sheet.png"
        if final_sheet.exists():
            raise ActionBatchMergeError(f"merged runtime sheet already exists: {final_sheet}")
        shutil.copy2(sheet_path, final_sheet)

        gif_path = output_dir / "animation.gif"
        _save_gif(
            frames,
            gif_path,
            fps=float(fps),
            frame_durations=[float(value) for value in frame_durations],
        )
        final_gif = final_dir / f"{final_prefix}.gif"
        if final_gif.exists():
            raise ActionBatchMergeError(f"merged runtime GIF already exists: {final_gif}")
        shutil.copy2(gif_path, final_gif)
    finally:
        for frame in frames:
            frame.close()

    scale_reference = loaded[0][1].get("scale_reference")
    if not isinstance(scale_reference, dict) or type(scale_reference.get("checked")) is not bool:
        raise ActionBatchMergeError("batch report must retain scale_reference.checked")
    metadata: dict[str, object] = {
        "version": 1,
        "ok": True,
        "action_name": action_name,
        "grid": {"cols": columns, "rows": rows},
        "frame_count": len(names_list),
        "frame_labels": names_list,
        "cell_size": cell_size,
        "align": "feet",
        "shared_scale": True,
        "fps": float(fps),
        "loop": loop,
        "frame_durations": [float(value) for value in frame_durations],
        "edge_touch_frames": [],
        "frames": source_frames,
        "frame_paths": [str(path) for path in merged_frame_paths],
        "sheet_path": str(sheet_path),
        "gif_path": str(gif_path),
        "final_frame_paths": final_frame_paths,
        "final_sheet_path": str(final_sheet),
        "final_gif_path": str(final_gif),
        "scale_reference": scale_reference,
        "source_batches": [
            {"report": str(path), "frame_labels": batch["frame_labels"]}
            for path, batch in loaded
        ],
    }
    meta_path = Path(report) if report is not None else output_dir / "pipeline-meta.json"
    _write_atomic_json(meta_path, metadata)
    metadata["report"] = str(meta_path)
    return metadata


def _main() -> int:
    parser = argparse.ArgumentParser(description="Assemble processed character action source batches")
    parser.add_argument("--batch-report", action="append", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--action-name", required=True)
    parser.add_argument("--grid", required=True)
    parser.add_argument("--names", required=True)
    parser.add_argument("--fps", required=True, type=float)
    loop_group = parser.add_mutually_exclusive_group(required=True)
    loop_group.add_argument("--loop", dest="loop", action="store_true")
    loop_group.add_argument("--no-loop", dest="loop", action="store_false")
    parser.add_argument("--frame-durations", required=True)
    parser.add_argument("--final-dir", required=True, type=Path)
    parser.add_argument("--final-prefix", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = merge_action_batches(
            args.batch_report,
            args.out_dir,
            action_name=args.action_name,
            grid=args.grid,
            names=args.names,
            fps=args.fps,
            loop=args.loop,
            frame_durations=[float(value) for value in args.frame_durations.split(",")],
            final_dir=args.final_dir,
            final_prefix=args.final_prefix,
            report=args.report,
        )
    except (ActionBatchMergeError, ActionProcessError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
