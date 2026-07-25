#!/usr/bin/env python3
"""Assemble a physical PNG atlas from explicitly declared fixed slots.

This is deliberately not a packing tool.  Every source PNG must be assigned to
one declared rectangle of an explicitly sized atlas; sources are neither
trimmed nor inspected to discover regions.  The companion metadata describes
those same declared rectangles for a later AtlasTexture compiler.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DECLARATION_KEYS = {"version", "atlas", "slots"}
ATLAS_KEYS = {"width", "height"}
SLOT_KEYS = {"name", "rect", "source", "pivot", "nine_slice"}


class AtlasAssemblyError(Exception):
    """Raised when a fixed-slot atlas declaration cannot be assembled."""


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AtlasAssemblyError(f"{label} must be an object")
    return value


def _reject_extra_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = sorted(set(value) - allowed)
    if extra:
        raise AtlasAssemblyError(f"{label} has unexpected fields: {', '.join(extra)}")


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise AtlasAssemblyError(f"{label} must be a positive integer")
    return value


def _non_negative_int(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise AtlasAssemblyError(f"{label} must be a non-negative integer")
    return value


def _rect(value: Any, label: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise AtlasAssemblyError(f"{label} must be [x, y, width, height]")
    x = _non_negative_int(value[0], f"{label}[0]")
    y = _non_negative_int(value[1], f"{label}[1]")
    width = _positive_int(value[2], f"{label}[2]")
    height = _positive_int(value[3], f"{label}[3]")
    return x, y, width, height


def _pivot(value: Any, label: str) -> list[float]:
    if value is None:
        return [0.5, 0.5]
    if not isinstance(value, list) or len(value) != 2:
        raise AtlasAssemblyError(f"{label} must be [x, y]")
    pivot: list[float] = []
    for index, component in enumerate(value):
        if type(component) not in {int, float} or not 0 <= component <= 1:
            raise AtlasAssemblyError(f"{label}[{index}] must be a number from 0 to 1")
        pivot.append(float(component))
    return pivot


def _rectangles_overlap(
    left: tuple[int, int, int, int], right: tuple[int, int, int, int]
) -> bool:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    return not (
        left_x + left_width <= right_x
        or right_x + right_width <= left_x
        or left_y + left_height <= right_y
        or right_y + right_height <= left_y
    )


def _load_png(path: Path):
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - environment dependency
        raise AtlasAssemblyError("Pillow is required to assemble PNG atlases") from exc

    if path.suffix.lower() != ".png":
        raise AtlasAssemblyError(f"Slot source must be a PNG file: {path}")
    if not path.is_file():
        raise AtlasAssemblyError(f"Slot source is missing: {path}")
    try:
        image = Image.open(path)
        image.load()
    except Exception as exc:  # noqa: BLE001 - converted into a tool error
        raise AtlasAssemblyError(f"Slot source is not a readable PNG: {path}") from exc
    if image.format != "PNG":
        image.close()
        raise AtlasAssemblyError(f"Slot source is not a PNG file: {path}")
    return image


def _output_path(project_root: Path, raw_path: Path, label: str) -> Path:
    root = Path(project_root).resolve()
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise AtlasAssemblyError(f"{label} resolves outside the project root")
    return resolved


def _res_path(project_root: Path, path: Path) -> str:
    return "res://" + path.resolve().relative_to(Path(project_root).resolve()).as_posix()


def _atomic_save_png(image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=output.parent, suffix=".png") as handle:
        temporary = Path(handle.name)
    try:
        image.save(temporary, format="PNG", optimize=False, compress_level=9)
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(data: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        delete=False, dir=output.parent, suffix=".json", mode="w", encoding="utf-8"
    ) as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, indent=2)
        handle.write("\n")
    try:
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_declaration(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - converted into a tool error
        raise AtlasAssemblyError(f"Invalid atlas declaration: {path}") from exc
    data = _require_object(data, "declaration")
    _reject_extra_keys(data, DECLARATION_KEYS, "declaration")
    if type(data.get("version")) is not int or data["version"] != SCHEMA_VERSION:
        raise AtlasAssemblyError(f"declaration.version must be integer {SCHEMA_VERSION}")
    return data


def assemble_atlas(
    declaration_path: Path,
    atlas_output: Path,
    metadata_output: Path,
    *,
    project_root: Path,
) -> dict[str, Any]:
    """Validate a declaration, then write its physical atlas PNG and metadata."""
    declaration_path = Path(declaration_path).resolve()
    declaration = _load_declaration(declaration_path)
    atlas = _require_object(declaration.get("atlas"), "declaration.atlas")
    _reject_extra_keys(atlas, ATLAS_KEYS, "declaration.atlas")
    atlas_width = _positive_int(atlas.get("width"), "declaration.atlas.width")
    atlas_height = _positive_int(atlas.get("height"), "declaration.atlas.height")
    slots = declaration.get("slots")
    if not isinstance(slots, list) or not slots:
        raise AtlasAssemblyError("declaration.slots must be a non-empty list")

    atlas_output = _output_path(project_root, atlas_output, "atlas output")
    metadata_output = _output_path(project_root, metadata_output, "metadata output")
    if atlas_output.suffix.lower() != ".png":
        raise AtlasAssemblyError("atlas output must end in .png")
    if metadata_output.suffix.lower() != ".json":
        raise AtlasAssemblyError("metadata output must end in .json")
    if atlas_output == metadata_output:
        raise AtlasAssemblyError("atlas output and metadata output must be different files")

    parsed_slots: list[dict[str, Any]] = []
    names: set[str] = set()
    rectangles: list[tuple[int, int, int, int]] = []
    for index, raw_slot in enumerate(slots):
        label = f"declaration.slots[{index}]"
        slot = _require_object(raw_slot, label)
        _reject_extra_keys(slot, SLOT_KEYS, label)
        name = slot.get("name")
        if not isinstance(name, str) or not name.strip():
            raise AtlasAssemblyError(f"{label}.name must be a non-empty string")
        if name in names:
            raise AtlasAssemblyError(f"Slot name is duplicated: {name}")
        names.add(name)
        rect = _rect(slot.get("rect"), f"{label}.rect")
        x, y, width, height = rect
        if x + width > atlas_width or y + height > atlas_height:
            raise AtlasAssemblyError(f"{label}.rect is outside the declared atlas bounds")
        if any(_rectangles_overlap(rect, existing) for existing in rectangles):
            raise AtlasAssemblyError(f"{label}.rect overlaps another declared slot")
        rectangles.append(rect)
        source = slot.get("source")
        if not isinstance(source, str) or not source.strip():
            raise AtlasAssemblyError(f"{label}.source must be a non-empty PNG path")
        source_path = (declaration_path.parent / source).resolve()
        if source_path == atlas_output:
            raise AtlasAssemblyError(f"{label}.source must not be the atlas output")
        if slot.get("nine_slice") is not None:
            raise AtlasAssemblyError(f"{label}.nine_slice must be null; nine-slice is not handled here")
        parsed_slots.append(
            {"name": name, "rect": rect, "source": source_path, "pivot": _pivot(slot.get("pivot"), f"{label}.pivot")}
        )

    # Validate every source and its declared size before creating either output.
    loaded_images: list[tuple[dict[str, Any], Any]] = []
    try:
        for slot in parsed_slots:
            image = _load_png(slot["source"])
            if image.size != slot["rect"][2:]:
                image.close()
                raise AtlasAssemblyError(
                    f"Slot source size {image.size} does not match declared rect "
                    f"{slot['rect'][2]}x{slot['rect'][3]}: {slot['source']}"
                )
            loaded_images.append((slot, image.convert("RGBA")))
            image.close()

        from PIL import Image

        canvas = Image.new("RGBA", (atlas_width, atlas_height), (0, 0, 0, 0))
        for slot, image in loaded_images:
            canvas.alpha_composite(image, dest=slot["rect"][:2])
        regions = [
            {
                "name": slot["name"],
                "rect": list(slot["rect"]),
                "pivot": slot["pivot"],
                "nine_slice": None,
            }
            for slot in sorted(parsed_slots, key=lambda item: item["name"])
        ]
        metadata = {
            "version": SCHEMA_VERSION,
            "atlas_path": _res_path(project_root, atlas_output),
            "regions": regions,
        }
        _atomic_save_png(canvas, atlas_output)
        canvas.close()
        _atomic_write_json(metadata, metadata_output)
    finally:
        for _, image in loaded_images:
            image.close()

    return {
        "ok": True,
        "atlas_path": metadata["atlas_path"],
        "metadata_path": _res_path(project_root, metadata_output),
        "width": atlas_width,
        "height": atlas_height,
        "slot_count": len(parsed_slots),
        "regions": metadata["regions"],
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Assemble a physical PNG atlas from explicit fixed slot rectangles"
    )
    parser.add_argument("--declaration", required=True, type=Path, help="Fixed-slot declaration JSON")
    parser.add_argument("--atlas-out", required=True, type=Path, help="Physical atlas PNG output")
    parser.add_argument("--metadata-out", required=True, type=Path, help="Atlas region metadata JSON output")
    parser.add_argument("--project-root", default=".", type=Path, help="Project root for outputs and res:// paths")
    args = parser.parse_args()
    try:
        result = assemble_atlas(
            args.declaration,
            args.atlas_out,
            args.metadata_out,
            project_root=args.project_root,
        )
    except AtlasAssemblyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
