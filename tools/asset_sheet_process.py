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


def _parse_names(value: str | None, total: int) -> list[str]:
    if value is None:
        return [f"{index + 1:02d}" for index in range(total)]
    names = [name.strip() for name in value.split(",")]
    if any(not name for name in names):
        raise SheetProcessError("--names cannot contain empty names")
    if len(names) != total:
        raise SheetProcessError(f"--names has {len(names)} entries, grid has {total} cells")
    for name in names:
        if not SAFE_NAME_RE.fullmatch(name) or name in {".", ".."}:
            raise SheetProcessError("--names entries must be safe file names")
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

    for x in range(width):
        for y in range(height):
            red, green, blue, alpha = pixels[x, y]
            if alpha > 0 and _color_distance((red, green, blue)) < threshold:
                pixels[x, y] = (0, 0, 0, 0)
                removed += 1

    visited: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()
    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if (x, y) in visited or x < 0 or x >= width or y < 0 or y >= height:
            continue
        visited.add((x, y))
        red, green, blue, alpha = pixels[x, y]
        should_expand = alpha == 0
        if alpha > 0 and _color_distance((red, green, blue)) < edge_threshold:
            pixels[x, y] = (0, 0, 0, 0)
            edge_removed += 1
            should_expand = True
        if should_expand:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    next_pixel = (x + dx, y + dy)
                    if next_pixel not in visited:
                        queue.append(next_pixel)

    return converted, {"removed_pixels": removed, "edge_removed_pixels": edge_removed}


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


def process_sheet(
    source: Path,
    output_dir: Path,
    *,
    grid: str,
    names: str | None = None,
    asset_id: str | None = None,
    tag: str | None = None,
    padding: int = 0,
    reject_edge_touch: bool = False,
    background: str = "transparent",
    magenta_threshold: int = 100,
    magenta_edge_threshold: int = 150,
    component_mode: str = "all",
    component_padding: int | None = None,
    min_component_area: int = 1,
    trim_border: int = 0,
    edge_clean_depth: int = 0,
    edge_touch_margin: int = 0,
    report: Path | None = None,
) -> dict[str, object]:
    """Split a production-shaped grid sheet into cropped per-cell PNGs."""
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

    cols, rows = _parse_grid(grid)
    total = cols * rows
    cell_names = _parse_names(names, total)

    if background not in {"transparent", "magenta"}:
        raise SheetProcessError("--background must be transparent or magenta")
    if component_mode not in COMPONENT_MODES:
        raise SheetProcessError("--component-mode must be all or largest")
    for name, value in {
        "--component-padding": component_padding,
        "--min-component-area": min_component_area,
        "--trim-border": trim_border,
        "--edge-clean-depth": edge_clean_depth,
        "--edge-touch-margin": edge_touch_margin,
    }.items():
        if value is not None and value < 0:
            raise SheetProcessError(f"{name} must be zero or positive")

    image = Image.open(source).convert("RGBA")
    try:
        cleanup: dict[str, object] = {
            "background": background,
            "magenta_threshold": magenta_threshold if background == "magenta" else None,
            "magenta_edge_threshold": magenta_edge_threshold if background == "magenta" else None,
            "removed_pixels": 0,
            "edge_removed_pixels": 0,
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
        if width % cols != 0 or height % rows != 0:
            raise SheetProcessError("Source dimensions must divide evenly by grid")
        cell_w = width // cols
        cell_h = height // rows
        output_dir.mkdir(parents=True, exist_ok=True)

        accepted: list[dict[str, object]] = []
        rejected: list[dict[str, object]] = []

        for index, name in enumerate(cell_names):
            row, col = divmod(index, cols)
            left = col * cell_w
            top = row * cell_h
            cell = image.crop((left, top, left + cell_w, top + cell_h))
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
                "source_box": [left, top, left + cell_w, top + cell_h],
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
            cropped = cell.crop(crop_bbox)
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
    finally:
        image.close()

    result: dict[str, object] = {
        "version": 1,
        "ok": True,
        "asset_id": asset_id,
        "tag": tag,
        "source": str(source),
        "source_path": str(source),
        "strategy": "solid_background_grid" if background == "magenta" else "transparent_grid",
        "status": "candidate_extracted" if accepted else "needs_regeneration",
        "background": background,
        "cleanup": cleanup,
        "component_mode": component_mode,
        "component_padding": padding if component_padding is None else component_padding,
        "min_component_area": min_component_area,
        "trim_border": trim_border,
        "edge_clean_depth": edge_clean_depth,
        "edge_touch_margin": edge_touch_margin,
        "grid": {"cols": cols, "rows": rows},
        "cell_size": [cell_w, cell_h],
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
    }
    if report is not None:
        _atomic_write_json(Path(report), result)
        result["report"] = str(report)
    return result


def _main() -> int:
    parser = argparse.ArgumentParser(description="Process a production-shaped 2D asset sheet")
    parser.add_argument("--source", required=True, help="Source sheet image path")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument("--grid", required=True, help="Grid layout, e.g. 2x2")
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
        default=100,
        help="Euclidean RGB distance for #FF00FF cleanup",
    )
    parser.add_argument(
        "--magenta-edge-threshold",
        type=int,
        default=150,
        help="Euclidean RGB distance for edge-connected #FF00FF fringe cleanup",
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
    parser.add_argument("--report", default=None, help="Optional JSON report path")
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
            component_mode=args.component_mode,
            component_padding=args.component_padding,
            min_component_area=args.min_component_area,
            trim_border=args.trim_border,
            edge_clean_depth=args.edge_clean_depth,
            edge_touch_margin=args.edge_touch_margin,
            report=Path(args.report) if args.report else None,
        )
    except SheetProcessError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
