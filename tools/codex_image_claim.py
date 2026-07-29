#!/usr/bin/env python3
"""Claim a Codex-generated image from an explicit generated image path.

The caller must pass the concrete generated image path reported by Codex.
This script never scans Codex image directories or guesses the newest file.
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


def claim_codex_image(generated_path: str, output: Path, *, asset_id: str | None = None) -> dict[str, object]:
    source_path = _path_from_arg(generated_path)
    output = Path(output)
    if not source_path.exists():
        raise CodexImageClaimError(f"Generated image not found: {source_path}")
    if not source_path.is_file():
        raise CodexImageClaimError(f"Generated image is not a file: {source_path}")
    if source_path.resolve() == output.resolve():
        raise CodexImageClaimError(f"generated_path must not be the output path: {output}")

    image = _load_image(source_path)
    try:
        width, height = image.size
        mode = image.mode
        fmt = image.format
    finally:
        image.close()

    _copy_atomic(source_path, output)
    if not output.exists() or not output.is_file():
        raise CodexImageClaimError(f"Claimed image was not written: {output}")

    result: dict[str, object] = {
        "ok": True,
        "generated_path": str(source_path),
        "claimed_path": str(output),
        "exists": output.exists(),
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


def _reference_items(value: Any, *, item_label: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CodexImageClaimError(f"{item_label}.references must be a list")
    references: list[dict[str, str]] = []
    for index, reference in enumerate(value):
        label = f"{item_label}.references[{index}]"
        if not isinstance(reference, dict) or set(reference) != {"role", "path"}:
            raise CodexImageClaimError(
                f"{label} must contain exactly role and path"
            )
        role = _string(reference.get("role"), "role", item_label=label)
        if role not in {"canonical", "style", "screen"}:
            raise CodexImageClaimError(
                f"{label}.role must be canonical, style, or screen"
            )
        references.append({
            "role": role,
            "path": _string(reference.get("path"), "path", item_label=label),
        })
    return references


def _planned_items(plan: Any) -> dict[str, dict[str, Any]]:
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

    planned: dict[str, dict[str, Any]] = {}
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
        required_trace = item.get("require_provider_trace", False)
        if type(required_trace) is not bool:
            raise CodexImageClaimError(
                f"{label}.require_provider_trace must be a boolean"
            )
        references = _reference_items(item.get("references"), item_label=label)
        planned[asset_id] = {
            "asset_id": asset_id,
            "source_path": source_path,
            "references": references,
            "require_provider_trace": required_trace or bool(references),
        }
    return planned


def _reported_generated_paths(report: Any) -> dict[str, dict[str, Any]]:
    if isinstance(report, list):
        raw_items = report
    elif isinstance(report, dict):
        if report.get("ok") is False:
            raise CodexImageClaimError(f"Codex generation report failed: {report.get('error') or 'unknown error'}")
        failures = report.get("failures")
        if isinstance(failures, list) and failures:
            first = failures[0]
            if isinstance(first, dict):
                asset = first.get("asset_id") or "unknown asset"
                error = first.get("error") or "unknown error"
                raise CodexImageClaimError(f"Codex generation failed for {asset}: {error}")
            raise CodexImageClaimError("Codex generation report contains failures")
        raw_items = report.get("assets")
    else:
        raise CodexImageClaimError("Generation report must be a JSON object or array")

    if not isinstance(raw_items, list) or not raw_items:
        raise CodexImageClaimError("Generation report must contain a non-empty assets list")

    generated_paths: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise CodexImageClaimError(f"report asset {index} must be an object")
        label = f"report asset {index}"
        asset_id = _string(item.get("asset_id"), "asset_id", item_label=label)
        generated_path = _string(item.get("generated_path"), "generated_path", item_label=label)
        if asset_id in generated_paths:
            raise CodexImageClaimError(f"Duplicate reported asset_id: {asset_id}")
        generated_paths[asset_id] = {"generated_path": generated_path, "item": item}
    return generated_paths


def _provider_trace(
    planned: dict[str, Any], reported: dict[str, Any], *, asset_id: str
) -> dict[str, Any] | None:
    """Validate the image-generation evidence before a claimed source is accepted."""
    if not planned["require_provider_trace"]:
        return None
    trace = reported["item"].get("provider_trace")
    if not isinstance(trace, dict):
        raise CodexImageClaimError(
            f"Generation report for {asset_id} is missing provider_trace"
        )
    required_fields = (
        "provider", "coding_model", "reasoning", "tool_call_id",
        "image_model_identity", "referenced_image_paths",
    )
    for field in required_fields[:-1]:
        _string(trace.get(field), field, item_label=f"provider_trace for {asset_id}")
    if trace["provider"] != "codex":
        raise CodexImageClaimError(
            f"provider_trace for {asset_id}.provider must be codex"
        )
    image_model_identity = trace["image_model_identity"]
    if image_model_identity == "runtime_reported":
        _string(
            trace.get("image_model"),
            "image_model",
            item_label=f"provider_trace for {asset_id}",
        )
    elif image_model_identity != "not_exposed_by_subscription_runtime":
        raise CodexImageClaimError(
            f"provider_trace for {asset_id}.image_model_identity must be "
            "runtime_reported or not_exposed_by_subscription_runtime"
        )
    attachment_paths = trace.get("referenced_image_paths")
    if not isinstance(attachment_paths, list) or any(
        not isinstance(path, str) or not path.strip() for path in attachment_paths
    ):
        raise CodexImageClaimError(
            f"provider_trace for {asset_id}.referenced_image_paths must be a string list"
        )
    expected_paths = [reference["path"] for reference in planned["references"]]
    if attachment_paths != expected_paths:
        raise CodexImageClaimError(
            f"provider_trace for {asset_id} does not prove every planned reference attachment"
        )
    reported_references = _reference_items(
        reported["item"].get("references"), item_label=f"report asset {asset_id}"
    )
    if reported_references != planned["references"]:
        raise CodexImageClaimError(
            f"Generation report for {asset_id} does not preserve planned reference roles"
        )
    verified_trace = {
        field: trace[field]
        for field in required_fields
    }
    if image_model_identity == "runtime_reported":
        verified_trace["image_model"] = trace["image_model"]
    return verified_trace


def claim_codex_image_batch(
    plan_path: Path,
    report_path: Path,
    *,
    project_root: Path,
    out_report: Path | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    planned = _planned_items(_load_json(plan_path, "Plan"))
    generated_paths = _reported_generated_paths(_load_json(report_path, "Generation report"))

    unknown = sorted(set(generated_paths) - set(planned))
    if unknown:
        raise CodexImageClaimError(f"Generation report contains unknown asset_id: {', '.join(unknown)}")

    missing = sorted(set(planned) - set(generated_paths))
    if missing:
        raise CodexImageClaimError(f"Generation report is missing asset_id: {', '.join(missing)}")

    results = []
    for asset_id, item in planned.items():
        output = project_root / item["source_path"]
        reported = generated_paths[asset_id]
        trace = _provider_trace(item, reported, asset_id=asset_id)
        generated_path = _path_from_arg(reported["generated_path"])
        if generated_path.resolve() == output.resolve():
            raise CodexImageClaimError(
                f"generated_path for {asset_id} must not be the planned source_path: {output}"
            )
        result = claim_codex_image(str(generated_path), output, asset_id=asset_id)
        result["source_path"] = item["source_path"]
        if trace is not None:
            result["references"] = item["references"]
            result["provider_trace"] = trace
        results.append(result)

    batch_result = {
        "ok": True,
        "plan": str(plan_path),
        "generation_report": str(report_path),
        "assets": results,
    }
    if out_report is not None:
        batch_result["claim_report"] = str(out_report)
        _write_atomic_json(Path(out_report), batch_result)
    return batch_result


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Claim Codex generated image outputs"
    )
    parser.add_argument("--source", help="Codex generated image path")
    parser.add_argument("--out", help="Project-local claimed source image path")
    parser.add_argument("--asset-id", default=None, help="Optional asset id for JSON output")
    parser.add_argument("--plan", help="Planned generation batch JSON")
    parser.add_argument("--report", help="Codex generated-path report JSON")
    parser.add_argument("--project-root", default=".", help="Project root for relative batch source_path outputs")
    parser.add_argument("--out-report", help="Authoritative claim result JSON path")
    args = parser.parse_args()

    try:
        if args.plan or args.report:
            if args.source or args.out or args.asset_id:
                raise CodexImageClaimError("Batch mode cannot be combined with --source, --out, or --asset-id")
            if not args.plan or not args.report:
                raise CodexImageClaimError("Batch mode requires --plan and --report")
            if not args.out_report:
                raise CodexImageClaimError("Batch mode requires --out-report")
            result = claim_codex_image_batch(
                Path(args.plan),
                Path(args.report),
                project_root=Path(args.project_root),
                out_report=Path(args.out_report),
            )
        else:
            if args.out_report:
                raise CodexImageClaimError("Single-image mode cannot be combined with --out-report")
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
