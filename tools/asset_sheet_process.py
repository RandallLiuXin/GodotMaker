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
            bbox = _alpha_bbox(cell)
            base = {
                "name": name,
                "candidate_id": f"{asset_id or source.stem}.{name}",
                "state": "candidate",
                "index": index,
                "grid": [col, row],
                "source_box": [left, top, left + cell_w, top + cell_h],
            }
            if bbox is None:
                rejected.append({**base, "state": "rejected", "reason": "empty_cell"})
                continue

            touches_edge = _edge_touch(bbox, width=cell_w, height=cell_h)
            if touches_edge and reject_edge_touch:
                rejected.append({
                    **base,
                    "state": "rejected",
                    "reason": "edge_touch",
                    "crop_bbox": list(bbox),
                })
                continue

            crop_bbox = _padded_bbox(bbox, width=cell_w, height=cell_h, padding=padding)
            cropped = cell.crop(crop_bbox)
            path = output_dir / f"{name}.png"
            cropped.save(path)
            accepted.append({
                **base,
                "path": str(path),
                "crop_bbox": list(bbox),
                "padded_crop_bbox": list(crop_bbox),
                "edge_touch": touches_edge,
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
            report=Path(args.report) if args.report else None,
        )
    except SheetProcessError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
