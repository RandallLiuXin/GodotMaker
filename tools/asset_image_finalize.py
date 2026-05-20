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


def finalize_image_asset(
    source: Path,
    output: Path,
    *,
    resize: str | None = None,
    image_format: str = "png",
    label: str | None = None,
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
    try:
        original_width, original_height = image.size
        source_format = (image.format or source.suffix.lstrip(".")).lower()
        changed = (
            requested_size is not None
            or output.suffix.lower() != source.suffix.lower()
            or source_format != image_format.lower()
        )
        if requested_size is not None:
            from PIL import Image

            resample = Image.Resampling.LANCZOS
            image = image.resize(requested_size, resample)
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
    args = parser.parse_args()

    try:
        result = finalize_image_asset(
            Path(args.source),
            Path(args.out),
            resize=args.resize,
            image_format=args.format,
            label=args.label,
        )
    except ImageFinalizeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
