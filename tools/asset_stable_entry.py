#!/usr/bin/env python3
"""Validate and serialize v1 generated-asset stable entries.

A stable entry is the single source of truth for one worker-consumable
generated asset. It stores stable identity plus the minimal contract a worker
needs: the production family, the source layout, an optional minimal Godot
artifact, and a processing status. It lives at::

    .godotmaker/asset-generation/entries/<tag>/<asset_id>.json

This is the v1.0.0 contract. The old ``runtime_artifact`` schema is not read,
migrated, or dual-written; entries carrying legacy fields fail with a clear
message and must be regenerated through ``/gm-asset``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

ENTRIES_ROOT = ".godotmaker/asset-generation/entries"

# Production families map one-to-one to the first-class asset skills.
PRODUCTION_FAMILIES = {
    "background-map",
    "character-bundle",
    "fx-bundle",
    "ui-kit",
    "card-kit",
    "compact-prop-pack",
    "platform-strip",
    "scene-prop-set",
    "screen-reference",
    "tileset",
}

# ``source_layout.type`` describes pixel organization, not a Godot artifact.
SOURCE_LAYOUT_TYPES = {
    "single",
    "grid_sheet",
    "region_atlas",
    "theme_recipe",
    "tile_atlas",
    "reference",
}

# Reference-only sources are never handed to workers as runtime game assets.
REFERENCE_LAYOUTS = {"reference"}

# Families whose assets are reference-only. A ``reference`` layout is legal only
# for these, and these families must use a ``reference`` layout. Binding the two
# closes the fail-open where a runtime family (e.g. ``character-bundle``) could
# declare a ``reference`` layout to slip an arbitrary path past the stable-dir
# constraint.
REFERENCE_FAMILIES = {"screen-reference"}

# Processing status maps to the L0-L4 readiness ladder.
PROCESSING_STATUSES = {
    "pending",       # L0 only; nothing produced yet
    "source_ready",  # L1 source generation and processing succeeded
    "compiled",      # L2 native Godot artifact compiled, not yet L3-L4 verified
    "ready",         # L0-L4 all passed; worker-consumable
    "failed",        # a stage failed
}

# Statuses that require a compiled ``godot_artifact`` for non-reference assets.
ARTIFACT_REQUIRED_STATUSES = {"compiled", "ready"}

# Reference-only entries do not enter the L0-L4 runtime ladder. They may be
# awaiting source generation, have a finalized source, or have failed; they can
# never be compiled or runtime-ready.
REFERENCE_PROCESSING_STATUSES = {"pending", "source_ready", "failed"}

# ``godot_artifact.type`` has the shape of a Godot ClassDB identifier, while
# the layout-to-type compatibility relation below is deliberately closed.
GODOT_TYPE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# The Godot resource types each non-reference layout may compile to. The
# compatibility relation is deliberately closed: Godot ClassDB identifiers are
# not a general allow-list. A ``StyleBoxTexture`` may use either a single image
# or a region from an atlas, while every other layout has one permitted result.
# A ``grid_sheet`` published as a plain ``Texture2D`` is a static image standing
# in for the ``SpriteFrames`` the worker was promised, and binding it yields a
# frozen sprite where an animation was specified. Declaring the source image as
# the artifact is the exact shortcut this mapping exists to reject, so a type
# that does not match its layout fails closed rather than reaching a worker.
LAYOUT_ARTIFACT_TYPES = {
    "single": ("Texture2D", "StyleBoxTexture"),
    "grid_sheet": ("SpriteFrames",),
    "region_atlas": ("AtlasTexture", "StyleBoxTexture"),
    "theme_recipe": ("Theme",),
    "tile_atlas": ("TileSet",),
}

# Any of these fields marks an old ``runtime_artifact`` manifest/entry.
LEGACY_FIELDS = {
    "runtime_artifact",
    "production_shape",
    "extraction_status",
    "runtime_role",
    "family",
    "final_path",
    "source_path",
}

# Characters that are illegal in a Windows filename or act as path separators /
# drive markers / alternate-data-stream selectors across platforms.
_RESERVED_PATH_CHARS = set('<>:"/\\|?*;')

# Windows reserved device basenames (case-insensitive, any extension).
_RESERVED_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_RES_PREFIX = "res://"

# Every worker-consumable generated file (source image, native Godot artifact,
# and required support files) lives under a deterministic, per-asset directory::
#
#     assets/generated/<production_family>/<asset_id>/
#
# Pinning outputs to this directory is what keeps timestamped, ``v2``, or
# ``final`` drift paths out of the runtime handoff: the location is derived from
# stable identity, so regeneration overwrites in place and never touches an
# unrelated asset's directory. Reference-only layouts are handed to nobody as a
# runtime game asset and keep their existing location outside this tree.
GENERATED_ROOT = "assets/generated"

# The generation workspace is temporary; no runtime handoff path may depend on
# it (design: "No consumer may depend on files under work/").
WORK_ROOT = ".godotmaker/asset-generation/work"

# Both nested contract objects hold exactly a type and a path. Internal detail
# (receipts, hashes, versions) belongs at the entry top level, never inside the
# worker-facing artifact.
SOURCE_LAYOUT_KEYS = {"type", "path"}
GODOT_ARTIFACT_KEYS = {"type", "path"}


class StableEntryError(Exception):
    """Raised when a stable entry is invalid."""


def is_schema_version(value: Any) -> bool:
    """Return True only for a strict JSON integer equal to the schema version.

    ``bool`` is a subclass of ``int`` and ``1.0 == 1``, so a plain ``== 1``
    would accept ``True`` and ``1.0``. Require an exact ``int`` type.
    """
    return type(value) is int and value == SCHEMA_VERSION


def _legacy_error(fields: set[str]) -> StableEntryError:
    listed = ", ".join(sorted(fields))
    return StableEntryError(
        f"Legacy runtime_artifact schema detected (fields: {listed}); "
        "v1.0.0 provides no migration or compatibility read. "
        "Regenerate this asset through /gm-asset."
    )


def _reject_legacy(data: dict[str, Any]) -> None:
    present = LEGACY_FIELDS.intersection(data.keys())
    if present:
        raise _legacy_error(present)


def _non_empty_string(data: dict[str, Any], field: str, label: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise StableEntryError(f"{label} must be a non-empty string")
    return value


def _safe_identifier(value: str, label: str) -> str:
    """Require a single cross-platform-safe path segment.

    ``tag`` and ``asset_id`` become one directory / file-stem component of the
    canonical entry path, so they must map to exactly that segment on every OS.
    """
    if value in (".", ".."):
        raise StableEntryError(f"{label} must not be '.' or '..'")
    for char in value:
        if char in _RESERVED_PATH_CHARS or ord(char) < 32:
            raise StableEntryError(
                f"{label} must be a single safe path segment "
                "(no path separators, ':', ';' or reserved characters)"
            )
    if value != value.strip() or value.endswith("."):
        raise StableEntryError(
            f"{label} must not have leading/trailing spaces or a trailing dot"
        )
    if value.split(".", 1)[0].upper() in _RESERVED_DEVICE_NAMES:
        raise StableEntryError(f"{label} must not be a Windows reserved device name")
    return value


def _reject_extra_keys(data: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(data.keys()) - allowed
    if extra:
        listed = ", ".join(sorted(extra))
        raise StableEntryError(f"{label} must only hold type and path; unexpected fields: {listed}")


def _check_res_path(value: str, label: str) -> str:
    if not value.startswith(_RES_PREFIX):
        raise StableEntryError(f"{label} must be a res:// path")
    remainder = value[len(_RES_PREFIX):]
    if not remainder.strip():
        raise StableEntryError(f"{label} must name a resource under res://")
    if "\\" in remainder:
        raise StableEntryError(f"{label} must use forward slashes")
    # Must be a clean, project-relative resource path: no absolute/UNC anchor,
    # no drive letter, no empty (``//``), ``.`` or ``..`` segments.
    segments = remainder.split("/")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise StableEntryError(
                f"{label} must be a relative resource path with no empty, '.' or '..' segments"
            )
        if ":" in segment:
            raise StableEntryError(f"{label} must not contain a drive letter or scheme")
    return value


def _resolve_res_path(project_root: Path, res_path: str) -> Path:
    return project_root / res_path[len(_RES_PREFIX):]


def _assert_within_root(project_root: Path, resolved: Path, label: str) -> None:
    root = project_root.resolve()
    if not resolved.resolve().is_relative_to(root):
        raise StableEntryError(f"{label} resolves outside the project root")


def stable_output_dir(production_family: str, asset_id: str) -> str:
    """Return the canonical project-relative output directory for one asset.

    The directory is derived only from stable identity, so it is deterministic
    and unique per ``(production_family, asset_id)``. Every source image, native
    Godot artifact, and support file for the asset must live under it.
    """
    if production_family not in PRODUCTION_FAMILIES:
        raise StableEntryError(f"production_family is not allowed: {production_family}")
    _safe_identifier(asset_id, "asset_id")
    return f"{GENERATED_ROOT}/{production_family}/{asset_id}"


def stable_output_res_path(production_family: str, asset_id: str) -> str:
    """Return the ``res://`` form of the asset's canonical output directory."""
    return _RES_PREFIX + stable_output_dir(production_family, asset_id)


def check_output_path(
    value: str,
    *,
    production_family: str,
    asset_id: str,
    label: str,
) -> str:
    """Require a ``res://`` file strictly under the asset's stable directory.

    On top of ``_check_res_path`` cleanliness this enforces that ``value`` names
    a file under ``assets/generated/<production_family>/<asset_id>/`` and never
    depends on the temporary generation ``work/`` workspace. A drifting
    location (``v2``, ``final``, a timestamped or unrelated directory) cannot
    satisfy the exact-prefix requirement, so it fails closed.
    """
    _check_res_path(value, label)
    remainder = value[len(_RES_PREFIX):]
    if remainder == WORK_ROOT or remainder.startswith(WORK_ROOT + "/"):
        raise StableEntryError(
            f"{label} must not depend on the generation work/ workspace"
        )
    stable_dir = stable_output_dir(production_family, asset_id)
    # A clean res path never ends in ``/`` (``_check_res_path`` rejects an empty
    # last segment), so an exact-prefix match with the trailing slash guarantees
    # a real file strictly under the directory, not the directory itself.
    if not remainder.startswith(stable_dir + "/"):
        raise StableEntryError(f"{label} must be a file under res://{stable_dir}/")
    return value


def check_support_files(
    paths: Any,
    *,
    production_family: str,
    asset_id: str,
) -> list[str]:
    """Validate that every required support file is under the stable directory."""
    if not isinstance(paths, (list, tuple)):
        raise StableEntryError("support files must be a list of res:// paths")
    validated: list[str] = []
    for index, path in enumerate(paths):
        if not isinstance(path, str) or not path.strip():
            raise StableEntryError(f"support_files[{index}] must be a non-empty string")
        check_output_path(
            path,
            production_family=production_family,
            asset_id=asset_id,
            label=f"support_files[{index}]",
        )
        validated.append(path)
    return validated


def assert_within_output_dir(
    project_root: Path,
    target: Path | str,
    *,
    production_family: str,
    asset_id: str,
    label: str = "output",
) -> Path:
    """Assert an on-disk write target sits strictly under the asset's stable dir.

    This is the write-time counterpart of ``check_output_path``: generation and
    finalize tools call it before writing so a run can only ever touch its own
    ``assets/generated/<production_family>/<asset_id>/`` directory, never an
    unrelated asset's. A relative ``target`` is resolved against ``project_root``.
    Symlinks are followed (``resolve``), so an in-tree link pointing elsewhere is
    rejected too.
    """
    root = Path(project_root).resolve()
    relative_dir = stable_output_dir(production_family, asset_id)
    stable = (root / relative_dir).resolve()
    # The stable directory itself must stay inside the project. Checking only
    # ``resolved`` against a resolved ``stable`` is not enough: if the stable
    # directory (or an ancestor) is a symlink pointing out of the project, both
    # it and the target resolve outside and the containment check passes while
    # the write still escapes. Anchor ``stable`` to ``root`` first.
    if stable != root and not stable.is_relative_to(root):
        raise StableEntryError(
            f"{label} stable directory resolves outside the project root"
        )
    resolved = Path(target)
    if not resolved.is_absolute():
        resolved = root / resolved
    resolved = resolved.resolve()
    if resolved == stable or not resolved.is_relative_to(stable):
        raise StableEntryError(f"{label} must be written under {relative_dir}/")
    return resolved


def _validate_source_layout(
    data: dict[str, Any],
    *,
    production_family: str,
    asset_id: str,
) -> tuple[str, str]:
    layout = data.get("source_layout")
    if not isinstance(layout, dict):
        raise StableEntryError("source_layout must be an object")
    _reject_legacy(layout)
    _reject_extra_keys(layout, SOURCE_LAYOUT_KEYS, "source_layout")
    layout_type = _non_empty_string(layout, "type", "source_layout.type")
    if layout_type not in SOURCE_LAYOUT_TYPES:
        raise StableEntryError(f"source_layout.type is not allowed: {layout_type}")
    layout_path = _non_empty_string(layout, "path", "source_layout.path")
    if layout_type in REFERENCE_LAYOUTS:
        # A reference is never handed to a worker as a runtime game asset, so it
        # falls outside the stable generated tree; only res-path cleanliness
        # applies.
        _check_res_path(layout_path, "source_layout.path")
    else:
        check_output_path(
            layout_path,
            production_family=production_family,
            asset_id=asset_id,
            label="source_layout.path",
        )
    return layout_type, layout_path


def _validate_godot_artifact(
    data: dict[str, Any],
    *,
    layout_type: str,
    processing_status: str,
    production_family: str,
    asset_id: str,
) -> tuple[str, str] | None:
    artifact = data.get("godot_artifact")
    is_reference = layout_type in REFERENCE_LAYOUTS

    if artifact is None:
        if is_reference:
            return None
        if processing_status in ARTIFACT_REQUIRED_STATUSES:
            raise StableEntryError(
                f"godot_artifact is required when processing_status is {processing_status}"
            )
        return None

    if is_reference:
        raise StableEntryError(
            "godot_artifact must be absent for a reference source_layout"
        )
    if not isinstance(artifact, dict):
        raise StableEntryError("godot_artifact must be an object or null")
    _reject_legacy(artifact)
    _reject_extra_keys(artifact, GODOT_ARTIFACT_KEYS, "godot_artifact")

    artifact_type = _non_empty_string(artifact, "type", "godot_artifact.type")
    if not GODOT_TYPE_PATTERN.match(artifact_type):
        raise StableEntryError(
            "godot_artifact.type must be a Godot ClassDB type identifier"
        )
    allowed_types = LAYOUT_ARTIFACT_TYPES[layout_type]
    if artifact_type not in allowed_types:
        raise StableEntryError(
            f"godot_artifact.type for a {layout_type} source_layout must be "
            f"one of: {', '.join(allowed_types)}; not {artifact_type}"
        )
    artifact_path = _non_empty_string(artifact, "path", "godot_artifact.path")
    check_output_path(
        artifact_path,
        production_family=production_family,
        asset_id=asset_id,
        label="godot_artifact.path",
    )
    return artifact_type, artifact_path


def validate_entry(
    data: Any,
    *,
    project_root: Path | None = None,
    check_files: bool = False,
) -> dict[str, Any]:
    """Validate one stable entry object and return it unchanged."""
    if not isinstance(data, dict):
        raise StableEntryError("Stable entry must be a JSON object")

    _reject_legacy(data)

    if not is_schema_version(data.get("version")):
        raise StableEntryError(f"Stable entry version must be integer {SCHEMA_VERSION}")

    asset_id = _non_empty_string(data, "asset_id", "asset_id")
    _safe_identifier(asset_id, "asset_id")
    _safe_identifier(_non_empty_string(data, "tag", "tag"), "tag")

    family = _non_empty_string(data, "production_family", "production_family")
    if family not in PRODUCTION_FAMILIES:
        raise StableEntryError(f"production_family is not allowed: {family}")

    processing_status = _non_empty_string(
        data, "processing_status", "processing_status"
    )
    if processing_status not in PROCESSING_STATUSES:
        raise StableEntryError(
            f"processing_status is not allowed: {processing_status}"
        )

    layout_type, layout_path = _validate_source_layout(
        data, production_family=family, asset_id=asset_id
    )
    # Bind reference layout and reference family so neither can be used to
    # bypass the other's contract.
    if layout_type in REFERENCE_LAYOUTS and family not in REFERENCE_FAMILIES:
        raise StableEntryError(
            "a reference source_layout is only allowed for a reference family "
            f"({', '.join(sorted(REFERENCE_FAMILIES))})"
        )
    if family in REFERENCE_FAMILIES and layout_type not in REFERENCE_LAYOUTS:
        raise StableEntryError(
            f"production_family {family} must use a reference source_layout"
        )
    if (
        layout_type in REFERENCE_LAYOUTS
        and processing_status not in REFERENCE_PROCESSING_STATUSES
    ):
        allowed = ", ".join(sorted(REFERENCE_PROCESSING_STATUSES))
        raise StableEntryError(
            "processing_status for a reference source_layout must be one of: "
            f"{allowed}; not {processing_status}"
        )
    artifact = _validate_godot_artifact(
        data,
        layout_type=layout_type,
        processing_status=processing_status,
        production_family=family,
        asset_id=asset_id,
    )

    # Whenever a project root is supplied, resolve-and-contain the referenced
    # paths even if existence is not being checked. The root-index registration
    # path (``check_index(..., check_entries=True)``) calls this with only a
    # project root, so containment must not be gated behind ``check_files`` or a
    # symlinked ``assets/generated`` could pass registration.
    if project_root is not None:
        root = Path(project_root)
        source_file = _resolve_res_path(root, layout_path)
        _assert_within_root(root, source_file, "source_layout.path")
        if check_files and not source_file.exists():
            raise StableEntryError(f"source_layout.path not found: {layout_path}")
        if artifact is not None:
            _, artifact_path = artifact
            artifact_file = _resolve_res_path(root, artifact_path)
            _assert_within_root(root, artifact_file, "godot_artifact.path")
            if check_files and not artifact_file.exists():
                raise StableEntryError(
                    f"godot_artifact.path not found: {artifact_path}"
                )
    elif check_files:
        raise StableEntryError("project_root is required to check files")

    return data


def entry_relative_path(tag: str, asset_id: str) -> str:
    """Return the canonical entry path for one ``(tag, asset_id)`` pair."""
    _safe_identifier(tag, "tag")
    _safe_identifier(asset_id, "asset_id")
    return f"{ENTRIES_ROOT}/{tag}/{asset_id}.json"


def _write_atomic(path: Path, data: dict[str, Any]) -> None:
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


def write_entry(
    entry: dict[str, Any],
    *,
    project_root: Path,
    check_files: bool = False,
) -> dict[str, Any]:
    """Validate and serialize one stable entry to its canonical path."""
    validated = validate_entry(entry, project_root=project_root, check_files=check_files)
    relative = entry_relative_path(validated["tag"], validated["asset_id"])
    target = Path(project_root) / relative
    _write_atomic(target, validated)
    return {
        "ok": True,
        "path": relative,
        "asset_id": validated["asset_id"],
        "tag": validated["tag"],
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - surfaced as a tool error
        raise StableEntryError(f"Invalid JSON: {path}") from exc


def _main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and serialize a v1 generated-asset stable entry"
    )
    parser.add_argument("entry", type=Path, help="Stable entry JSON file")
    parser.add_argument("--project-root", default=".", type=Path)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Serialize the entry to its canonical entries/<tag>/<asset_id>.json path",
    )
    parser.add_argument(
        "--check-files",
        action="store_true",
        help="Verify referenced source and artifact files exist",
    )
    args = parser.parse_args()

    try:
        data = _load_json(args.entry)
        if args.write:
            result = write_entry(
                data if isinstance(data, dict) else {},
                project_root=args.project_root,
                check_files=args.check_files,
            )
        else:
            validate_entry(
                data, project_root=args.project_root, check_files=args.check_files
            )
            result = {"ok": True, "path": str(args.entry)}
    except StableEntryError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
