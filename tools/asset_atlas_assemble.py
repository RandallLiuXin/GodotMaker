#!/usr/bin/env python3
"""Assemble a physical PNG atlas from explicitly declared fixed slots.

This is deliberately not a packing tool. Every source PNG must be assigned to
one declared rectangle of an explicitly sized atlas; sources are neither
trimmed nor inspected to discover regions. Both output files are constrained to
the asset's stable generated-output directory and are committed together.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_output_paths import AssetOutputPathError, assert_within_output_dir, safe_identifier


SCHEMA_VERSION = 1
MAX_ATLAS_PIXELS = 64 * 1024 * 1024
DECLARATION_KEYS = {"version", "atlas", "slots"}
ATLAS_KEYS = {"width", "height"}
SLOT_KEYS = {"name", "rect", "source", "pivot"}


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


def rectangles_overlap(
    left: tuple[int, int, int, int], right: tuple[int, int, int, int]
) -> bool:
    """Return whether two positive [x, y, width, height] rectangles overlap."""
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    return not (
        left_x + left_width <= right_x
        or right_x + right_width <= left_x
        or left_y + left_height <= right_y
        or right_y + right_height <= left_y
    )


def validate_fixed_slot_rectangles(
    rectangles: list[tuple[int, int, int, int]], atlas_width: int, atlas_height: int
) -> None:
    """Reject fixed slot rectangles outside an atlas or overlapping a prior slot."""
    for index, rect in enumerate(rectangles):
        x, y, width, height = rect
        if x + width > atlas_width or y + height > atlas_height:
            raise ValueError(f"slots[{index}].rect is outside the declared atlas bounds")
        if any(rectangles_overlap(rect, existing) for existing in rectangles[:index]):
            raise ValueError(f"slots[{index}].rect overlaps another declared slot")


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


def _project_file(project_root: Path, value: Path | str, label: str) -> Path:
    root = Path(project_root).resolve()
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise AtlasAssemblyError(f"{label} resolves outside the project root")
    return resolved


def _temporary_path(directory: Path, suffix: str) -> Path:
    with tempfile.NamedTemporaryFile(delete=False, dir=directory, suffix=suffix) as handle:
        return Path(handle.name)


def _write_png_temp(image, directory: Path) -> Path:
    try:
        temporary = _temporary_path(directory, ".png")
        image.save(temporary, format="PNG", optimize=False, compress_level=9)
        return temporary
    except (MemoryError, OSError, ValueError) as exc:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)
        raise AtlasAssemblyError("Unable to write atlas PNG") from exc


def _write_json_temp(data: dict[str, Any], directory: Path) -> Path:
    try:
        temporary = _temporary_path(directory, ".json")
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        return temporary
    except (MemoryError, OSError, TypeError, ValueError) as exc:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)
        raise AtlasAssemblyError("Unable to write atlas metadata") from exc


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    try:
        backup = _temporary_path(path.parent, path.suffix)
        shutil.copy2(path, backup)
    except OSError as exc:
        if "backup" in locals():
            backup.unlink(missing_ok=True)
        raise AtlasAssemblyError(f"Unable to back up existing output: {path}") from exc
    return backup


def _restore(path: Path, backup: Path | None) -> None:
    if backup is None:
        path.unlink(missing_ok=True)
    else:
        os.replace(backup, path)


def _commit_output_pair(
    atlas_temp: Path,
    atlas_output: Path,
    metadata_temp: Path,
    metadata_output: Path,
) -> None:
    """Replace both outputs or restore the previous pair after an I/O failure."""
    atlas_backup: Path | None = None
    metadata_backup: Path | None = None
    atlas_replaced = False
    metadata_replaced = False
    commit_succeeded = False
    try:
        atlas_backup = _backup(atlas_output)
        metadata_backup = _backup(metadata_output)
        os.replace(atlas_temp, atlas_output)
        atlas_replaced = True
        os.replace(metadata_temp, metadata_output)
        metadata_replaced = True
        commit_succeeded = True
    except OSError as exc:
        rollback_failures: list[tuple[Path, Path | None, OSError]] = []
        if atlas_replaced:
            try:
                _restore(atlas_output, atlas_backup)
                atlas_backup = None
            except OSError as rollback_exc:
                rollback_failures.append((atlas_output, atlas_backup, rollback_exc))
        if metadata_replaced:
            try:
                _restore(metadata_output, metadata_backup)
                metadata_backup = None
            except OSError as rollback_exc:
                rollback_failures.append(
                    (metadata_output, metadata_backup, rollback_exc)
                )
        if rollback_failures:
            recovery_locations = "; ".join(
                f"{output} (backup: {backup})"
                for output, backup, _ in rollback_failures
            )
            raise AtlasAssemblyError(
                "Unable to commit atlas outputs and rollback failed; "
                f"manual recovery required for: {recovery_locations}"
            ) from rollback_failures[0][2]
        raise AtlasAssemblyError("Unable to commit atlas outputs; changes were rolled back") from exc
    finally:
        atlas_temp.unlink(missing_ok=True)
        metadata_temp.unlink(missing_ok=True)
        if atlas_backup is not None and (commit_succeeded or not atlas_replaced):
            atlas_backup.unlink(missing_ok=True)
        if metadata_backup is not None and (commit_succeeded or not metadata_replaced):
            metadata_backup.unlink(missing_ok=True)


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
    production_family: str,
    asset_id: str,
    project_root: Path,
) -> dict[str, Any]:
    """Validate a declaration, then write its physical atlas PNG and metadata."""
    project_root = Path(project_root).resolve()
    declaration_path = _project_file(project_root, declaration_path, "declaration")
    declaration = _load_declaration(declaration_path)
    atlas = _require_object(declaration.get("atlas"), "declaration.atlas")
    _reject_extra_keys(atlas, ATLAS_KEYS, "declaration.atlas")
    atlas_width = _positive_int(atlas.get("width"), "declaration.atlas.width")
    atlas_height = _positive_int(atlas.get("height"), "declaration.atlas.height")
    if atlas_width * atlas_height > MAX_ATLAS_PIXELS:
        raise AtlasAssemblyError(
            f"Declared atlas exceeds the {MAX_ATLAS_PIXELS}-pixel safety limit"
        )
    slots = declaration.get("slots")
    if not isinstance(slots, list) or not slots:
        raise AtlasAssemblyError("declaration.slots must be a non-empty list")

    try:
        atlas_output = assert_within_output_dir(
            project_root,
            atlas_output,
            production_family=production_family,
            asset_id=asset_id,
            label="atlas output",
        )
        metadata_output = assert_within_output_dir(
            project_root,
            metadata_output,
            production_family=production_family,
            asset_id=asset_id,
            label="metadata output",
        )
    except AssetOutputPathError as exc:
        raise AtlasAssemblyError(str(exc)) from exc
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
        try:
            safe_identifier(name, f"{label}.name")
        except AssetOutputPathError as exc:
            raise AtlasAssemblyError(str(exc)) from exc
        if name in names:
            raise AtlasAssemblyError(f"Slot name is duplicated: {name}")
        names.add(name)
        rect = _rect(slot.get("rect"), f"{label}.rect")
        try:
            validate_fixed_slot_rectangles(
                [*rectangles, rect], atlas_width, atlas_height
            )
        except ValueError as exc:
            raise AtlasAssemblyError(f"declaration.{exc}") from exc
        rectangles.append(rect)
        source = slot.get("source")
        if not isinstance(source, str) or not source.strip():
            raise AtlasAssemblyError(f"{label}.source must be a non-empty PNG path")
        source_path = _project_file(project_root, source, f"{label}.source")
        if source_path == atlas_output:
            raise AtlasAssemblyError(f"{label}.source must not be the atlas output")
        parsed_slots.append(
            {
                "name": name,
                "rect": rect,
                "source": source_path,
                "pivot": _pivot(slot.get("pivot"), f"{label}.pivot"),
            }
        )

    loaded_images: list[tuple[dict[str, Any], Any]] = []
    canvas = None
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

        try:
            canvas = Image.new("RGBA", (atlas_width, atlas_height), (0, 0, 0, 0))
        except (MemoryError, OSError, ValueError) as exc:
            raise AtlasAssemblyError("Unable to allocate the declared atlas") from exc
        for slot, image in loaded_images:
            # Slots are non-overlapping, so a direct copy preserves every RGBA
            # value, including transparent RGB edge-padding used by filtering.
            canvas.paste(image, box=slot["rect"][:2])
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
            "atlas_path": "res://" + atlas_output.relative_to(project_root).as_posix(),
            "regions": regions,
        }
        # Both parents are made ready before either temporary output is written.
        try:
            atlas_output.parent.mkdir(parents=True, exist_ok=True)
            metadata_output.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise AtlasAssemblyError("Unable to prepare atlas output directories") from exc
        atlas_temp = _write_png_temp(canvas, atlas_output.parent)
        try:
            metadata_temp = _write_json_temp(metadata, metadata_output.parent)
        except AtlasAssemblyError:
            atlas_temp.unlink(missing_ok=True)
            raise
        _commit_output_pair(atlas_temp, atlas_output, metadata_temp, metadata_output)
    finally:
        if canvas is not None:
            canvas.close()
        for _, image in loaded_images:
            image.close()

    return {
        "ok": True,
        "atlas_path": metadata["atlas_path"],
        "metadata_path": "res://" + metadata_output.relative_to(project_root).as_posix(),
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
    parser.add_argument("--family", required=True, help="Production family for the stable output directory")
    parser.add_argument("--asset-id", required=True, help="Asset id for the stable output directory")
    parser.add_argument("--project-root", default=".", type=Path, help="Project root for inputs and outputs")
    args = parser.parse_args()
    try:
        result = assemble_atlas(
            args.declaration,
            args.atlas_out,
            args.metadata_out,
            production_family=args.family,
            asset_id=args.asset_id,
            project_root=args.project_root,
        )
    except AtlasAssemblyError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
