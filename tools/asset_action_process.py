#!/usr/bin/env python3
"""Process a character action source sheet into runtime-ready frames."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from asset_sheet_process import SheetProcessError, process_sheet


class ActionProcessError(Exception):
    """Raised when a character action sheet cannot be processed."""


def _parse_grid(value: str) -> tuple[int, int]:
    raw = value.lower().strip()
    if "x" not in raw:
        raise ActionProcessError("--grid must use COLSxROWS")
    left, right = raw.split("x", 1)
    try:
        cols = int(left)
        rows = int(right)
    except ValueError as exc:
        raise ActionProcessError("--grid must use integer dimensions") from exc
    if cols <= 0 or rows <= 0:
        raise ActionProcessError("--grid dimensions must be positive")
    return cols, rows


def _parse_names(value: str, total: int) -> list[str]:
    names = [name.strip() for name in value.split(",")]
    if any(not name for name in names):
        raise ActionProcessError("--names cannot contain empty names")
    if len(names) != total:
        raise ActionProcessError(f"--names has {len(names)} entries, grid has {total} cells")
    return names


def _write_atomic_json(path: Path, data: dict[str, Any]) -> None:
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


def _load_rgba(path: Path):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ActionProcessError("Pillow is required to process action sheets") from exc
    try:
        image = Image.open(path).convert("RGBA")
        image.load()
        return image
    except Exception as exc:
        raise ActionProcessError(f"Frame is not a readable image: {path}") from exc


def _normalize_frames(
    frame_paths: list[Path],
    *,
    cell_size: int,
    fit_scale: float,
    align: str,
    shared_scale: bool,
) -> tuple[list[Any], list[dict[str, object]]]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ActionProcessError("Pillow is required to process action sheets") from exc

    originals = [_load_rgba(path) for path in frame_paths]
    try:
        max_width = max((image.width for image in originals), default=0)
        max_height = max((image.height for image in originals), default=0)
        if max_width <= 0 or max_height <= 0:
            raise ActionProcessError("Action source produced no visible frames")

        common_scale = None
        if shared_scale:
            common_scale = min(cell_size / max_width, cell_size / max_height) * fit_scale

        frames = []
        metadata = []
        for path, image in zip(frame_paths, originals):
            scale = common_scale or min(cell_size / image.width, cell_size / image.height) * fit_scale
            width = max(1, int(image.width * scale))
            height = max(1, int(image.height * scale))
            resized = image.resize((width, height), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (cell_size, cell_size), (0, 0, 0, 0))
            x = (cell_size - width) // 2
            if align in {"bottom", "feet"}:
                pad = max(0, int(cell_size * (1 - fit_scale) * 0.5))
                y = cell_size - height - pad
            else:
                y = (cell_size - height) // 2
            canvas.paste(resized, (x, y), resized)
            frames.append(canvas)
            metadata.append(
                {
                    "candidate_path": str(path),
                    "source_size": [image.width, image.height],
                    "output_size": [width, height],
                    "paste_position": [x, y],
                }
            )
        return frames, metadata
    finally:
        for image in originals:
            image.close()


def _compose_sheet(frames: list[Any], *, cols: int, rows: int, cell_size: int):
    from PIL import Image

    sheet = Image.new("RGBA", (cols * cell_size, rows * cell_size), (0, 0, 0, 0))
    for index, frame in enumerate(frames):
        col = index % cols
        row = index // cols
        sheet.paste(frame, (col * cell_size, row * cell_size), frame)
    return sheet


def _save_gif(frames: list[Any], path: Path, *, duration: int) -> None:
    if not frames:
        raise ActionProcessError("No frames to encode")
    path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        path,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=duration,
        loop=0,
        disposal=2,
        transparency=0,
    )


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _frame_heights_from_metadata(metadata: dict[str, Any]) -> list[float]:
    frames = metadata.get("frames")
    if not isinstance(frames, list):
        return []
    heights: list[float] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        output_size = frame.get("output_size")
        if (
            isinstance(output_size, list)
            and len(output_size) == 2
            and isinstance(output_size[1], (int, float))
            and output_size[1] > 0
        ):
            heights.append(float(output_size[1]))
    return heights


def _check_scale_reference(
    metadata: dict[str, Any],
    reference_path: Path | None,
    *,
    tolerance: float,
) -> dict[str, object]:
    if reference_path is None:
        return {"checked": False}
    if tolerance <= 0:
        raise ActionProcessError("--scale-tolerance must be positive")
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ActionProcessError(f"Scale reference metadata is not readable: {reference_path}") from exc

    current_height = _median(_frame_heights_from_metadata(metadata))
    reference_height = _median(_frame_heights_from_metadata(reference))
    if current_height is None:
        raise ActionProcessError("Current action metadata has no frame heights")
    if reference_height is None:
        raise ActionProcessError("Scale reference metadata has no frame heights")

    ratio = current_height / reference_height
    min_ratio = 1 - tolerance
    max_ratio = 1 + tolerance
    result: dict[str, object] = {
        "checked": True,
        "reference_metadata_path": str(reference_path),
        "current_median_height": current_height,
        "reference_median_height": reference_height,
        "ratio": ratio,
        "tolerance": tolerance,
    }
    if ratio < min_ratio or ratio > max_ratio:
        raise ActionProcessError(
            "Body scale drift exceeds tolerance: "
            f"{ratio:.3f} outside {min_ratio:.3f}-{max_ratio:.3f}"
        )
    return result


def _copy_runtime_outputs(
    frame_paths: list[Path],
    sheet_path: Path,
    *,
    final_dir: Path | None,
    final_prefix: str | None,
) -> tuple[list[str], str | None]:
    if final_dir is None:
        return [str(path) for path in frame_paths], None
    if not final_prefix:
        raise ActionProcessError("--final-prefix is required when --final-dir is used")
    final_dir.mkdir(parents=True, exist_ok=True)
    final_frames = []
    used_names: set[str] = set()
    for path in frame_paths:
        frame_stem = path.stem
        output_stem = frame_stem if frame_stem.startswith(f"{final_prefix}_") else f"{final_prefix}_{frame_stem}"
        output_name = f"{output_stem}{path.suffix}"
        if output_name in used_names:
            raise ActionProcessError(f"Runtime frame name collision: {output_name}")
        used_names.add(output_name)
        target = final_dir / output_name
        shutil.copy2(path, target)
        final_frames.append(str(target))
    final_sheet = final_dir / f"{final_prefix}_sheet.png"
    shutil.copy2(sheet_path, final_sheet)
    return final_frames, str(final_sheet)


def process_action_sheet(
    source: Path,
    output_dir: Path,
    *,
    grid: str,
    names: str,
    asset_id: str | None = None,
    tag: str | None = None,
    background: str = "magenta",
    component_mode: str = "largest",
    component_padding: int = 8,
    min_component_area: int = 100,
    cell_size: int = 128,
    fit_scale: float = 0.85,
    align: str = "feet",
    shared_scale: bool = True,
    duration: int = 160,
    reject_edge_touch: bool = True,
    scale_reference_metadata: Path | None = None,
    scale_tolerance: float = 0.15,
    final_dir: Path | None = None,
    final_prefix: str | None = None,
    report: Path | None = None,
) -> dict[str, object]:
    """Normalize one action sheet into frames, a transparent sheet, GIF, and metadata."""
    if align not in {"center", "bottom", "feet"}:
        raise ActionProcessError("--align must be center, bottom, or feet")
    if cell_size <= 0:
        raise ActionProcessError("--cell-size must be positive")
    if fit_scale <= 0:
        raise ActionProcessError("--fit-scale must be positive")
    cols, rows = _parse_grid(grid)
    frame_names = _parse_names(names, cols * rows)

    output_dir = Path(output_dir)
    candidate_dir = output_dir / "candidates"
    frame_dir = output_dir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    curation_report = output_dir / "curation-report.json"

    try:
        curation = process_sheet(
            source,
            candidate_dir,
            grid=grid,
            names=names,
            asset_id=asset_id,
            tag=tag,
            background=background,
            snap_mode="grid",
            component_mode=component_mode,
            component_padding=component_padding,
            min_component_area=min_component_area,
            reject_edge_touch=reject_edge_touch,
            report=curation_report,
        )
    except SheetProcessError as exc:
        raise ActionProcessError(str(exc)) from exc

    candidates = {
        str(item.get("name")): Path(str(item.get("path")))
        for item in curation.get("candidates", [])
        if isinstance(item, dict) and item.get("path")
    }
    missing = [name for name in frame_names if name not in candidates]
    if missing:
        raise ActionProcessError(f"Missing required frames: {', '.join(missing)}")

    normalized, frame_meta = _normalize_frames(
        [candidates[name] for name in frame_names],
        cell_size=cell_size,
        fit_scale=fit_scale,
        align=align,
        shared_scale=shared_scale,
    )
    frame_paths = []
    for name, frame, meta in zip(frame_names, normalized, frame_meta):
        path = frame_dir / f"{name}.png"
        frame.save(path)
        meta["name"] = name
        meta["path"] = str(path)
        frame_paths.append(path)

    sheet = _compose_sheet(normalized, cols=cols, rows=rows, cell_size=cell_size)
    sheet_path = output_dir / "sheet-transparent.png"
    sheet.save(sheet_path)
    gif_path = output_dir / "animation.gif"
    _save_gif(normalized, gif_path, duration=duration)
    final_frames, final_sheet = _copy_runtime_outputs(
        frame_paths,
        sheet_path,
        final_dir=final_dir,
        final_prefix=final_prefix,
    )

    metadata: dict[str, object] = {
        "version": 1,
        "ok": True,
        "asset_id": asset_id,
        "tag": tag,
        "source_path": str(source),
        "output_dir": str(output_dir),
        "grid": {"cols": cols, "rows": rows},
        "frame_count": len(frame_names),
        "frame_labels": frame_names,
        "component_mode": component_mode,
        "component_padding": component_padding,
        "min_component_area": min_component_area,
        "cell_size": cell_size,
        "fit_scale": fit_scale,
        "align": align,
        "shared_scale": shared_scale,
        "duration": duration,
        "curation_report_path": str(curation_report),
        "edge_touch_frames": curation.get("edge_touch_candidates", []),
        "frames": frame_meta,
        "frame_paths": [str(path) for path in frame_paths],
        "sheet_path": str(sheet_path),
        "gif_path": str(gif_path),
        "final_frame_paths": final_frames,
        "final_sheet_path": final_sheet,
    }
    metadata["scale_reference"] = _check_scale_reference(
        metadata,
        scale_reference_metadata,
        tolerance=scale_tolerance,
    )
    meta_path = Path(report) if report is not None else output_dir / "pipeline-meta.json"
    _write_atomic_json(meta_path, metadata)
    metadata["report"] = str(meta_path)
    return metadata


def _main() -> int:
    parser = argparse.ArgumentParser(description="Process a character action source sheet")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--grid", required=True)
    parser.add_argument("--names", required=True)
    parser.add_argument("--kind", required=True, choices=["body", "fx"])
    parser.add_argument("--asset-id")
    parser.add_argument("--tag")
    parser.add_argument("--background", choices=["transparent", "magenta"], default="magenta")
    parser.add_argument("--align", choices=["center", "bottom", "feet"])
    parser.add_argument("--scale-reference-metadata", type=Path)
    parser.add_argument("--scale-tolerance", type=float, default=0.15)
    parser.add_argument("--final-dir", type=Path)
    parser.add_argument("--final-prefix")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    component_mode = "largest" if args.kind == "body" else "all"
    align = args.align or ("feet" if args.kind == "body" else "center")

    try:
        result = process_action_sheet(
            args.source,
            args.out_dir,
            grid=args.grid,
            names=args.names,
            asset_id=args.asset_id,
            tag=args.tag,
            background=args.background,
            component_mode=component_mode,
            align=align,
            scale_reference_metadata=args.scale_reference_metadata,
            scale_tolerance=args.scale_tolerance,
            final_dir=args.final_dir,
            final_prefix=args.final_prefix,
            report=args.report,
        )
    except ActionProcessError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
