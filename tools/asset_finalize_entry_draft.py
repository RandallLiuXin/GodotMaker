#!/usr/bin/env python3
"""Build a v1 stable-entry draft from an ``asset_image_finalize.py`` report.

Every production path that ends in one finalized image registers through this
tool: screen references, backgrounds and parallax plates, and single card or
portrait frames. Together with ``asset_action_entry_draft.py`` and
``asset_curation_entry_draft.py`` it means no production unit needs a
hand-written draft.

The checks that matter for a finalized image stay mechanical here:

- the finalize run succeeded and actually validated the aspect
  (``--require-aspect``), which every one of these units requires before the
  image is accepted;
- the report's own label identifies the same asset the draft is being built for,
  so a report from a different image cannot be pointed at this entry;
- the finalized file exists, and sits where its layout demands.

That last rule matters most for references. A ``reference`` layout is the single
case the schema lets out of the stable generated tree and out of the
``godot_artifact`` requirement, so an unconstrained reference path is a way to
register a scratch source — or a real runtime asset — while skipping compilation
entirely. Pinning references to ``references/`` and everything else to the stable
output directory closes that.

The layout is derived from the production family rather than passed in: the
schema already binds reference families and reference layouts to each other in
both directions, so a flag could only introduce a contradiction.

``background-map`` is the one family here that compiles a native artifact. Its
PNG *is* the ``Texture2D`` Godot imports, so the finalized image and the
artifact are the same file and no ``.tres`` wraps it. Supplying that Skill's
passing result with ``--result`` binds it to the image this run finalized, runs
the declared ``single -> Texture2D`` route, and writes the ``ready`` entry from
the compiler's own artifact. The Skill holds a passing L0-L4 result by the time
it drafts, so there is no ``compiled`` stage to promote from and no window in
which the registered bytes could drift from the validated ones.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asset_runtime_path import ensure_asset_runtime_on_path
from asset_skill_contract_check import AssetContractError, check_result
from asset_stable_entry import (
    GENERATED_ROOT,
    PRODUCTION_FAMILIES,
    REFERENCE_FAMILIES,
    SCHEMA_VERSION,
    StableEntryError,
    check_output_path,
    stable_output_dir,
    validate_entry,
)

# Published projects keep this runtime at .godotmaker/asset-runtime, not under
# skills/assets/. Resolving it by hand here breaks every published run.
SHARED_ROOT = ensure_asset_runtime_on_path()
from asset_compiler import CompileRequest, CompilerError, build_default_registry  # noqa: E402

REFERENCES_ROOT = "references"
DRAFT_STATUS = "source_ready"
READY_STATUS = "ready"

# The one finalize-driven family with a declared native compiler route and its
# own L0-L4 runner. Every other family on this builder stops at source_ready.
COMPILED_FAMILY = "background-map"
COMPILED_LAYOUT = "single"
COMPILED_ARTIFACT_TYPE = "Texture2D"
LEVELS = ("L0", "L1", "L2", "L3", "L4")


class FinalizeEntryDraftError(Exception):
    """Raised when a finalized-image stable-entry draft cannot be built."""


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced as a tool error
        raise FinalizeEntryDraftError(f"{label} is not readable JSON: {path}") from exc
    if not isinstance(data, dict):
        raise FinalizeEntryDraftError(f"{label} must be a JSON object: {path}")
    return data


def _string(data: dict[str, Any], field: str, label: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise FinalizeEntryDraftError(f"{label}.{field} must be a non-empty string")
    return value


def _number(data: dict[str, Any], field: str, label: str) -> float:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FinalizeEntryDraftError(f"{label}.{field} must be a number")
    return float(value)


def _project_relative(raw_path: str, project_root: Path) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(Path(project_root).resolve()).as_posix()
        except ValueError as exc:
            raise FinalizeEntryDraftError(
                f"path resolves outside the project root: {raw_path}"
            ) from exc
    return path.as_posix()


def _clean_relative(relative: str) -> str:
    if "\\" in relative:
        raise FinalizeEntryDraftError("finalized path must use forward slashes")
    if any(segment in ("", ".", "..") for segment in relative.split("/")):
        raise FinalizeEntryDraftError(
            "finalized path must have no empty, '.' or '..' segments"
        )
    return relative


def _reference_res_path(relative: str) -> str:
    _clean_relative(relative)
    if relative.startswith(f"{GENERATED_ROOT}/"):
        raise FinalizeEntryDraftError(
            f"a reference must not live under {GENERATED_ROOT}/; "
            "that tree is for compiled runtime assets"
        )
    if not relative.startswith(f"{REFERENCES_ROOT}/"):
        raise FinalizeEntryDraftError(
            f"reference path must be a file under {REFERENCES_ROOT}/"
        )
    return f"res://{relative}"


def _runtime_res_path(relative: str, *, production_family: str, asset_id: str) -> str:
    _clean_relative(relative)
    try:
        return check_output_path(
            f"res://{relative}",
            production_family=production_family,
            asset_id=asset_id,
            label="finalized path",
        )
    except StableEntryError as exc:
        raise FinalizeEntryDraftError(str(exc)) from exc


def _check_compiled_result(result_path: Path, *, source_path: str) -> None:
    """Bind a passing background-map result to the image this run finalized."""
    result = _load_object(result_path, "result")
    try:
        check_result(result)
    except AssetContractError as exc:
        raise FinalizeEntryDraftError(str(exc)) from exc
    if result["asset_type"] != COMPILED_FAMILY:
        raise FinalizeEntryDraftError(
            f"--result must be a {COMPILED_FAMILY} result, not {result['asset_type']}"
        )

    # One scenic image is one runtime resource. A second output would reach a
    # worker as a rival texture for the same asset.
    runtime = [item for item in result["outputs"] if item.get("role") == "runtime"]
    if len(result["outputs"]) != 1 or len(runtime) != 1:
        raise FinalizeEntryDraftError(
            f"{COMPILED_FAMILY} result must expose exactly one runtime output"
        )
    if (
        runtime[0].get("path") != source_path
        or runtime[0].get("godot_type") != COMPILED_ARTIFACT_TYPE
    ):
        raise FinalizeEntryDraftError(
            "result runtime output must be the finalized stable "
            f"{COMPILED_ARTIFACT_TYPE} path"
        )
    # The runtime output alone proves some image was validated, never which file
    # carried the `single` layout, so a result about another asset's image would
    # otherwise register this one.
    if result["sources"] != [{"path": source_path, "layout": COMPILED_LAYOUT}]:
        raise FinalizeEntryDraftError(
            "result single source must be the finalized stable image"
        )

    # L5 is a legal level of the shared contract; require L0-L4 to have passed
    # rather than demanding the level map contain nothing else.
    validation = result["validation"]
    levels = validation.get("levels")
    if not isinstance(levels, dict):
        raise FinalizeEntryDraftError(
            "result must have passed L0-L4 before a ready entry is drafted; "
            "no explicit validation levels were reported"
        )
    unpassed = [level for level in LEVELS if levels.get(level) is not True]
    if unpassed:
        raise FinalizeEntryDraftError(
            "result must have passed L0-L4 before a ready entry is drafted; "
            f"not passing: {', '.join(unpassed)}"
        )
    # A result may pass every runtime level and still declare itself failed —
    # an L5 finding, or a note the Skill stopped on. Registering it anyway would
    # promote a delivery its own producer refused to stand behind.
    if validation.get("passed") is not True:
        raise FinalizeEntryDraftError(
            "result must have passed L0-L4 before a ready entry is drafted; "
            "validation.passed is not true"
        )


def _compiled_artifact(
    source_ready: dict[str, Any], *, result_path: Path, project_root: Path
) -> dict[str, Any]:
    """Return the ready entry for a validated background-map delivery."""
    asset_id = source_ready["asset_id"]
    if source_ready["production_family"] != COMPILED_FAMILY:
        raise FinalizeEntryDraftError(
            f"--result is only supported for {COMPILED_FAMILY}; "
            f"{source_ready['production_family']} compiles no Godot artifact here"
        )
    source_path = source_ready["source_layout"]["path"]
    expected = f"res://{stable_output_dir(COMPILED_FAMILY, asset_id)}/{asset_id}.png"
    if source_path != expected:
        raise FinalizeEntryDraftError(
            f"{COMPILED_FAMILY} must finalize into its stable {asset_id}.png "
            f"before a ready entry: {source_path}"
        )
    _check_compiled_result(result_path, source_path=source_path)

    # The artifact is the compiler's, not this builder's: the registry is what
    # decides a PNG really is the Texture2D Godot imports for a `single` layout.
    try:
        compiled = build_default_registry().compile(
            CompileRequest(
                COMPILED_FAMILY,
                asset_id,
                COMPILED_LAYOUT,
                source_path,
                COMPILED_ARTIFACT_TYPE,
                source_path,
                Path(project_root),
            )
        )
    except (CompilerError, StableEntryError) as exc:
        raise FinalizeEntryDraftError(str(exc)) from exc

    return {
        **source_ready,
        "godot_artifact": compiled.godot_artifact.to_dict(),
        "processing_status": READY_STATUS,
    }


def build_finalize_entry_draft(
    finalize_report: Path,
    *,
    asset_id: str,
    tag: str,
    production_family: str,
    project_root: Path,
    result_path: Path | None = None,
) -> dict[str, Any]:
    """Validate a finalize report and return the draft stable entry.

    Without ``result_path`` the entry stops at ``source_ready``. Supplying the
    ``background-map`` Skill's passing result compiles its native
    ``single -> Texture2D`` route and returns the ``ready`` entry instead.
    """
    if not asset_id.strip():
        raise FinalizeEntryDraftError("--asset-id must be a non-empty string")
    if not tag.strip():
        raise FinalizeEntryDraftError("--tag must be a non-empty string")
    if production_family not in PRODUCTION_FAMILIES:
        raise FinalizeEntryDraftError(
            f"production_family is not allowed: {production_family}"
        )
    is_reference = production_family in REFERENCE_FAMILIES

    report = _load_object(finalize_report, "finalize report")
    if report.get("ok") is not True:
        raise FinalizeEntryDraftError("finalize report must report ok: true")

    # `--require-aspect` is what every finalize-driven production unit demands
    # before the image is accepted; its absence means the check never ran.
    if "required_aspect" not in report:
        raise FinalizeEntryDraftError(
            "finalize report has no required_aspect; rerun asset_image_finalize.py "
            "with --require-aspect"
        )
    delta = _number(report, "aspect_delta", "finalize report")
    tolerance = _number(report, "aspect_tolerance", "finalize report")
    if delta > tolerance:
        raise FinalizeEntryDraftError(
            f"finalize report aspect_delta {delta} exceeds tolerance {tolerance}"
        )

    # Cross-bind the report to this asset so a report for a different image
    # cannot be reused to register this one.
    reported_id = report.get("asset_id") or report.get("label")
    if not isinstance(reported_id, str) or not reported_id.strip():
        raise FinalizeEntryDraftError(
            "finalize report has no asset label; rerun asset_image_finalize.py "
            "with --label <asset_id>"
        )
    if reported_id != asset_id:
        raise FinalizeEntryDraftError(
            f"finalize report is for {reported_id}, not {asset_id}"
        )

    relative = _project_relative(
        _string(report, "path", "finalize report"), project_root
    )
    if is_reference:
        layout_type = "reference"
        res_path = _reference_res_path(relative)
    else:
        layout_type = "single"
        res_path = _runtime_res_path(
            relative, production_family=production_family, asset_id=asset_id
        )
    if not (Path(project_root) / relative).is_file():
        raise FinalizeEntryDraftError(f"finalized file not found: {relative}")

    entry = {
        "version": SCHEMA_VERSION,
        "asset_id": asset_id,
        "tag": tag,
        "production_family": production_family,
        "source_layout": {"type": layout_type, "path": res_path},
        "processing_status": DRAFT_STATUS,
    }
    if result_path is not None:
        entry = _compiled_artifact(
            entry, result_path=result_path, project_root=project_root
        )
    try:
        validate_entry(entry, project_root=Path(project_root), check_files=True)
    except StableEntryError as exc:
        raise FinalizeEntryDraftError(str(exc)) from exc
    return entry


def write_finalize_entry_draft(
    finalize_report: Path,
    *,
    asset_id: str,
    tag: str,
    production_family: str,
    project_root: Path,
    out: Path,
    result_path: Path | None = None,
) -> dict[str, Any]:
    entry = build_finalize_entry_draft(
        finalize_report,
        asset_id=asset_id,
        tag=tag,
        production_family=production_family,
        project_root=project_root,
        result_path=result_path,
    )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "draft": str(out),
        "asset_id": asset_id,
        "tag": tag,
        "source_layout": entry["source_layout"]["type"],
        "path": entry["source_layout"]["path"],
        "processing_status": entry["processing_status"],
    }


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a v1 stable-entry draft from an asset_image_finalize.py report"
    )
    parser.add_argument(
        "--finalize-report",
        required=True,
        type=Path,
        help="JSON report printed by asset_image_finalize.py",
    )
    parser.add_argument(
        "--result",
        type=Path,
        help=(
            "Passing background-map Skill result; compiles its single -> "
            "Texture2D route and writes a ready entry instead of source_ready"
        ),
    )
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--production-family", required=True)
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    try:
        result = write_finalize_entry_draft(
            args.finalize_report,
            asset_id=args.asset_id,
            tag=args.tag,
            production_family=args.production_family,
            project_root=args.project_root,
            out=args.out,
            result_path=args.result,
        )
    except FinalizeEntryDraftError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
