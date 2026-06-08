#!/usr/bin/env python3
"""Create a layout-only guide for image-generation sheets."""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
BACKGROUND_COLORS = {
    "magenta": (255, 0, 255, 255),
    "dark": (18, 24, 36, 255),
    "white": (255, 255, 255, 255),
}


class LayoutGuideError(Exception):
    """Raised when a layout guide cannot be created."""


def _parse_labels(raw: str | None, total: int) -> list[str]:
    if raw is None:
        return []
    labels = [item.strip() for item in raw.split(",")]
    if len(labels) != total:
        raise LayoutGuideError(f"--labels has {len(labels)} entries, expected {total}")
    for label in labels:
        if label and (not SAFE_NAME_RE.fullmatch(label) or label in {".", ".."}):
            raise LayoutGuideError("--labels entries must be safe names")
    return labels


def _write_atomic_image(path: Path, image: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=str(path.parent), suffix=".png") as handle:
        tmp_path = Path(handle.name)
    try:
        image.save(tmp_path)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def create_layout_guide(
    out: Path,
    *,
    rows: int,
    cols: int,
    cell_width: int = 384,
    cell_height: int = 384,
    safe_ratio: float = 0.65,
    background: str = "magenta",
    labels: list[str] | None = None,
) -> dict[str, object]:
    """Create a layout guide PNG and return its metadata."""
    if rows <= 0 or cols <= 0:
        raise LayoutGuideError("--rows and --cols must be positive")
    if cell_width <= 0 or cell_height <= 0:
        raise LayoutGuideError("--cell-width and --cell-height must be positive")
    if not 0 < safe_ratio <= 1:
        raise LayoutGuideError("--safe-ratio must be greater than 0 and at most 1")
    if background not in BACKGROUND_COLORS:
        raise LayoutGuideError(f"--background must be one of: {', '.join(sorted(BACKGROUND_COLORS))}")

    total = rows * cols
    clean_labels = labels or []
    if clean_labels and len(clean_labels) != total:
        raise LayoutGuideError("labels length must match rows * cols")

    width = cols * cell_width
    height = rows * cell_height
    image = Image.new("RGBA", (width, height), BACKGROUND_COLORS[background])
    draw = ImageDraw.Draw(image)
    grid_color = (0, 0, 0, 180) if background != "dark" else (255, 255, 255, 170)
    safe_color = (255, 255, 255, 210) if background != "white" else (0, 0, 0, 190)
    center_color = (40, 180, 255, 220)
    text_color = (255, 255, 255, 235) if background == "dark" else (0, 0, 0, 220)
    font = ImageFont.load_default()

    safe_width = int(cell_width * safe_ratio)
    safe_height = int(cell_height * safe_ratio)
    safe_margin_x = (cell_width - safe_width) // 2
    safe_margin_y = (cell_height - safe_height) // 2

    for row in range(rows):
        for col in range(cols):
            index = row * cols + col
            left = col * cell_width
            top = row * cell_height
            right = left + cell_width
            bottom = top + cell_height
            draw.rectangle((left, top, right - 1, bottom - 1), outline=grid_color, width=3)

            safe_left = left + safe_margin_x
            safe_top = top + safe_margin_y
            safe_right = safe_left + safe_width
            safe_bottom = safe_top + safe_height
            draw.rectangle((safe_left, safe_top, safe_right, safe_bottom), outline=safe_color, width=2)

            center_x = left + cell_width // 2
            center_y = top + cell_height // 2
            draw.line((center_x, safe_top, center_x, safe_bottom), fill=center_color, width=1)
            draw.line((safe_left, center_y, safe_right, center_y), fill=center_color, width=1)

            label = clean_labels[index] if clean_labels else f"{index + 1:02d}"
            draw.text((left + 10, top + 10), label, fill=text_color, font=font)

    _write_atomic_image(out, image)
    return {
        "ok": True,
        "path": str(out),
        "rows": rows,
        "cols": cols,
        "cell_width": cell_width,
        "cell_height": cell_height,
        "canvas_width": width,
        "canvas_height": height,
        "safe_ratio": safe_ratio,
        "background": background,
        "labels": clean_labels,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Create a layout-only guide for image-generation sheets")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rows", required=True, type=int)
    parser.add_argument("--cols", required=True, type=int)
    parser.add_argument("--cell-width", type=int, default=384)
    parser.add_argument("--cell-height", type=int, default=384)
    parser.add_argument("--safe-ratio", type=float, default=0.65)
    parser.add_argument("--background", choices=sorted(BACKGROUND_COLORS), default="magenta")
    parser.add_argument("--labels")
    args = parser.parse_args()

    try:
        labels = _parse_labels(args.labels, args.rows * args.cols)
        result = create_layout_guide(
            args.out,
            rows=args.rows,
            cols=args.cols,
            cell_width=args.cell_width,
            cell_height=args.cell_height,
            safe_ratio=args.safe_ratio,
            background=args.background,
            labels=labels,
        )
    except LayoutGuideError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
