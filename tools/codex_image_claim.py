#!/usr/bin/env python3
"""Claim a Codex-generated image from an explicit saved_path.

The caller must pass the concrete path returned by Codex ImageGenerationEnd.
This script never scans generated_images or guesses the newest file.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse


class CodexImageClaimError(Exception):
    """Raised when a Codex generated image cannot be claimed."""


def _path_from_arg(value: str) -> Path:
    if len(value) >= 3 and value[1] == ":" and value[2] in {"\\", "/"}:
        return Path(value)
    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme != "file":
        raise CodexImageClaimError("Only local paths and file:// URLs are supported")
    if parsed.scheme == "file":
        raw_path = unquote(parsed.path)
        if parsed.netloc and parsed.netloc.lower() != "localhost":
            raw_path = f"//{parsed.netloc}{raw_path}"
        if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
            raw_path = raw_path[1:]
        return Path(raw_path)
    return Path(value)


def _load_image(path: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise CodexImageClaimError("Pillow is required to validate image assets") from exc

    try:
        image = Image.open(path)
        image.load()
        return image
    except Exception as exc:
        raise CodexImageClaimError(f"Source is not a readable image: {path}") from exc


def _copy_atomic(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False,
        dir=str(output.parent),
        suffix=output.suffix or ".png",
    ) as handle:
        tmp_path = Path(handle.name)
    try:
        shutil.copy2(source, tmp_path)
        tmp_path.replace(output)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def claim_codex_image(source: str, output: Path, *, asset_id: str | None = None) -> dict[str, object]:
    source_path = _path_from_arg(source)
    output = Path(output)
    if not source_path.exists():
        raise CodexImageClaimError(f"Source image not found: {source_path}")
    if not source_path.is_file():
        raise CodexImageClaimError(f"Source image is not a file: {source_path}")

    image = _load_image(source_path)
    try:
        width, height = image.size
        mode = image.mode
        fmt = image.format
    finally:
        image.close()

    _copy_atomic(source_path, output)

    result: dict[str, object] = {
        "ok": True,
        "source": str(source_path),
        "path": str(output),
        "bytes": output.stat().st_size,
        "width": width,
        "height": height,
        "format": fmt or output.suffix.lstrip(".").upper() or "PNG",
        "mode": mode,
    }
    if asset_id:
        result["asset_id"] = asset_id
        result["label"] = asset_id
    return result


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy a Codex ImageGenerationEnd saved_path to a project source path"
    )
    parser.add_argument("--source", required=True, help="Codex ImageGenerationEnd saved_path")
    parser.add_argument("--out", required=True, help="Project-local claimed source image path")
    parser.add_argument("--asset-id", default=None, help="Optional asset id for JSON output")
    args = parser.parse_args()

    try:
        result = claim_codex_image(args.source, Path(args.out), asset_id=args.asset_id)
    except (CodexImageClaimError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
