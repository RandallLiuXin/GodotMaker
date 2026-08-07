#!/usr/bin/env python3
"""Recover a fixed-grid image sheet from whole-sheet pixel components.

This tool deliberately knows nothing about asset families or Skill workflows. It
uses 8-neighbour foreground connectivity across the complete source image, then
assigns the resulting components to declared grid cells by actual foreground
pixel ownership (with deterministic centre-distance tie breaking).
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_sheet_process import _remove_magenta_background


class RecoveryError(Exception):
    """An invalid recovery invocation or unreadable source image."""


class RecoveryIncomplete(RecoveryError):
    """The source is valid, but cannot be safely recovered into its grid."""

    def __init__(self, report: dict[str, object]) -> None:
        self.report = report
        super().__init__(str(report["message"]))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".json", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    try:
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _parse_grid(value: str) -> tuple[int, int]:
    parts = value.lower().strip().split("x")
    if len(parts) != 2:
        raise RecoveryError("--grid must use COLSxROWS")
    try:
        cols, rows = (int(part) for part in parts)
    except ValueError as exc:
        raise RecoveryError("--grid must use integer dimensions") from exc
    if cols <= 0 or rows <= 0:
        raise RecoveryError("--grid dimensions must be positive")
    return cols, rows


def _maximum_weight_assignment(weights: list[list[int]]) -> list[int]:
    """Return the deterministic maximum-weight component-to-cell assignment."""
    size = len(weights)
    if size == 0 or any(len(row) != size for row in weights):
        raise RecoveryError("component assignment requires a square score matrix")
    maximum = max(max(row) for row in weights)
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
                cost = maximum - weights[current_row - 1][column - 1]
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


def _components(image: Any, *, min_area: int) -> list[dict[str, object]]:
    """Find 8-connected non-transparent components without using their AABBs."""
    alpha = image.getchannel("A")
    width, height = image.size
    try:
        foreground = {index for index, value in enumerate(alpha.getdata()) if value > 0}
    finally:
        alpha.close()
    found: list[dict[str, object]] = []
    while foreground:
        start = min(foreground)
        foreground.remove(start)
        stack = [start]
        pixels: list[int] = []
        while stack:
            point = stack.pop()
            pixels.append(point)
            y, x = divmod(point, width)
            for yy in range(max(0, y - 1), min(height, y + 2)):
                for xx in range(max(0, x - 1), min(width, x + 2)):
                    neighbour = yy * width + xx
                    if neighbour in foreground:
                        foreground.remove(neighbour)
                        stack.append(neighbour)
        if len(pixels) < min_area:
            continue
        xs = [point % width for point in pixels]
        ys = [point // width for point in pixels]
        found.append({
            "pixels": pixels,
            "area": len(pixels),
            "bbox": [min(xs), min(ys), max(xs) + 1, max(ys) + 1],
            "centre": [sum(xs) / len(xs), sum(ys) / len(ys)],
        })
    return sorted(found, key=lambda component: tuple(component["bbox"]))


def _cell_index(x: int, y: int, *, width: int, height: int, cols: int, rows: int) -> int:
    col = min(cols - 1, x * cols // width)
    row = min(rows - 1, y * rows // height)
    return row * cols + col


def _recover(
    source: Path,
    output: Path,
    *,
    cols: int,
    rows: int,
    background: str,
    min_component_area: int,
    padding: int,
) -> dict[str, object]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise RecoveryError("Pillow is required for connected-component recovery") from exc
    try:
        image = Image.open(source).convert("RGBA")
        image.load()
    except Exception as exc:
        raise RecoveryError(f"source is not a readable image: {source}") from exc
    try:
        if background == "magenta":
            scan, cleanup = _remove_magenta_background(image)
        else:
            scan = image.copy()
            cleanup = {"background": "transparent", "algorithm": None}
        try:
            components = _components(scan, min_area=min_component_area)
            expected = cols * rows
            if len(components) != expected:
                raise RecoveryIncomplete({
                    "version": 1, "ok": False, "status": "needs_fallback",
                    "error_code": "component_count_mismatch",
                    "message": f"found {len(components)} connected components; expected {expected}",
                    "component_count": len(components), "expected_component_count": expected,
                })

            ownership: list[list[int]] = []
            scores: list[list[int]] = []
            centres: list[list[float]] = []
            for component in components:
                counts = [0] * expected
                for point in component["pixels"]:
                    y, x = divmod(point, scan.width)
                    counts[_cell_index(x, y, width=scan.width, height=scan.height, cols=cols, rows=rows)] += 1
                ownership.append(counts)
                centre = component["centre"]
                centres.append(centre)
                # Pixel ownership dominates. Centre proximity is only a stable tie breaker.
                component_scores: list[int] = []
                for cell in range(expected):
                    row, col = divmod(cell, cols)
                    cell_centre_x = (col + 0.5) * scan.width / cols
                    cell_centre_y = (row + 0.5) * scan.height / rows
                    distance = abs(centre[0] - cell_centre_x) + abs(centre[1] - cell_centre_y)
                    tie_break = max(0, int((scan.width + scan.height) * 2 - distance))
                    component_scores.append(counts[cell] * 10000 + tie_break)
                scores.append(component_scores)
            assignment = _maximum_weight_assignment(scores)
            ordered: list[dict[str, object] | None] = [None] * expected
            placements: list[dict[str, object] | None] = [None] * expected
            for component_index, cell in enumerate(assignment):
                component = components[component_index]
                area = int(component["area"])
                owned = ownership[component_index][cell]
                ratio = owned / area if area else 0.0
                if owned == 0 or ratio <= 0.5:
                    raise RecoveryIncomplete({
                        "version": 1, "ok": False, "status": "needs_fallback",
                        "error_code": "cell_assignment_ambiguous",
                        "message": "a component cannot be assigned to a source cell with majority pixel ownership",
                        "component_index": component_index, "assigned_cell": [cell % cols, cell // cols],
                        "ownership_ratio": ratio,
                    })
                ordered[cell] = component
                placements[cell] = {
                    "source_component": component_index,
                    "source_bbox": component["bbox"], "source_area": area,
                    "source_centre": centres[component_index],
                    "target_cell": [cell % cols, cell // cols],
                    "source_cell_ownership_pixels": owned,
                    "source_cell_ownership_ratio": ratio,
                }
            if any(component is None for component in ordered):
                raise RecoveryError("component assignment did not fill every target cell")

            original_cell_w = (scan.width + cols - 1) // cols
            original_cell_h = (scan.height + rows - 1) // rows
            max_width = max(int(component["bbox"][2]) - int(component["bbox"][0]) for component in ordered if component)
            max_height = max(int(component["bbox"][3]) - int(component["bbox"][1]) for component in ordered if component)
            cell_w = max(original_cell_w, max_width + padding * 2)
            cell_h = max(original_cell_h, max_height + padding * 2)
            recovered = Image.new("RGBA", (cell_w * cols, cell_h * rows), (0, 0, 0, 0))
            try:
                for target, component in enumerate(ordered):
                    assert component is not None
                    left, top, right, bottom = component["bbox"]
                    crop = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
                    for point in component["pixels"]:
                        y, x = divmod(point, scan.width)
                        crop.putpixel((x - left, y - top), scan.getpixel((x, y)))
                    row, col = divmod(target, cols)
                    x = col * cell_w + (cell_w - crop.width) // 2
                    y = row * cell_h + (cell_h - crop.height) // 2
                    recovered.alpha_composite(crop, (x, y))
                    assert placements[target] is not None
                    placements[target]["paste_position"] = [x, y]
                output.parent.mkdir(parents=True, exist_ok=True)
                recovered.save(output)
            finally:
                recovered.close()
            return {
                "version": 1, "ok": True, "status": "recovered",
                "method": "whole_sheet_8_connected_components",
                "ordering_method": "foreground_ownership_then_centre_distance",
                "source_path": str(source), "output_path": str(output), "background": background,
                "cleanup": cleanup, "grid": {"cols": cols, "rows": rows},
                "min_component_area": min_component_area, "padding": padding,
                "component_count": len(components), "original_size": list(scan.size),
                "recovered_size": [cell_w * cols, cell_h * rows],
                "recovered_cell_size": [cell_w, cell_h], "placements": placements,
            }
        finally:
            scan.close()
    finally:
        image.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover a fixed-grid sheet from 8-connected image components")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--grid", required=True)
    parser.add_argument("--background", choices=["transparent", "magenta"], default="magenta")
    parser.add_argument("--min-component-area", type=int, default=100)
    parser.add_argument("--padding", type=int, default=8)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        cols, rows = _parse_grid(args.grid)
        if args.min_component_area < 1:
            raise RecoveryError("--min-component-area must be positive")
        if args.padding < 0:
            raise RecoveryError("--padding cannot be negative")
        result = _recover(args.source, args.output, cols=cols, rows=rows, background=args.background,
                          min_component_area=args.min_component_area, padding=args.padding)
        result["report"] = str(args.report)
        _write_json(args.report, result)
        print(json.dumps(result))
        return 0
    except RecoveryIncomplete as exc:
        result = {**exc.report, "source_path": str(args.source), "output_path": str(args.output), "report": str(args.report)}
        _write_json(args.report, result)
        print(json.dumps(result))
        return 2
    except RecoveryError as exc:
        result = {"version": 1, "ok": False, "status": "error", "error_code": "invalid_input", "message": str(exc), "report": str(args.report)}
        _write_json(args.report, result)
        print(json.dumps(result))
        return 1


if __name__ == "__main__":
    sys.exit(main())
