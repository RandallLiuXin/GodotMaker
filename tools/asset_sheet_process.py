#!/usr/bin/env python3
"""Process a production-shaped 2D asset sheet."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
from collections import deque
from pathlib import Path


class SheetProcessError(Exception):
    """Raised when a source sheet cannot be processed."""


SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
MAGENTA_RGB = (255, 0, 255)
COMPONENT_MODES = {"all", "largest"}
SNAP_MODES = {"grid", "autoslice"}
MAGENTA_MATTE_MAX_PASSES = 8
MAGENTA_MATTE_SEARCH_RADIUS = 3
MAGENTA_COMPOSITE_RESIDUAL = 12
MAGENTA_COMPOSITE_RATIO_SPREAD = 0.16


def _parse_grid(value: str) -> tuple[int, int]:
    raw = value.lower().strip()
    if "x" not in raw:
        raise SheetProcessError("--grid must use COLSxROWS")
    left, right = raw.split("x", 1)
    try:
        cols = int(left)
        rows = int(right)
    except ValueError as exc:
        raise SheetProcessError("--grid must use integer dimensions") from exc
    if cols <= 0 or rows <= 0:
        raise SheetProcessError("--grid dimensions must be positive")
    return cols, rows


def _parse_name_values(value: str | None) -> list[str] | None:
    if value is None:
        return None
    names = [name.strip() for name in value.split(",")]
    if any(not name for name in names):
        raise SheetProcessError("--names cannot contain empty names")
    for name in names:
        if not SAFE_NAME_RE.fullmatch(name) or name in {".", ".."}:
            raise SheetProcessError("--names entries must be safe file names")
    return names


def _parse_names(value: str | None, total: int, *, subject: str = "grid cells") -> list[str]:
    names = _parse_name_values(value)
    if names is None:
        return [f"{index + 1:02d}" for index in range(total)]
    if len(names) != total:
        raise SheetProcessError(
            f"--names has {len(names)} entries, detected {subject} has {total} entries"
        )
    return names


def _alpha_bbox(image) -> tuple[int, int, int, int] | None:
    alpha = image.getchannel("A")
    return alpha.getbbox()


def _has_transparent_pixels(image) -> bool:
    alpha = image.getchannel("A")
    extrema = alpha.getextrema()
    return extrema[0] < 255


def _color_distance(rgb: tuple[int, int, int], target: tuple[int, int, int] = MAGENTA_RGB) -> float:
    red, green, blue = rgb
    target_red, target_green, target_blue = target
    return math.sqrt(
        (red - target_red) ** 2
        + (green - target_green) ** 2
        + (blue - target_blue) ** 2
    )


def _remove_magenta_background(
    image,
    *,
    threshold: int,
    edge_threshold: int,
) -> tuple[object, dict[str, int]]:
    if threshold < 0:
        raise SheetProcessError("--magenta-threshold must be zero or positive")
    if edge_threshold < 0:
        raise SheetProcessError("--magenta-edge-threshold must be zero or positive")
    converted = image.convert("RGBA")
    pixels = converted.load()
    removed = 0
    edge_removed = 0
    width, height = converted.size
    original = list(converted.get_flattened_data())

    # A colour-distance test can safely clear only the strict key radius.  Do
    # not extend an exterior fill through a locally smooth path: a blurred
    # violet foreground creates the same path and would be erased wholesale.
    # The broader edge threshold is reserved exclusively for the compositing
    # validation below, where an actual foreground colour is available.
    background = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if x < 0 or x >= width or y < 0 or y >= height:
            continue
        index = y * width + x
        if background[index]:
            continue
        red, green, blue, alpha = original[index]
        rgb = (red, green, blue)
        if alpha > 0 and _color_distance(rgb) > threshold:
            continue
        background[index] = 1
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx or dy:
                    queue.append((x + dx, y + dy))

    for y in range(height):
        for x in range(width):
            index = y * width + x
            if not background[index]:
                continue
            red, green, blue, alpha = original[index]
            if alpha == 0:
                continue
            edge_removed += 1
            pixels[x, y] = (0, 0, 0, 0)

    # Enclosed strict-key holes are intentionally removed, but never become
    # flood-fill seeds.  This keeps a magenta window transparent without
    # letting its neighbourhood consume a soft-edged foreground.
    for y in range(height):
        for x in range(width):
            index = y * width + x
            if background[index]:
                continue
            red, green, blue, alpha = original[index]
            if alpha > 0 and _color_distance((red, green, blue)) <= threshold:
                pixels[x, y] = (0, 0, 0, 0)
                removed += 1

    # Decontaminate soft edges from the outside in.  Every pass observes the
    # previous pass's reduced alpha, allowing a two- or three-pixel composite
    # ramp to expose the real foreground colour before the outer layer is
    # revisited.  Fits always use the original input pixel, so alpha is not
    # compounded between passes.
    edge_spill_pixels: set[tuple[int, int]] = set()
    frontier: set[tuple[int, int]] = set()
    for y in range(height):
        for x in range(width):
            if pixels[x, y][3] == 0:
                continue
            if any(
                pixels[x + dx, y + dy][3] < pixels[x, y][3]
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                if (dx or dy) and 0 <= x + dx < width and 0 <= y + dy < height
            ):
                frontier.add((x, y))

    for _ in range(MAGENTA_MATTE_MAX_PASSES):
        updates: list[tuple[int, int, tuple[int, int, int], int]] = []
        for x, y in frontier:
            index = y * width + x
            red, green, blue, original_alpha = original[index]
            current_alpha = pixels[x, y][3]
            distance = _color_distance((red, green, blue))
            if original_alpha == 0 or current_alpha == 0 or distance > edge_threshold:
                continue
            neighbours = [
                pixels[x + dx, y + dy]
                for dx in range(-MAGENTA_MATTE_SEARCH_RADIUS, MAGENTA_MATTE_SEARCH_RADIUS + 1)
                for dy in range(-MAGENTA_MATTE_SEARCH_RADIUS, MAGENTA_MATTE_SEARCH_RADIUS + 1)
                if (dx or dy) and 0 <= x + dx < width and 0 <= y + dy < height
            ]
            if not any(item[3] < current_alpha for item in neighbours):
                continue
            best: tuple[tuple[int, int, int], int, float] | None = None
            for neighbour_red, neighbour_green, neighbour_blue, neighbour_alpha in neighbours:
                foreground = (neighbour_red, neighbour_green, neighbour_blue)
                if neighbour_alpha == 0 or _color_distance(foreground) <= distance + 8:
                    continue
                matte_alpha = _magenta_composite_alpha((red, green, blue), foreground)
                if matte_alpha is None:
                    continue
                residual = _magenta_composite_residual(
                    (red, green, blue), foreground, matte_alpha
                )
                if residual > MAGENTA_COMPOSITE_RESIDUAL:
                    continue
                output_alpha = round(original_alpha * matte_alpha)
                if output_alpha >= current_alpha:
                    continue
                if best is None or output_alpha < best[1] or (
                    output_alpha == best[1] and residual < best[2]
                ):
                    best = (foreground, output_alpha, residual)
            if best is not None:
                foreground, output_alpha, _ = best
                updates.append((x, y, foreground, output_alpha))
        if not updates:
            break
        frontier = set()
        for x, y, foreground, output_alpha in updates:
            pixels[x, y] = (*foreground, output_alpha)
            edge_spill_pixels.add((x, y))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    next_x, next_y = x + dx, y + dy
                    if 0 <= next_x < width and 0 <= next_y < height:
                        frontier.add((next_x, next_y))

    return converted, {
        "removed_pixels": removed,
        "edge_removed_pixels": edge_removed,
        "edge_spill_pixels": len(edge_spill_pixels),
    }


def _magenta_composite_alpha(
    pixel: tuple[int, int, int], foreground: tuple[int, int, int]
) -> float | None:
    """Return a consistent foreground coverage for ``pixel`` over magenta."""
    ratios: list[float] = []
    for value, foreground_value, key_value in zip(pixel, foreground, MAGENTA_RGB):
        denominator = foreground_value - key_value
        if abs(denominator) >= 8:
            ratios.append((value - key_value) / denominator)
    if not ratios:
        return None
    coverage = sum(ratios) / len(ratios)
    if not 0.05 <= coverage <= 0.95:
        return None
    if len(ratios) > 1 and max(ratios) - min(ratios) > MAGENTA_COMPOSITE_RATIO_SPREAD:
        return None
    return coverage


def _magenta_composite_residual(
    pixel: tuple[int, int, int], foreground: tuple[int, int, int], coverage: float
) -> float:
    return max(
        abs(value - round(key_value + coverage * (foreground_value - key_value)))
        for value, foreground_value, key_value in zip(pixel, foreground, MAGENTA_RGB)
    )


def _trim_border(image, *, pixels: int):
    if pixels <= 0:
        return image
    width, height = image.size
    if width <= pixels * 2 or height <= pixels * 2:
        return image
    return image.crop((pixels, pixels, width - pixels, height - pixels))


def _clean_edge_noise(image, *, depth: int):
    if depth <= 0:
        return image
    cleaned = image.copy()
    pixels = cleaned.load()
    width, height = cleaned.size
    for offset in range(depth):
        for x in range(width):
            for y in (offset, height - 1 - offset):
                if 0 <= y < height:
                    red, green, blue, alpha = pixels[x, y]
                    if alpha > 0 and (
                        (red < 40 and green < 40 and blue < 40)
                        or _color_distance((red, green, blue)) < 150
                    ):
                        pixels[x, y] = (0, 0, 0, 0)
        for y in range(height):
            for x in (offset, width - 1 - offset):
                if 0 <= x < width:
                    red, green, blue, alpha = pixels[x, y]
                    if alpha > 0 and (
                        (red < 40 and green < 40 and blue < 40)
                        or _color_distance((red, green, blue)) < 150
                    ):
                        pixels[x, y] = (0, 0, 0, 0)
    return cleaned


def _connected_components(image, *, min_area: int) -> list[dict[str, object]]:
    alpha = image.getchannel("A")
    pixels = alpha.load()
    width, height = image.size
    visited = [[False] * width for _ in range(height)]
    components: list[dict[str, object]] = []

    for y in range(height):
        for x in range(width):
            if pixels[x, y] == 0 or visited[y][x]:
                continue
            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited[y][x] = True
            coords: list[tuple[int, int]] = []
            min_x = max_x = x
            min_y = max_y = y
            touches_edge = x == 0 or y == 0 or x == width - 1 or y == height - 1

            while queue:
                cx, cy = queue.popleft()
                coords.append((cx, cy))
                min_x = min(min_x, cx)
                min_y = min(min_y, cy)
                max_x = max(max_x, cx)
                max_y = max(max_y, cy)
                if cx == 0 or cy == 0 or cx == width - 1 or cy == height - 1:
                    touches_edge = True
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx = cx + dx
                    ny = cy + dy
                    if (
                        0 <= nx < width
                        and 0 <= ny < height
                        and pixels[nx, ny] > 0
                        and not visited[ny][nx]
                    ):
                        visited[ny][nx] = True
                        queue.append((nx, ny))

            if len(coords) >= min_area:
                components.append({
                    "area": len(coords),
                    "bbox": (min_x, min_y, max_x + 1, max_y + 1),
                    "touches_edge": touches_edge,
                    "coords": coords,
                })

    components.sort(key=lambda item: int(item["area"]), reverse=True)
    return components


def _mask_to_component(image, component: dict[str, object]):
    selected = image.copy()
    selected.paste((0, 0, 0, 0), (0, 0, selected.width, selected.height))
    source_pixels = image.load()
    target_pixels = selected.load()
    for x, y in component["coords"]:  # type: ignore[index]
        target_pixels[x, y] = source_pixels[x, y]
    return selected


def _padded_bbox(
    bbox: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    padding: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def _edge_touch(bbox: tuple[int, int, int, int], *, width: int, height: int) -> bool:
    left, top, right, bottom = bbox
    return left <= 0 or top <= 0 or right >= width or bottom >= height


def _bbox_touches_margin(
    bbox: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    margin: int,
) -> bool:
    left, top, right, bottom = bbox
    return left <= margin or top <= margin or right >= width - margin or bottom >= height - margin


def _rect_has_point(
    rect: tuple[int, int, int, int],
    point: tuple[int, int],
    *,
    grow: float,
) -> bool:
    left, top, right, bottom = rect
    x, y = point
    return left - grow <= x < right + grow and top - grow <= y < bottom + grow


def _rect_intersects(
    left_rect: tuple[int, int, int, int],
    right_rect: tuple[int, int, int, int],
    *,
    grow: float,
) -> bool:
    left_a, top_a, right_a, bottom_a = left_rect
    left_b, top_b, right_b, bottom_b = right_rect
    return (
        left_a - grow < right_b
        and right_a + grow > left_b
        and top_a - grow < bottom_b
        and bottom_a + grow > top_b
    )


def _expand_rect_to_point(
    rect: tuple[int, int, int, int],
    point: tuple[int, int],
) -> tuple[int, int, int, int]:
    left, top, right, bottom = rect
    x, y = point
    return min(left, x), min(top, y), max(right, x + 1), max(bottom, y + 1)


def _merge_rects(
    left_rect: tuple[int, int, int, int],
    right_rect: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    left_a, top_a, right_a, bottom_a = left_rect
    left_b, top_b, right_b, bottom_b = right_rect
    return (
        min(left_a, left_b),
        min(top_a, top_b),
        max(right_a, right_b),
        max(bottom_a, bottom_b),
    )


def _autoslice_rects(image) -> list[tuple[int, int, int, int]]:
    alpha = image.getchannel("A")
    pixels = alpha.load()
    width, height = image.size
    rects: list[tuple[int, int, int, int]] = []

    for y in range(height):
        for x in range(width):
            if pixels[x, y] == 0:
                continue
            found_index = None
            for index, rect in enumerate(rects):
                if _rect_has_point(rect, (x, y), grow=1.5):
                    found_index = index
                    break
            if found_index is None:
                rects.append((x, y, x + 1, y + 1))
                continue

            rects[found_index] = _expand_rect_to_point(rects[found_index], (x, y))
            merged = True
            while merged:
                merged = False
                base = rects[found_index]
                for index, rect in enumerate(rects):
                    if index == found_index:
                        continue
                    if _rect_intersects(base, rect, grow=1):
                        rects[found_index] = _merge_rects(base, rect)
                        del rects[index]
                        if index < found_index:
                            found_index -= 1
                        merged = True
                        break

    rects.sort(key=lambda rect: (rect[1], rect[0]))
    return rects


def _rect_alpha_area(image, rect: tuple[int, int, int, int]) -> int:
    return sum(image.getchannel("A").crop(rect).histogram()[1:])


def _atomic_write_json(path: Path, data: dict[str, object]) -> None:
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


def _atomic_save_png(image, path: Path) -> None:
    """Save a processed RGBA sheet without leaving a partial evidence file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(path.parent),
        suffix=".png",
    ) as handle:
        tmp_path = Path(handle.name)
    try:
        image.save(tmp_path, format="PNG")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def process_sheet(
    source: Path,
    output_dir: Path,
    *,
    grid: str | None = None,
    snap_mode: str,
    names: str | None = None,
    asset_id: str | None = None,
    tag: str | None = None,
    padding: int = 0,
    reject_edge_touch: bool = False,
    background: str = "transparent",
    magenta_threshold: int = 60,
    magenta_edge_threshold: int = 220,
    component_mode: str = "all",
    component_padding: int | None = None,
    min_component_area: int = 1,
    trim_border: int = 0,
    edge_clean_depth: int = 0,
    edge_touch_margin: int = 0,
    preserve_cell_bounds: bool = False,
    processed_out: Path | None = None,
    report: Path | None = None,
) -> dict[str, object]:
    """Extract fixed grid cells or independent autoslice regions."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise SheetProcessError("Pillow is required to process asset sheets") from exc

    source = Path(source)
    output_dir = Path(output_dir)
    if not source.exists():
        raise SheetProcessError(f"Source sheet not found: {source}")
    if not source.is_file():
        raise SheetProcessError(f"Source sheet is not a file: {source}")
    if padding < 0:
        raise SheetProcessError("--padding must be zero or positive")

    if background not in {"transparent", "magenta"}:
        raise SheetProcessError("--background must be transparent or magenta")
    if snap_mode not in SNAP_MODES:
        raise SheetProcessError("--snap-mode must be grid or autoslice")
    if snap_mode == "grid" and grid is None:
        raise SheetProcessError("--grid is required with --snap-mode grid")
    if snap_mode == "autoslice" and grid is not None:
        raise SheetProcessError("--grid is not accepted with --snap-mode autoslice")
    if preserve_cell_bounds and snap_mode != "grid":
        raise SheetProcessError("--preserve-cell-bounds requires --snap-mode grid")
    if component_mode not in COMPONENT_MODES:
        raise SheetProcessError("--component-mode must be all or largest")
    if snap_mode == "autoslice" and component_mode != "all":
        raise SheetProcessError("--component-mode is only configurable with --snap-mode grid")
    for name, value in {
        "--component-padding": component_padding,
        "--min-component-area": min_component_area,
        "--trim-border": trim_border,
        "--edge-clean-depth": edge_clean_depth,
        "--edge-touch-margin": edge_touch_margin,
    }.items():
        if value is not None and value < 0:
            raise SheetProcessError(f"{name} must be zero or positive")

    cols: int | None = None
    rows: int | None = None
    cell_names: list[str] | None = None
    requested_names = _parse_name_values(names)
    if snap_mode == "grid":
        cols, rows = _parse_grid(grid or "")
        cell_names = _parse_names(names, cols * rows)

    image = Image.open(source).convert("RGBA")
    try:
        cleanup: dict[str, object] = {
            "background": background,
            "magenta_threshold": magenta_threshold if background == "magenta" else None,
            "magenta_edge_threshold": magenta_edge_threshold if background == "magenta" else None,
            "removed_pixels": 0,
            "edge_removed_pixels": 0,
            "edge_spill_pixels": 0,
        }
        if background == "magenta":
            image, cleanup_counts = _remove_magenta_background(
                image,
                threshold=magenta_threshold,
                edge_threshold=magenta_edge_threshold,
            )
            cleanup.update(cleanup_counts)
        width, height = image.size
        if not _has_transparent_pixels(image):
            raise SheetProcessError("Source sheet must have transparency after background cleanup")
        column_edges: list[int] | None = None
        row_edges: list[int] | None = None
        cell_w: int | None = None
        cell_h: int | None = None
        if snap_mode == "grid":
            assert cols is not None and rows is not None
            column_edges = [(width * index) // cols for index in range(cols + 1)]
            row_edges = [(height * index) // rows for index in range(rows + 1)]
            cell_w = width // cols
            cell_h = height // rows
        output_dir.mkdir(parents=True, exist_ok=True)

        accepted: list[dict[str, object]] = []
        rejected: list[dict[str, object]] = []
        detected_regions: list[dict[str, object]] = []
        discarded_regions: list[dict[str, object]] = []
        name_count_mismatch = False

        if snap_mode == "autoslice":
            for rect in _autoslice_rects(image):
                alpha_area = _rect_alpha_area(image, rect)
                region = {"bbox": list(rect), "alpha_area": alpha_area}
                if alpha_area < min_component_area:
                    discarded_regions.append({**region, "reason": "below_min_component_area"})
                else:
                    detected_regions.append(region)

            if requested_names is not None and len(requested_names) != len(detected_regions):
                name_count_mismatch = True
                rejected.append({
                    "state": "rejected",
                    "reason": "name_count_mismatch",
                    "expected_count": len(requested_names),
                    "detected_count": len(detected_regions),
                })
            else:
                region_names = requested_names or [
                    f"{index + 1:02d}" for index in range(len(detected_regions))
                ]
                for index, (name, region) in enumerate(zip(region_names, detected_regions)):
                    bbox = tuple(region["bbox"])
                    base = {
                        "name": name,
                        "candidate_id": f"{asset_id or source.stem}.{name}",
                        "state": "candidate",
                        "index": index,
                        "grid": None,
                        "source_box": list(bbox),
                        "component_mode": "all",
                        "component_count": 1,
                        "selected_component_area": region["alpha_area"],
                        "selected_component_bbox": list(bbox),
                    }
                    touches_edge = _bbox_touches_margin(
                        bbox,
                        width=width,
                        height=height,
                        margin=edge_touch_margin,
                    )
                    if touches_edge and reject_edge_touch:
                        rejected.append({
                            **base,
                            "state": "rejected",
                            "reason": "edge_touch",
                            "crop_bbox": list(bbox),
                        })
                        continue

                    crop_bbox = _padded_bbox(
                        bbox,
                        width=width,
                        height=height,
                        padding=padding if component_padding is None else component_padding,
                    )
                    cropped = image.crop(crop_bbox)
                    path = output_dir / f"{name}.png"
                    cropped.save(path)
                    accepted.append({
                        **base,
                        "path": str(path),
                        "crop_bbox": list(bbox),
                        "padded_crop_bbox": list(crop_bbox),
                        "edge_touch": touches_edge,
                        "trim_border": trim_border,
                        "edge_clean_depth": edge_clean_depth,
                        "edge_touch_margin": edge_touch_margin,
                        "width": cropped.size[0],
                        "height": cropped.size[1],
                    })
        else:
            assert cols is not None and column_edges is not None and row_edges is not None
            for index, name in enumerate(cell_names or []):
                row, col = divmod(index, cols)
                left = column_edges[col]
                top = row_edges[row]
                right = column_edges[col + 1]
                bottom = row_edges[row + 1]
                cell = image.crop((left, top, right, bottom))
                cell = _trim_border(cell, pixels=trim_border)
                cell = _clean_edge_noise(cell, depth=edge_clean_depth)
                components = _connected_components(cell, min_area=min_component_area)
                selected_component = components[0] if component_mode == "largest" and components else None
                if selected_component is not None:
                    cell = _mask_to_component(cell, selected_component)
                    bbox = tuple(selected_component["bbox"])  # type: ignore[arg-type]
                else:
                    bbox = _alpha_bbox(cell)
                base = {
                    "name": name,
                    "candidate_id": f"{asset_id or source.stem}.{name}",
                    "state": "candidate",
                    "index": index,
                    "grid": [col, row],
                    "source_box": [left, top, right, bottom],
                    "component_mode": component_mode,
                    "component_count": len(components),
                    "selected_component_area": (
                        int(selected_component["area"]) if selected_component else None
                    ),
                    "selected_component_bbox": (
                        list(selected_component["bbox"]) if selected_component else None
                    ),
                }
                if bbox is None:
                    rejected.append({**base, "state": "rejected", "reason": "empty_cell"})
                    continue

                touches_edge = _bbox_touches_margin(
                    bbox,
                    width=cell.width,
                    height=cell.height,
                    margin=edge_touch_margin,
                )
                if touches_edge and reject_edge_touch:
                    rejected.append({
                        **base,
                        "state": "rejected",
                        "reason": "edge_touch",
                        "crop_bbox": list(bbox),
                    })
                    continue

                crop_bbox = _padded_bbox(
                    bbox,
                    width=cell.width,
                    height=cell.height,
                    padding=padding if component_padding is None else component_padding,
                )
                output_box = (0, 0, cell.width, cell.height) if preserve_cell_bounds else crop_bbox
                cropped = cell.crop(output_box)
                path = output_dir / f"{name}.png"
                cropped.save(path)
                accepted.append({
                    **base,
                    "path": str(path),
                    "crop_bbox": list(bbox),
                    "padded_crop_bbox": list(crop_bbox),
                    "output_box": list(output_box),
                    "preserve_cell_bounds": preserve_cell_bounds,
                    "edge_touch": touches_edge,
                    "trim_border": trim_border,
                    "edge_clean_depth": edge_clean_depth,
                    "edge_touch_margin": edge_touch_margin,
                    "width": cropped.size[0],
                    "height": cropped.size[1],
                })

        # A name-count mismatch means the candidate set cannot be bound to the
        # caller's logical props. Preserve only the report, not a sheet that
        # could be mistaken for a valid transparent source artifact.
        processed_path: str | None = None
        if processed_out is not None and not name_count_mismatch:
            processed_target = Path(processed_out)
            _atomic_save_png(image, processed_target)
            processed_path = str(processed_target)
    finally:
        image.close()

    if snap_mode == "autoslice":
        strategy = "solid_background_autoslice" if background == "magenta" else "transparent_autoslice"
    else:
        strategy = "solid_background_grid" if background == "magenta" else "transparent_grid"

    autoslice_needs_regeneration = snap_mode == "autoslice" and (
        name_count_mismatch or bool(rejected) or not accepted
    )
    result: dict[str, object] = {
        "version": 1,
        "ok": not autoslice_needs_regeneration,
        "asset_id": asset_id,
        "tag": tag,
        "source": str(source),
        "source_path": str(source),
        "strategy": strategy,
        "status": "needs_regeneration" if autoslice_needs_regeneration or not accepted else "candidate_extracted",
        "background": background,
        "cleanup": cleanup,
        "snap_mode": snap_mode,
        "component_mode": component_mode,
        "component_padding": padding if component_padding is None else component_padding,
        "min_component_area": min_component_area,
        "trim_border": trim_border,
        "edge_clean_depth": edge_clean_depth,
        "edge_touch_margin": edge_touch_margin,
        "preserve_cell_bounds": preserve_cell_bounds,
        "grid": {"cols": cols, "rows": rows} if snap_mode == "grid" else None,
        "cell_size": [cell_w, cell_h] if snap_mode == "grid" else None,
        "cell_bounds": (
            {"columns": column_edges, "rows": row_edges}
            if snap_mode == "grid"
            else None
        ),
        "expected_region_count": len(requested_names) if requested_names is not None else None,
        "detected_region_count": len(detected_regions),
        "detected_regions": detected_regions,
        "discarded_regions": discarded_regions,
        "candidates": [
            {
                "candidate_id": f"{asset_id or source.stem}.{item['name']}",
                "name": item["name"],
                "path": item["path"],
                "state": "candidate",
                "bbox": item["source_box"],
                "crop_bbox": item["crop_bbox"],
                "component_count": item["component_count"],
                "selected_component_bbox": item["selected_component_bbox"],
                "selected_component_area": item["selected_component_area"],
                "role": "",
                "final_path": None,
            }
            for item in accepted
        ],
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "edge_touch_candidates": [
            item["candidate_id"] for item in accepted if bool(item.get("edge_touch"))
        ],
        "processed_path": processed_path,
    }
    if report is not None:
        _atomic_write_json(Path(report), result)
        result["report"] = str(report)
    return result


def _main() -> int:
    parser = argparse.ArgumentParser(description="Process a production-shaped 2D asset sheet")
    parser.add_argument("--source", required=True, help="Source sheet image path")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument(
        "--grid",
        default=None,
        help="Grid layout COLSxROWS for --snap-mode grid",
    )
    parser.add_argument("--names", default=None, help="Comma-separated output names")
    parser.add_argument("--asset-id", default=None, help="Optional source asset id")
    parser.add_argument("--tag", default=None, help="Optional current tag")
    parser.add_argument("--padding", type=int, default=0, help="Padding around detected content")
    parser.add_argument("--reject-edge-touch", action="store_true", help="Reject cells touching edges")
    parser.add_argument(
        "--background",
        choices=["transparent", "magenta"],
        default="transparent",
        help="Source background mode",
    )
    parser.add_argument(
        "--magenta-threshold",
        type=int,
        default=60,
        help="Global RGB distance for strict and enclosed #FF00FF background cleanup",
    )
    parser.add_argument(
        "--magenta-edge-threshold",
        type=int,
        default=220,
        help="Maximum RGB distance for locally validated magenta spill cleanup",
    )
    parser.add_argument(
        "--snap-mode",
        choices=sorted(SNAP_MODES),
        required=True,
        help="Use fixed grid cells or independent Godot-style autoslice regions",
    )
    parser.add_argument(
        "--component-mode",
        choices=sorted(COMPONENT_MODES),
        default="all",
        help="Whether to crop all visible pixels or only the largest connected component",
    )
    parser.add_argument(
        "--component-padding",
        type=int,
        default=None,
        help="Padding around the selected component or visible bbox; defaults to --padding",
    )
    parser.add_argument(
        "--min-component-area",
        type=int,
        default=1,
        help="Minimum connected-component area to track",
    )
    parser.add_argument(
        "--trim-border",
        type=int,
        default=0,
        help="Pixels to trim from every cell before component extraction",
    )
    parser.add_argument(
        "--edge-clean-depth",
        type=int,
        default=0,
        help="Cell-edge depth to clear dark or magenta edge noise before component extraction",
    )
    parser.add_argument(
        "--edge-touch-margin",
        type=int,
        default=0,
        help="Additional margin treated as edge touch during component checks",
    )
    parser.add_argument(
        "--preserve-cell-bounds",
        action="store_true",
        help="Keep each accepted grid output at its full fixed cell dimensions",
    )
    parser.add_argument("--report", default=None, help="Optional JSON report path")
    parser.add_argument(
        "--processed-out",
        default=None,
        help="Optional transparent RGBA sheet path written after successful processing",
    )
    args = parser.parse_args()

    try:
        result = process_sheet(
            Path(args.source),
            Path(args.out_dir),
            grid=args.grid,
            names=args.names,
            asset_id=args.asset_id,
            tag=args.tag,
            padding=args.padding,
            reject_edge_touch=args.reject_edge_touch,
            background=args.background,
            magenta_threshold=args.magenta_threshold,
            magenta_edge_threshold=args.magenta_edge_threshold,
            snap_mode=args.snap_mode,
            component_mode=args.component_mode,
            component_padding=args.component_padding,
            min_component_area=args.min_component_area,
            trim_border=args.trim_border,
            edge_clean_depth=args.edge_clean_depth,
            edge_touch_margin=args.edge_touch_margin,
            preserve_cell_bounds=args.preserve_cell_bounds,
            processed_out=Path(args.processed_out) if args.processed_out else None,
            report=Path(args.report) if args.report else None,
        )
    except SheetProcessError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(_main())
