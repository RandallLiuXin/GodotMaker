#!/usr/bin/env python3
"""Finalize generated image assets.

Copies a selected generated image to its project target path, optionally resizes
it, verifies it as an image, and prints JSON for the caller.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from collections import deque
from pathlib import Path


class ImageFinalizeError(Exception):
    """Raised when an image cannot be finalized."""


MAGENTA_RGB = (255, 0, 255)


def _parse_size(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    raw = value.lower().strip()
    if "x" not in raw:
        raise ImageFinalizeError("--resize must use WIDTHxHEIGHT")
    left, right = raw.split("x", 1)
    try:
        width = int(left)
        height = int(right)
    except ValueError as exc:
        raise ImageFinalizeError("--resize must use integer dimensions") from exc
    if width <= 0 or height <= 0:
        raise ImageFinalizeError("--resize dimensions must be positive")
    return width, height


def _parse_aspect(value: str | None) -> tuple[float, str] | None:
    if not value:
        return None
    raw = value.lower().strip()
    separator = ":" if ":" in raw else "x" if "x" in raw else None
    if separator is None:
        raise ImageFinalizeError("--require-aspect must use WIDTH:HEIGHT or WIDTHxHEIGHT")
    left, right = raw.split(separator, 1)
    try:
        width = float(left)
        height = float(right)
    except ValueError as exc:
        raise ImageFinalizeError("--require-aspect must use numeric dimensions") from exc
    if width <= 0 or height <= 0:
        raise ImageFinalizeError("--require-aspect dimensions must be positive")
    return width / height, f"{left}:{right}"


def _aspect_delta(width: int, height: int, required_ratio: float) -> float:
    if width <= 0 or height <= 0:
        raise ImageFinalizeError("Image dimensions must be positive")
    actual_ratio = width / height
    return abs(actual_ratio - required_ratio) / required_ratio


def _load_image(path: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageFinalizeError("Pillow is required to validate image assets") from exc

    try:
        image = Image.open(path)
        image.load()
        return image
    except Exception as exc:
        raise ImageFinalizeError(f"Source is not a readable image: {path}") from exc


def _color_distance(rgb: tuple[int, int, int], target: tuple[int, int, int] = MAGENTA_RGB) -> float:
    red, green, blue = rgb
    target_red, target_green, target_blue = target
    return (
        (red - target_red) ** 2
        + (green - target_green) ** 2
        + (blue - target_blue) ** 2
    ) ** 0.5


def _remove_magenta_background(
    image,
    *,
    edge_threshold: int,
) -> tuple[object, dict[str, int]]:
    if edge_threshold < 0:
        raise ImageFinalizeError("--magenta-edge-threshold must be zero or positive")
    converted = image.convert("RGBA")
    pixels = converted.load()
    removed = 0
    width, height = converted.size

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
            removed += 1
            should_expand = True
        if should_expand:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    next_pixel = (x + dx, y + dy)
                    if next_pixel not in visited:
                        queue.append(next_pixel)

    return converted, {"removed_pixels": removed}


def _atomic_save(image, output: Path, image_format: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    suffix = "." + image_format.lower()
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(output.parent),
        suffix=suffix,
    ) as handle:
        tmp_path = Path(handle.name)
    try:
        image.save(tmp_path, format=image_format.upper())
        tmp_path.replace(output)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _fit_with_padding(image, size: tuple[int, int]):
    """Resize preserving aspect ratio, padding to exactly ``size``.

    The image is scaled to fit within ``size`` (never cropped, never
    stretched) and centered on a fully transparent canvas of exactly
    ``size``. When the source aspect ratio already matches the target this
    degrades to a plain proportional resize with no padding. Avoids the
    aspect-ratio distortion a direct ``Image.resize(size)`` would cause when
    the generated image's aspect ratio differs from the requested one.
    """
    from PIL import Image

    target_w, target_h = size
    src_w, src_h = image.size
    scale = min(target_w / src_w, target_h / src_h)
    fit_w = max(1, round(src_w * scale))
    fit_h = max(1, round(src_h * scale))
    fitted = image.resize((fit_w, fit_h), Image.Resampling.LANCZOS)
    if fitted.mode != "RGBA":
        fitted = fitted.convert("RGBA")
    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    canvas.paste(fitted, ((target_w - fit_w) // 2, (target_h - fit_h) // 2))
    return canvas


def _origin_path_for(output: Path) -> Path:
    """Archive location for the untouched original of a finalized asset.

    Mirrors the asset under an ``origin/`` sibling of the project
    ``assets/`` root (e.g. ``assets/img/foo.png`` -> ``assets/origin/foo.png``).
    Falls back to an ``origin/`` directory beside the output when there is no
    ``assets`` ancestor (e.g. scene references under ``references/``).
    """
    for ancestor in output.parents:
        if ancestor.name == "assets":
            return ancestor / "origin" / (output.stem + ".png")
    return output.parent / "origin" / (output.stem + ".png")


def finalize_image_asset(
    source: Path,
    output: Path,
    *,
    resize: str | None = None,
    require_aspect: str | None = None,
    aspect_tolerance: float = 0.03,
    image_format: str = "png",
    label: str | None = None,
    archive_original: bool = True,
    background: str = "none",
    magenta_edge_threshold: int = 150,
) -> dict[str, object]:
    """Copy or transform a generated source image into its final path."""
    source = Path(source)
    output = Path(output)
    if not source.exists():
        raise ImageFinalizeError(f"Source image not found: {source}")
    if not source.is_file():
        raise ImageFinalizeError(f"Source image is not a file: {source}")

    requested_size = _parse_size(resize)
    required_aspect = _parse_aspect(require_aspect)
    if background not in {"none", "magenta"}:
        raise ImageFinalizeError("--background must be none or magenta")
    if aspect_tolerance < 0:
        raise ImageFinalizeError("--aspect-tolerance must be non-negative")
    image = _load_image(source)
    origin_saved: str | None = None
    background_cleanup: dict[str, int] | None = None
    try:
        original_width, original_height = image.size
        aspect_delta: float | None = None
        aspect_label: str | None = None
        if required_aspect is not None:
            required_ratio, aspect_label = required_aspect
            aspect_delta = _aspect_delta(original_width, original_height, required_ratio)
            if aspect_delta > aspect_tolerance:
                actual = f"{original_width}:{original_height}"
                raise ImageFinalizeError(
                    "Source image aspect ratio "
                    f"{actual} does not match required {aspect_label} "
                    f"(delta {aspect_delta:.4f}, tolerance {aspect_tolerance:.4f})"
                )
        source_format = (image.format or source.suffix.lstrip(".")).lower()
        changed = (
            requested_size is not None
            or background != "none"
            or output.suffix.lower() != source.suffix.lower()
            or source_format != image_format.lower()
        )
        # Archive the untouched original before resizing, so the pre-resize
        # art sits next to the finalized asset for comparison/debugging.
        # Only meaningful when we resize (otherwise the final IS the original).
        if archive_original and requested_size is not None:
            origin_path = _origin_path_for(output)
            origin_image = image
            if origin_image.mode not in {"RGB", "RGBA"}:
                origin_image = origin_image.convert(
                    "RGBA" if "A" in image.getbands() else "RGB"
                )
            _atomic_save(origin_image, origin_path, "png")
            origin_saved = str(origin_path)
        if background == "magenta":
            image, background_cleanup = _remove_magenta_background(
                image,
                edge_threshold=magenta_edge_threshold,
            )
        if requested_size is not None:
            image = _fit_with_padding(image, requested_size)
        if image_format.lower() == "png" and image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")

        if source.resolve() == output.resolve() and not changed:
            final_image = _load_image(output)
            final_image.close()
        elif not changed:
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, output)
        else:
            _atomic_save(image, output, image_format)
    finally:
        image.close()

    final_image = _load_image(output)
    try:
        width, height = final_image.size
        mode = final_image.mode
        fmt = final_image.format
    finally:
        final_image.close()

    result: dict[str, object] = {
        "ok": True,
        "source": str(source),
        "path": str(output),
        "bytes": output.stat().st_size,
        "width": width,
        "height": height,
        "format": fmt or image_format.upper(),
        "mode": mode,
        "original_width": original_width,
        "original_height": original_height,
    }
    if origin_saved is not None:
        result["origin"] = origin_saved
    if requested_size is not None:
        result["resize"] = f"{requested_size[0]}x{requested_size[1]}"
    if background_cleanup is not None:
        result["background"] = "magenta"
        result["background_cleanup"] = background_cleanup
    if required_aspect is not None:
        result["required_aspect"] = aspect_label
        result["aspect_delta"] = aspect_delta
        result["aspect_tolerance"] = aspect_tolerance
    if label:
        result["label"] = label
        result["asset_id"] = label
    return result


def _main() -> int:
    parser = argparse.ArgumentParser(description="Finalize a generated image asset")
    parser.add_argument("--source", required=True, help="Generated source image path")
    parser.add_argument("--out", required=True, help="Final project image path")
    parser.add_argument("--resize", default=None, help="Optional WIDTHxHEIGHT resize")
    parser.add_argument(
        "--require-aspect",
        default=None,
        help="Require source aspect WIDTH:HEIGHT or WIDTHxHEIGHT before resize",
    )
    parser.add_argument(
        "--aspect-tolerance",
        type=float,
        default=0.03,
        help="Maximum relative source-aspect delta for --require-aspect",
    )
    parser.add_argument("--format", default="png", choices=["png"], help="Output format")
    parser.add_argument("--label", default=None, help="Optional asset label for JSON output")
    parser.add_argument(
        "--background",
        default="none",
        choices=["none", "magenta"],
        help="Optional source background cleanup mode",
    )
    parser.add_argument(
        "--magenta-edge-threshold",
        type=int,
        default=150,
        help="RGB distance threshold for edge-connected magenta cleanup",
    )
    parser.add_argument(
        "--no-origin",
        dest="archive_original",
        action="store_false",
        help="Do not archive the untouched original under assets/origin/",
    )
    args = parser.parse_args()

    try:
        result = finalize_image_asset(
            Path(args.source),
            Path(args.out),
            resize=args.resize,
            require_aspect=args.require_aspect,
            aspect_tolerance=args.aspect_tolerance,
            image_format=args.format,
            label=args.label,
            archive_original=args.archive_original,
            background=args.background,
            magenta_edge_threshold=args.magenta_edge_threshold,
        )
    except ImageFinalizeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
