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
from typing import Any
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


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CodexImageClaimError(f"{label} file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CodexImageClaimError(f"{label} file is not valid JSON: {path}") from exc


def _string(value: Any, field: str, *, item_label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CodexImageClaimError(f"{item_label}.{field} must be a non-empty string")
    return value.strip()


def _planned_items(plan: Any) -> dict[str, dict[str, str]]:
    if not isinstance(plan, dict):
        raise CodexImageClaimError("Plan must be a JSON object")

    raw_items: list[Any] = []
    if isinstance(plan.get("items"), list):
        raw_items.extend(plan["items"])
    if plan.get("anchor_item") is not None:
        raw_items.append(plan["anchor_item"])
    if isinstance(plan.get("parallel_items"), list):
        raw_items.extend(plan["parallel_items"])

    if not raw_items:
        raise CodexImageClaimError("Plan must contain items, anchor_item, or parallel_items")

    planned: dict[str, dict[str, str]] = {}
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise CodexImageClaimError(f"plan item {index} must be an object")
        label = f"plan item {index}"
        asset_id = _string(item.get("asset_id"), "asset_id", item_label=label)
        source_path = _string(item.get("source_path"), "source_path", item_label=label)
        source = Path(source_path)
        if source.is_absolute() or ".." in source.parts:
            raise CodexImageClaimError(f"{label}.source_path must stay within the project")
        if asset_id in planned:
            raise CodexImageClaimError(f"Duplicate planned asset_id: {asset_id}")
        planned[asset_id] = {"asset_id": asset_id, "source_path": source_path}
    return planned


def _reported_saved_paths(report: Any) -> dict[str, str]:
    if isinstance(report, list):
        raw_items = report
    elif isinstance(report, dict):
        if report.get("ok") is False:
            raise CodexImageClaimError(f"Codex saved-path report failed: {report.get('error') or 'unknown error'}")
        failures = report.get("failures")
        if isinstance(failures, list) and failures:
            first = failures[0]
            if isinstance(first, dict):
                asset = first.get("asset_id") or "unknown asset"
                error = first.get("error") or "unknown error"
                raise CodexImageClaimError(f"Codex generation failed for {asset}: {error}")
            raise CodexImageClaimError("Codex saved-path report contains failures")
        raw_items = report.get("assets")
    else:
        raise CodexImageClaimError("Saved-path report must be a JSON object or array")

    if not isinstance(raw_items, list) or not raw_items:
        raise CodexImageClaimError("Saved-path report must contain a non-empty assets list")

    saved_paths: dict[str, str] = {}
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise CodexImageClaimError(f"report asset {index} must be an object")
        label = f"report asset {index}"
        asset_id = _string(item.get("asset_id"), "asset_id", item_label=label)
        saved_path = _string(item.get("saved_path"), "saved_path", item_label=label)
        if asset_id in saved_paths:
            raise CodexImageClaimError(f"Duplicate reported asset_id: {asset_id}")
        saved_paths[asset_id] = saved_path
    return saved_paths


def claim_codex_image_batch(plan_path: Path, report_path: Path, *, project_root: Path) -> dict[str, Any]:
    planned = _planned_items(_load_json(plan_path, "Plan"))
    saved_paths = _reported_saved_paths(_load_json(report_path, "Saved-path report"))

    unknown = sorted(set(saved_paths) - set(planned))
    if unknown:
        raise CodexImageClaimError(f"Saved-path report contains unknown asset_id: {', '.join(unknown)}")

    missing = sorted(set(planned) - set(saved_paths))
    if missing:
        raise CodexImageClaimError(f"Saved-path report is missing asset_id: {', '.join(missing)}")

    results = []
    for asset_id, item in planned.items():
        output = project_root / item["source_path"]
        result = claim_codex_image(saved_paths[asset_id], output, asset_id=asset_id)
        result["source_path"] = item["source_path"]
        results.append(result)

    return {
        "ok": True,
        "plan": str(plan_path),
        "report": str(report_path),
        "assets": results,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Claim Codex ImageGenerationEnd saved_path outputs"
    )
    parser.add_argument("--source", help="Codex ImageGenerationEnd saved_path")
    parser.add_argument("--out", help="Project-local claimed source image path")
    parser.add_argument("--asset-id", default=None, help="Optional asset id for JSON output")
    parser.add_argument("--plan", help="Planned generation batch JSON")
    parser.add_argument("--report", help="Codex saved-path report JSON")
    parser.add_argument("--project-root", default=".", help="Project root for relative batch source_path outputs")
    args = parser.parse_args()

    try:
        if args.plan or args.report:
            if args.source or args.out or args.asset_id:
                raise CodexImageClaimError("Batch mode cannot be combined with --source, --out, or --asset-id")
            if not args.plan or not args.report:
                raise CodexImageClaimError("Batch mode requires --plan and --report")
            result = claim_codex_image_batch(
                Path(args.plan),
                Path(args.report),
                project_root=Path(args.project_root),
            )
        else:
            if not args.source or not args.out:
                raise CodexImageClaimError("Single-image mode requires --source and --out")
            result = claim_codex_image(args.source, Path(args.out), asset_id=args.asset_id)
    except (CodexImageClaimError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
