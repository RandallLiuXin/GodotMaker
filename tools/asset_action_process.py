#!/usr/bin/env python3
"""Process a character action source sheet into runtime-ready frames."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from math import isfinite
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_sheet_process import (
    SheetProcessError,
    _autoslice_rects,
    _remove_magenta_background,
    process_sheet,
)


class ActionProcessError(Exception):
    """Raised when a character action sheet cannot be processed."""


class ActionRegenerationRequired(ActionProcessError):
    """Raised when processing completed with a retryable source-image diagnosis."""

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        super().__init__(str(result["message"]))


def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0


def _parse_grid(value: str) -> tuple[int, int]:
    raw = value.lower().strip()
    if "x" not in raw:
        raise ActionProcessError("--grid must use COLSxROWS")
    left, right = raw.split("x", 1)
    try:
        cols = int(left)
        rows = int(right)
    except ValueError as exc:
        raise ActionProcessError("--grid must use integer dimensions") from exc
    if cols <= 0 or rows <= 0:
        raise ActionProcessError("--grid dimensions must be positive")
    return cols, rows


def _parse_names(value: str, total: int) -> list[str]:
    names = [name.strip() for name in value.split(",")]
    if any(not name for name in names):
        raise ActionProcessError("--names cannot contain empty names")
    if len(names) != total:
        raise ActionProcessError(f"--names has {len(names)} entries, grid has {total} cells")
    return names


def _write_atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(path.parent),
        suffix=".json",
        mode="w",
        encoding="utf-8",
    ) as handle:
        tmp_path = Path(handle.name)
        json.dump(data, handle, indent=2)
        handle.write("\n")
    try:
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _load_rgba(path: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ActionProcessError("Pillow is required to process action sheets") from exc
    try:
        image = Image.open(path).convert("RGBA")
        image.load()
        return image
    except Exception as exc:
        raise ActionProcessError(f"Frame is not a readable image: {path}") from exc


def _normalize_frames(
    frame_paths: list[Path],
    *,
    cell_size: int,
    fit_scale: float,
    align: str,
    shared_scale: bool,
) -> tuple[list[Any], list[dict[str, object]]]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ActionProcessError("Pillow is required to process action sheets") from exc

    originals = [_load_rgba(path) for path in frame_paths]
    try:
        max_width = max((image.width for image in originals), default=0)
        max_height = max((image.height for image in originals), default=0)
        if max_width <= 0 or max_height <= 0:
            raise ActionProcessError("Action source produced no visible frames")

        common_scale = None
        if shared_scale:
            common_scale = min(cell_size / max_width, cell_size / max_height) * fit_scale

        frames = []
        metadata = []
        for path, image in zip(frame_paths, originals):
            scale = common_scale or min(cell_size / image.width, cell_size / image.height) * fit_scale
            width = max(1, int(image.width * scale))
            height = max(1, int(image.height * scale))
            resized = image.resize((width, height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (cell_size, cell_size), (0, 0, 0, 0))
            x = (cell_size - width) // 2
            if align in {"bottom", "feet"}:
                pad = max(0, int(cell_size * (1 - fit_scale) * 0.5))
                y = cell_size - height - pad
            else:
                y = (cell_size - height) // 2
            canvas.paste(resized, (x, y), resized)
            frames.append(canvas)
            metadata.append(
                {
                    "candidate_path": str(path),
                    "source_size": [image.width, image.height],
                    "output_size": [width, height],
                    "paste_position": [x, y],
                }
            )
        return frames, metadata
    finally:
        for image in originals:
            image.close()


def _compose_sheet(frames: list[Any], *, cols: int, rows: int, cell_size: int):
    from PIL import Image

    sheet = Image.new("RGBA", (cols * cell_size, rows * cell_size), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        col = index % cols
        row = index // cols
        sheet.paste(frame, (col * cell_size, row * cell_size), frame)
    return sheet


def _gif_frame_durations_ms(fps: float, frame_durations: list[float]) -> list[int]:
    return [
        max(10, int(round((1000.0 * float(duration) / float(fps)) / 10.0)) * 10)
        for duration in frame_durations
    ]


def _save_gif(
    frames: list[Any],
    path: Path,
    *,
    fps: float,
    loop: bool,
    frame_durations: list[float],
) -> list[int]:
    if not frames:
        raise ActionProcessError("No frames to encode")
    if len(frame_durations) != len(frames):
        raise ActionProcessError("GIF frame durations must match the frame count")
    if type(loop) is not bool:
        raise ActionProcessError("GIF loop must be boolean")
    durations_ms = _gif_frame_durations_ms(fps, frame_durations)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_options = {
        "format": "GIF",
        "save_all": True,
        "append_images": frames[1:],
        "duration": durations_ms,
        "disposal": 2,
        "transparency": 0,
    }
    if loop:
        save_options["loop"] = 0
    frames[0].save(path, **save_options)
    return durations_ms


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _frame_heights_from_metadata(metadata: dict[str, Any]) -> list[float]:
    frames = metadata.get("frames")
    if not isinstance(frames, list):
        return []
    heights: list[float] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        output_size = frame.get("output_size")
        if (
            isinstance(output_size, list)
            and len(output_size) == 2
            and isinstance(output_size[1], (int, float))
            and output_size[1] > 0
        ):
            heights.append(float(output_size[1]))
    return heights


def _check_scale_reference(
    metadata: dict[str, Any],
    reference_path: Path | None,
    *,
    tolerance: float,
) -> dict[str, object]:
    if reference_path is None:
        return {"checked": False}
    if tolerance <= 0:
        raise ActionProcessError("--scale-tolerance must be positive")
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ActionProcessError(f"Scale reference metadata is not readable: {reference_path}") from exc

    current_height = _median(_frame_heights_from_metadata(metadata))
    reference_height = _median(_frame_heights_from_metadata(reference))
    if current_height is None:
        raise ActionProcessError("Current action metadata has no frame heights")
    if reference_height is None:
        raise ActionProcessError("Scale reference metadata has no frame heights")

    ratio = current_height / reference_height
    min_ratio = 1 - tolerance
    max_ratio = 1 + tolerance
    result: dict[str, object] = {
        "checked": True,
        "reference_metadata_path": str(reference_path),
        "current_median_height": current_height,
        "reference_median_height": reference_height,
        "ratio": ratio,
        "tolerance": tolerance,
    }
    if ratio < min_ratio or ratio > max_ratio:
        raise ActionProcessError(
            "Body scale drift exceeds tolerance: "
            f"{ratio:.3f} outside {min_ratio:.3f}-{max_ratio:.3f}"
        )
    return result


def _reference_median_height(reference_path: Path) -> float:
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ActionProcessError(f"Scale reference metadata is not readable: {reference_path}") from exc
    height = _median(_frame_heights_from_metadata(reference))
    if height is None:
        raise ActionProcessError("Scale reference metadata has no frame heights")
    return height


def _copy_runtime_outputs(
    frame_paths: list[Path],
    sheet_path: Path,
    gif_path: Path,
    *,
    final_dir: Path | None,
    final_prefix: str | None,
    final_sheet_name: str | None,
) -> tuple[list[str], str | None, str | None]:
    if final_dir is None:
        return [str(path) for path in frame_paths], None, None
    if not final_prefix:
        raise ActionProcessError("--final-prefix is required when --final-dir is used")
    final_dir.mkdir(parents=True, exist_ok=True)
    final_frames = []
    used_names: set[str] = set()
    for path in frame_paths:
        frame_stem = path.stem
        output_stem = frame_stem if frame_stem.startswith(f"{final_prefix}_") else f"{final_prefix}_{frame_stem}"
        output_name = f"{output_stem}{path.suffix}"
        if output_name in used_names:
            raise ActionProcessError(f"Runtime frame name collision: {output_name}")
        used_names.add(output_name)
        target = final_dir / output_name
        shutil.copy2(path, target)
        final_frames.append(str(target))
    if final_sheet_name is not None:
        if (not final_sheet_name.endswith(".png")
                or Path(final_sheet_name).name != final_sheet_name):
            raise ActionProcessError("--final-sheet-name must be a PNG filename without directories")
    final_sheet = final_dir / (final_sheet_name or f"{final_prefix}_sheet.png")
    shutil.copy2(sheet_path, final_sheet)
    final_gif = final_dir / f"{final_prefix}.gif"
    shutil.copy2(gif_path, final_gif)
    return final_frames, str(final_sheet), str(final_gif)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _history_path_for(source: Path, timestamp: str) -> Path:
    history_dir = source.parent / "history"
    candidate = history_dir / f"{source.stem}.{timestamp}{source.suffix}"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        numbered = history_dir / f"{source.stem}.{timestamp}-{index}{source.suffix}"
        if not numbered.exists():
            return numbered
        index += 1


def _visible_pixel_count(alpha: Any, box: tuple[int, int, int, int]) -> int:
    left, top, right, bottom = box
    if left >= right or top >= bottom:
        return 0
    histogram = alpha.crop(box).histogram()
    return sum(histogram[1:])


def _intersect_rect(
    first: tuple[int, int, int, int],
    second: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    return (
        max(first[0], second[0]),
        max(first[1], second[1]),
        min(first[2], second[2]),
        min(first[3], second[3]),
    )


def _maximum_weight_assignment(weights: list[list[int]]) -> list[int]:
    size = len(weights)
    if size == 0 or any(len(row) != size for row in weights):
        raise ActionProcessError("Recovery assignment requires a square score matrix")

    max_weight = max(max(row) for row in weights)
    row_potential = [0] * (size + 1)
    column_potential = [0] * (size + 1)
    matched_row = [0] * (size + 1)
    previous_column = [0] * (size + 1)

    for row in range(1, size + 1):
        matched_row[0] = row
        current_column = 0
        minimum = [float("inf")] * (size + 1)
        used = [False] * (size + 1)
        while True:
            used[current_column] = True
            current_row = matched_row[current_column]
            delta = float("inf")
            next_column = 0
            for column in range(1, size + 1):
                if used[column]:
                    continue
                cost = max_weight - weights[current_row - 1][column - 1]
                reduced = cost - row_potential[current_row] - column_potential[column]
                if reduced < minimum[column]:
                    minimum[column] = reduced
                    previous_column[column] = current_column
                if minimum[column] < delta:
                    delta = minimum[column]
                    next_column = column
            for column in range(size + 1):
                if used[column]:
                    row_potential[matched_row[column]] += delta
                    column_potential[column] -= delta
                else:
                    minimum[column] -= delta
            current_column = next_column
            if matched_row[current_column] == 0:
                break
        while True:
            next_column = previous_column[current_column]
            matched_row[current_column] = matched_row[next_column]
            current_column = next_column
            if current_column == 0:
                break

    assignment = [-1] * size
    for column in range(1, size + 1):
        assignment[matched_row[column] - 1] = column - 1
    return assignment


def _assign_recovery_rects_to_cells(
    scan_image: Any,
    rects: list[tuple[int, int, int, int]],
    *,
    cols: int,
    rows: int,
) -> tuple[list[tuple[int, int, int, int]], list[dict[str, object]]]:
    width, height = scan_image.size
    cell_width = width // cols
    cell_height = height // rows
    alpha = scan_image.getchannel("A")
    try:
        cell_boxes: list[tuple[int, int, int, int]] = []
        core_boxes: list[tuple[int, int, int, int]] = []
        for index in range(cols * rows):
            row, col = divmod(index, cols)
            left = col * cell_width
            top = row * cell_height
            right = left + cell_width
            bottom = top + cell_height
            cell_boxes.append((left, top, right, bottom))
            inset_x = cell_width // 4
            inset_y = cell_height // 4
            core_boxes.append((left + inset_x, top + inset_y, right - inset_x, bottom - inset_y))

        overlaps: list[list[int]] = []
        core_overlaps: list[list[int]] = []
        scores: list[list[int]] = []
        for rect in rects:
            rect_overlaps = [
                _visible_pixel_count(alpha, _intersect_rect(rect, cell_box))
                for cell_box in cell_boxes
            ]
            rect_core_overlaps = [
                _visible_pixel_count(alpha, _intersect_rect(rect, core_box))
                for core_box in core_boxes
            ]
            overlaps.append(rect_overlaps)
            core_overlaps.append(rect_core_overlaps)
            scores.append([
                overlap + core_overlap
                for overlap, core_overlap in zip(rect_overlaps, rect_core_overlaps)
            ])

        assigned_cells = _maximum_weight_assignment(scores)
        ordered: list[tuple[int, int, int, int] | None] = [None] * len(rects)
        diagnostics: list[dict[str, object] | None] = [None] * len(rects)
        for rect_index, cell_index in enumerate(assigned_cells):
            total_foreground_pixels = sum(overlaps[rect_index])
            assigned_foreground_pixels = (
                overlaps[rect_index][cell_index]
                if cell_index >= 0
                else 0
            )
            ownership_ratio = (
                assigned_foreground_pixels / total_foreground_pixels
                if total_foreground_pixels > 0
                else 0.0
            )
            if (
                cell_index < 0
                or scores[rect_index][cell_index] <= 0
                or ownership_ratio <= 0.5
            ):
                raise ActionRegenerationRequired(
                    {
                        "version": 1,
                        "ok": False,
                        "status": "needs_regeneration",
                        "retryable": True,
                        "reason": "recovery_cell_assignment_failed",
                        "message": "Autoslice recovery could not assign every frame to one source grid cell",
                        "found_frame_count": len(rects),
                        "expected_frame_count": cols * rows,
                        "assigned_cell": (
                            [cell_index % cols, cell_index // cols]
                            if cell_index >= 0
                            else None
                        ),
                        "assigned_foreground_pixels": assigned_foreground_pixels,
                        "total_foreground_pixels": total_foreground_pixels,
                        "ownership_ratio": ownership_ratio,
                        "recommended_action": "regenerate_source",
                    }
                )
            ordered[cell_index] = rects[rect_index]
            row, col = divmod(cell_index, cols)
            diagnostics[cell_index] = {
                "source_cell": [col, row],
                "source_cell_overlap_pixels": overlaps[rect_index][cell_index],
                "source_cell_core_overlap_pixels": core_overlaps[rect_index][cell_index],
                "source_cell_ownership_ratio": ownership_ratio,
                "assignment_score": scores[rect_index][cell_index],
                "cell_scores": [
                    {
                        "cell": [candidate % cols, candidate // cols],
                        "foreground_pixels": overlaps[rect_index][candidate],
                        "core_foreground_pixels": core_overlaps[rect_index][candidate],
                        "score": scores[rect_index][candidate],
                    }
                    for candidate in range(cols * rows)
                ],
            }

        if any(rect is None for rect in ordered) or any(item is None for item in diagnostics):
            raise ActionProcessError("Recovery assignment did not fill every source grid cell")
        return (
            [rect for rect in ordered if rect is not None],
            [item for item in diagnostics if item is not None],
        )
    finally:
        alpha.close()


def _write_recovered_action_source(
    source: Path,
    *,
    output_dir: Path,
    grid: str,
    frame_names: list[str],
    background: str,
    align: str,
    timestamp: str | None,
) -> dict[str, object]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ActionProcessError("Pillow is required to recover action sheets") from exc

    source = Path(source)
    if not source.exists():
        raise ActionProcessError(f"Source sheet not found: {source}")

    cols, rows = _parse_grid(grid)
    expected = cols * rows
    if len(frame_names) != expected:
        raise ActionProcessError("Recovery frame names do not match grid")

    image = Image.open(source).convert("RGBA")
    try:
        if background == "magenta":
            scan_image, cleanup = _remove_magenta_background(
                image,
                threshold=40,
                edge_threshold=220,
            )
        elif background == "transparent":
            scan_image = image.copy()
            cleanup = {"removed_pixels": 0, "edge_removed_pixels": 0}
        else:
            raise ActionProcessError("--background must be transparent or magenta")

        rects = _autoslice_rects(scan_image)
        if len(rects) != expected:
            message = f"Autoslice recovery found {len(rects)} frames; expected {expected}"
            raise ActionRegenerationRequired(
                {
                    "version": 1,
                    "ok": False,
                    "status": "needs_regeneration",
                    "retryable": True,
                    "reason": "recovery_frame_count_mismatch",
                    "message": message,
                    "source_path": str(source),
                    "found_frame_count": len(rects),
                    "expected_frame_count": expected,
                    "recommended_action": "regenerate_source",
                }
            )

        width, height = image.size
        if width % cols != 0 or height % rows != 0:
            raise ActionProcessError("Source dimensions must divide evenly by grid")
        original_cell_w = width // cols
        original_cell_h = height // rows
        rects, assignment_diagnostics = _assign_recovery_rects_to_cells(
            scan_image,
            rects,
            cols=cols,
            rows=rows,
        )
        padding = max(8, int(min(original_cell_w, original_cell_h) * 0.08))
        max_crop_w = max(rect[2] - rect[0] for rect in rects)
        max_crop_h = max(rect[3] - rect[1] for rect in rects)
        cell_w = max(original_cell_w, max_crop_w + padding * 2)
        cell_h = max(original_cell_h, max_crop_h + padding * 2)

        recovered = Image.new("RGBA", (cell_w * cols, cell_h * rows), (0, 0, 0, 0))
        placements: list[dict[str, object]] = []
        for index, (name, rect, assignment) in enumerate(
            zip(frame_names, rects, assignment_diagnostics)
        ):
            left, top, right, bottom = rect
            crop = scan_image.crop(rect)
            row, col = divmod(index, cols)
            x = col * cell_w + (cell_w - crop.width) // 2
            if align in {"bottom", "feet"}:
                y = row * cell_h + cell_h - crop.height - padding
            else:
                y = row * cell_h + (cell_h - crop.height) // 2
            # The destination is transparent and components do not overlap.
            # Copy RGBA directly so a semitransparent antialiased source edge
            # keeps its original colour and alpha instead of being composited
            # against the old magenta recovery canvas.
            recovered.paste(crop, (x, y))
            placements.append(
                {
                    "name": name,
                    "source_bbox": [left, top, right, bottom],
                    "source_size": [crop.width, crop.height],
                    **assignment,
                    "target_cell": [col, row],
                    "paste_position": [x, y],
                }
            )

        archive_timestamp = timestamp or _utc_timestamp()
        archived_source = _history_path_for(source, archive_timestamp)
        archived_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, archived_source)
        recovered.save(source)

        report = {
            "version": 1,
            "ok": True,
            "method": "autoslice_repack",
            "ordering_method": "grid_foreground_overlap",
            "archived_source_path": str(archived_source),
            "active_source_path": str(source),
            "background": background,
            "cleanup": cleanup,
            "grid": {"cols": cols, "rows": rows},
            "original_size": [width, height],
            "recovered_size": [recovered.width, recovered.height],
            "original_cell_size": [original_cell_w, original_cell_h],
            "recovered_cell_size": [cell_w, cell_h],
            "padding": padding,
            "placements": placements,
        }
        recovery_report = output_dir / "recovery-report.json"
        _write_atomic_json(recovery_report, report)
        report["report"] = str(recovery_report)
        return report
    finally:
        image.close()


def _has_edge_touch_rejection(curation: dict[str, object]) -> bool:
    rejected = curation.get("rejected")
    if not isinstance(rejected, list):
        return False
    return any(isinstance(item, dict) and item.get("reason") == "edge_touch" for item in rejected)


def process_action_sheet(
    source: Path,
    output_dir: Path,
    *,
    grid: str,
    names: str,
    asset_id: str | None = None,
    tag: str | None = None,
    background: str = "magenta",
    component_mode: str = "largest",
    component_padding: int = 8,
    min_component_area: int = 100,
    cell_size: int = 256,
    fit_scale: float = 0.85,
    align: str = "feet",
    shared_scale: bool = True,
    action_name: str | None = None,
    fps: float | None = None,
    loop: bool | None = None,
    frame_durations: list[float] | None = None,
    reject_edge_touch: bool = True,
    recover_edge_touch: bool = False,
    recovery_timestamp: str | None = None,
    scale_reference_metadata: Path | None = None,
    scale_tolerance: float = 0.15,
    match_scale_reference: bool = False,
    final_dir: Path | None = None,
    final_prefix: str | None = None,
    final_sheet_name: str | None = None,
    report: Path | None = None,
) -> dict[str, object]:
    """Normalize one action sheet into frames, a transparent sheet, GIF, and metadata."""
    if align not in {"center", "bottom", "feet"}:
        raise ActionProcessError("--align must be center, bottom, or feet")
    if not _is_power_of_two(cell_size):
        raise ActionProcessError("--cell-size must be a positive power of two")
    if fit_scale <= 0:
        raise ActionProcessError("--fit-scale must be positive")
    cols, rows = _parse_grid(grid)
    frame_names = _parse_names(names, cols * rows)
    if not isinstance(action_name, str) or not action_name.strip():
        raise ActionProcessError("--action-name is required")
    if (type(fps) not in (int, float) or isinstance(fps, bool)
            or not isfinite(fps) or fps <= 0):
        raise ActionProcessError("--fps must be a positive number")
    if type(loop) is not bool:
        raise ActionProcessError("--loop or --no-loop is required")
    if not isinstance(frame_durations, list) or len(frame_durations) != len(frame_names):
        raise ActionProcessError("--frame-durations must have one value per frame")
    if any(type(value) not in (int, float) or isinstance(value, bool)
           or not isfinite(value) or value <= 0
           for value in frame_durations):
        raise ActionProcessError("--frame-durations values must be positive numbers")

    output_dir = Path(output_dir)
    candidate_dir = output_dir / "candidates"
    frame_dir = output_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    curation_report = output_dir / "curation-report.json"
    initial_curation_report = output_dir / "curation-report.initial-grid.json"
    source_recovery: dict[str, object] | None = None
    recovered_background = background

    try:
        curation = process_sheet(
            source,
            candidate_dir,
            grid=grid,
            names=names,
            asset_id=asset_id,
            tag=tag,
            background=background,
            snap_mode="grid",
            component_mode=component_mode,
            component_padding=component_padding,
            min_component_area=min_component_area,
            reject_edge_touch=reject_edge_touch,
            report=curation_report,
        )
    except SheetProcessError as exc:
        raise ActionProcessError(str(exc)) from exc

    candidates = {
        str(item.get("name")): Path(str(item.get("path")))
        for item in curation.get("candidates", [])
        if isinstance(item, dict) and item.get("path")
    }
    missing = [name for name in frame_names if name not in candidates]
    if missing and recover_edge_touch and reject_edge_touch and _has_edge_touch_rejection(curation):
        if curation_report.exists():
            shutil.copy2(curation_report, initial_curation_report)
        try:
            source_recovery = _write_recovered_action_source(
                source,
                output_dir=output_dir,
                grid=grid,
                frame_names=frame_names,
                background=background,
                align=align,
                timestamp=recovery_timestamp,
            )
            # Recovery writes an already-clean transparent source.  Running
            # magenta cleanup again would double-matte semitransparent edges.
            recovered_background = "transparent"
        except ActionRegenerationRequired as exc:
            diagnostic = {
                **exc.result,
                "action_name": action_name,
                "grid": grid,
                "frame_names": frame_names,
                "initial_curation_report_path": str(initial_curation_report),
            }
            diagnostic_report = report or output_dir / "regeneration-report.json"
            diagnostic["report"] = str(diagnostic_report)
            _write_atomic_json(diagnostic_report, diagnostic)
            raise ActionRegenerationRequired(diagnostic) from exc
        try:
            curation = process_sheet(
                source,
                candidate_dir,
                grid=grid,
                names=names,
                asset_id=asset_id,
                tag=tag,
                background=recovered_background,
                snap_mode="grid",
                component_mode=component_mode,
                component_padding=component_padding,
                min_component_area=min_component_area,
                reject_edge_touch=reject_edge_touch,
                report=curation_report,
            )
        except SheetProcessError as exc:
            raise ActionProcessError(str(exc)) from exc
        candidates = {
            str(item.get("name")): Path(str(item.get("path")))
            for item in curation.get("candidates", [])
            if isinstance(item, dict) and item.get("path")
        }
        missing = [name for name in frame_names if name not in candidates]
    if missing:
        raise ActionProcessError(f"Missing required frames: {', '.join(missing)}")

    normalized, frame_meta = _normalize_frames(
        [candidates[name] for name in frame_names],
        cell_size=cell_size,
        fit_scale=fit_scale,
        align=align,
        shared_scale=shared_scale,
    )
    scale_normalization: dict[str, object] | None = None
    if match_scale_reference:
        if scale_reference_metadata is None:
            raise ActionProcessError("--match-scale-reference requires --scale-reference-metadata")
        current_height = _median(_frame_heights_from_metadata({"frames": frame_meta}))
        reference_height = _reference_median_height(scale_reference_metadata)
        if current_height is None:
            raise ActionProcessError("Current action metadata has no frame heights")
        effective_fit_scale = fit_scale * reference_height / current_height
        # A normalized frame must retain transparent padding so feet alignment
        # remains meaningful instead of clipping provider artwork at the cell edge.
        if effective_fit_scale <= 0 or effective_fit_scale > 0.95:
            raise ActionProcessError(
                "Body scale cannot be matched within the normalized cell safely: "
                f"requested fit scale {effective_fit_scale:.3f}"
            )
        normalized, frame_meta = _normalize_frames(
            [candidates[name] for name in frame_names],
            cell_size=cell_size,
            fit_scale=effective_fit_scale,
            align=align,
            shared_scale=shared_scale,
        )
        scale_normalization = {
            "mode": "reference_median_height",
            "reference_metadata_path": str(scale_reference_metadata),
            "initial_fit_scale": fit_scale,
            "effective_fit_scale": effective_fit_scale,
            "reference_median_height": reference_height,
        }
    frame_paths = []
    for name, frame, meta in zip(frame_names, normalized, frame_meta):
        path = frame_dir / f"{name}.png"
        frame.save(path)
        meta["name"] = name
        meta["path"] = str(path)
        frame_paths.append(path)

    sheet = _compose_sheet(normalized, cols=cols, rows=rows, cell_size=cell_size)
    sheet_path = output_dir / "sheet-transparent.png"
    sheet.save(sheet_path)
    gif_path = output_dir / "animation.gif"
    _save_gif(
        normalized,
        gif_path,
        fps=float(fps),
        loop=loop,
        frame_durations=[float(value) for value in frame_durations],
    )
    final_frames, final_sheet, final_gif = _copy_runtime_outputs(
        frame_paths,
        sheet_path,
        gif_path,
        final_dir=final_dir,
        final_prefix=final_prefix,
        final_sheet_name=final_sheet_name,
    )

    metadata: dict[str, object] = {
        "version": 1,
        "ok": True,
        "asset_id": asset_id,
        "tag": tag,
        "source_path": str(source),
        "output_dir": str(output_dir),
        "grid": {"cols": cols, "rows": rows},
        "frame_count": len(frame_names),
        "frame_labels": frame_names,
        "component_mode": component_mode,
        "component_padding": component_padding,
        "min_component_area": min_component_area,
        "cell_size": cell_size,
        "fit_scale": scale_normalization["effective_fit_scale"] if scale_normalization else fit_scale,
        "align": align,
        "shared_scale": shared_scale,
        "action_name": action_name,
        "fps": float(fps),
        "loop": loop,
        "frame_durations": [float(value) for value in frame_durations],
        "curation_report_path": str(curation_report),
        "initial_curation_report_path": (
            str(initial_curation_report) if source_recovery is not None else None
        ),
        "source_recovery": source_recovery,
        "edge_touch_frames": curation.get("edge_touch_candidates", []),
        "frames": frame_meta,
        "frame_paths": [str(path) for path in frame_paths],
        "sheet_path": str(sheet_path),
        "gif_path": str(gif_path),
        "final_frame_paths": final_frames,
        "final_sheet_path": final_sheet,
        "final_gif_path": final_gif,
        "scale_normalization": scale_normalization,
    }
    metadata["scale_reference"] = _check_scale_reference(
        metadata,
        scale_reference_metadata,
        tolerance=scale_tolerance,
    )
    meta_path = Path(report) if report is not None else output_dir / "pipeline-meta.json"
    _write_atomic_json(meta_path, metadata)
    metadata["report"] = str(meta_path)
    return metadata


def _main() -> int:
    parser = argparse.ArgumentParser(description="Process a character action source sheet")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--grid", required=True)
    parser.add_argument("--names", required=True)
    parser.add_argument("--kind", required=True, choices=["body", "fx"])
    parser.add_argument("--asset-id")
    parser.add_argument("--tag")
    parser.add_argument("--background", choices=["transparent", "magenta"], default="magenta")
    parser.add_argument(
        "--cell-size",
        type=int,
        default=256,
        help="Power-of-two runtime frame canvas in pixels (default: 256)",
    )
    parser.add_argument("--align", choices=["center", "bottom", "feet"])
    parser.add_argument("--recover-edge-touch", action="store_true")
    parser.add_argument("--scale-reference-metadata", type=Path)
    parser.add_argument("--scale-tolerance", type=float, default=0.15)
    parser.add_argument("--fit-scale", type=float, default=0.85)
    parser.add_argument("--match-scale-reference", action="store_true")
    parser.add_argument("--final-dir", type=Path)
    parser.add_argument("--final-prefix")
    parser.add_argument("--final-sheet-name")
    parser.add_argument("--action-name", required=True)
    parser.add_argument("--fps", required=True, type=float)
    loop_group = parser.add_mutually_exclusive_group(required=True)
    loop_group.add_argument("--loop", dest="loop", action="store_true")
    loop_group.add_argument("--no-loop", dest="loop", action="store_false")
    parser.add_argument("--frame-durations", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    component_mode = "largest" if args.kind == "body" else "all"
    align = args.align or ("feet" if args.kind == "body" else "center")

    try:
        result = process_action_sheet(
            args.source,
            args.out_dir,
            grid=args.grid,
            names=args.names,
            asset_id=args.asset_id,
            tag=args.tag,
            background=args.background,
            cell_size=args.cell_size,
            component_mode=component_mode,
            align=align,
            recover_edge_touch=args.recover_edge_touch,
            scale_reference_metadata=args.scale_reference_metadata,
            scale_tolerance=args.scale_tolerance,
            fit_scale=args.fit_scale,
            match_scale_reference=args.match_scale_reference,
            final_dir=args.final_dir,
            final_prefix=args.final_prefix,
            final_sheet_name=args.final_sheet_name,
            action_name=args.action_name,
            fps=args.fps,
            loop=args.loop,
            frame_durations=[float(value) for value in args.frame_durations.split(",")],
            report=args.report,
        )
    except ActionRegenerationRequired as exc:
        print(json.dumps(exc.result))
        return 2
    except ActionProcessError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
