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
from pathlib import Path


class ImageFinalizeError(Exception):
    """Raised when an image cannot be finalized."""


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
    image_format: str = "png",
    label: str | None = None,
    archive_original: bool = True,
) -> dict[str, object]:
    """Copy or transform a generated source image into its final path."""
    source = Path(source)
    output = Path(output)
    if not source.exists():
        raise ImageFinalizeError(f"Source image not found: {source}")
    if not source.is_file():
        raise ImageFinalizeError(f"Source image is not a file: {source}")

    requested_size = _parse_size(resize)
    image = _load_image(source)
    origin_saved: str | None = None
    try:
        original_width, original_height = image.size
        source_format = (image.format or source.suffix.lstrip(".")).lower()
        changed = (
            requested_size is not None
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
    if label:
        result["label"] = label
        result["asset_id"] = label
    return result


def _main() -> int:
    parser = argparse.ArgumentParser(description="Finalize a generated image asset")
    parser.add_argument("--source", required=True, help="Generated source image path")
    parser.add_argument("--out", required=True, help="Final project image path")
    parser.add_argument("--resize", default=None, help="Optional WIDTHxHEIGHT resize")
    parser.add_argument("--format", default="png", choices=["png"], help="Output format")
    parser.add_argument("--label", default=None, help="Optional asset label for JSON output")
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
            image_format=args.format,
            label=args.label,
            archive_original=args.archive_original,
        )
    except ImageFinalizeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
