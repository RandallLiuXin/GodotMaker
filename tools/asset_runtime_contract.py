#!/usr/bin/env python3
"""Validate and serialize v1 generated-asset stable entries.

A runtime record is the single source of truth for one worker-consumable
generated asset. It stores stable identity plus the minimal contract a worker
needs: the production family, the source layout, an optional minimal Godot
artifact, and a processing status. It lives at::

    .godotmaker/asset-generation/entries/<tag>/<asset_id>.json

This is the v1.0.0 contract. The old ``runtime_artifact`` schema is not read,
migrated, or dual-written; entries carrying legacy fields fail with a clear
message and must be regenerated through ``/gm-asset``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from asset_family_registry import FAMILY_NAMES, REFERENCE_FAMILY_NAMES

SCHEMA_VERSION = 1

ENTRIES_ROOT = ".godotmaker/asset-generation/entries"

# Production families map one-to-one to the first-class asset skills. The list
# lives in ``asset_family_registry`` together with each family's layout,
# artifact, adapter, and terminal-status semantics; re-declaring the names here
# is what let an advertised family drift away from its registration chain.
PRODUCTION_FAMILIES = set(FAMILY_NAMES)

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

# Families whose one production delivers several independently worker-consumable
# runtime resources out of a single shared output directory. Their logical
# entries carry ``bundle_id`` plus a ``<bundle_id>--<logical_output_id>``
# ``asset_id``; every other family owns its directory alone.
BUNDLE_FAMILIES = {"card-kit", "compact-prop-pack", "platform-strip", "ui-kit"}

# Families whose assets are reference-only. A ``reference`` layout is legal only
# for these, and these families must use a ``reference`` layout. Binding the two
# closes the fail-open where a runtime family (e.g. ``character-bundle``) could
# declare a ``reference`` layout to slip an arbitrary path past the stable-dir
# constraint.
REFERENCE_FAMILIES = set(REFERENCE_FAMILY_NAMES)

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


class RuntimeContractError(Exception):
    """Raised when a runtime record is invalid."""


def is_schema_version(value: Any) -> bool:
    """Return True only for a strict JSON integer equal to the schema version.

    ``bool`` is a subclass of ``int`` and ``1.0 == 1``, so a plain ``== 1``
    would accept ``True`` and ``1.0``. Require an exact ``int`` type.
    """
    return type(value) is int and value == SCHEMA_VERSION


def _legacy_error(fields: set[str]) -> RuntimeContractError:
    listed = ", ".join(sorted(fields))
    return RuntimeContractError(
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
        raise RuntimeContractError(f"{label} must be a non-empty string")
    return value


def _safe_identifier(value: str, label: str) -> str:
    """Require a single cross-platform-safe path segment.

    ``tag`` and ``asset_id`` become one directory / file-stem component of the
    canonical entry path, so they must map to exactly that segment on every OS.
    """
    if value in (".", ".."):
        raise RuntimeContractError(f"{label} must not be '.' or '..'")
    for char in value:
        if char in _RESERVED_PATH_CHARS or ord(char) < 32:
            raise RuntimeContractError(
                f"{label} must be a single safe path segment "
                "(no path separators, ':', ';' or reserved characters)"
            )
    if value != value.strip() or value.endswith("."):
        raise RuntimeContractError(
            f"{label} must not have leading/trailing spaces or a trailing dot"
        )
    if value.split(".", 1)[0].upper() in _RESERVED_DEVICE_NAMES:
        raise RuntimeContractError(f"{label} must not be a Windows reserved device name")
    return value


def safe_identifier(value: str, label: str) -> str:
    """Validate one cross-platform stable-identity segment.

    This public wrapper lets producer tools validate logical prop names with
    exactly the same path and Windows-device rules as stable entries.
    """
    return _safe_identifier(value, label)


def _reject_extra_keys(data: dict[str, Any], allowed: set[str], label: str) -> None:
    extra = set(data.keys()) - allowed
    if extra:
        listed = ", ".join(sorted(extra))
        raise RuntimeContractError(f"{label} must only hold type and path; unexpected fields: {listed}")


def _check_res_path(value: str, label: str) -> str:
    if not value.startswith(_RES_PREFIX):
        raise RuntimeContractError(f"{label} must be a res:// path")
    remainder = value[len(_RES_PREFIX):]
    if not remainder.strip():
        raise RuntimeContractError(f"{label} must name a resource under res://")
    if "\\" in remainder:
        raise RuntimeContractError(f"{label} must use forward slashes")
    # Must be a clean, project-relative resource path: no absolute/UNC anchor,
    # no drive letter, no empty (``//``), ``.`` or ``..`` segments.
    segments = remainder.split("/")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise RuntimeContractError(
                f"{label} must be a relative resource path with no empty, '.' or '..' segments"
            )
        if ":" in segment:
            raise RuntimeContractError(f"{label} must not contain a drive letter or scheme")
    return value


def _resolve_res_path(project_root: Path, res_path: str) -> Path:
    return project_root / res_path[len(_RES_PREFIX):]


def _assert_within_root(project_root: Path, resolved: Path, label: str) -> None:
    root = project_root.resolve()
    if not resolved.resolve().is_relative_to(root):
        raise RuntimeContractError(f"{label} resolves outside the project root")


def stable_output_dir(production_family: str, asset_id: str) -> str:
    """Return the canonical project-relative output directory for one asset.

    The directory is derived only from stable identity, so it is deterministic
    and unique per ``(production_family, asset_id)``. Every source image, native
    Godot artifact, and support file for the asset must live under it.
    """
    if production_family not in PRODUCTION_FAMILIES:
        raise RuntimeContractError(f"production_family is not allowed: {production_family}")
    _safe_identifier(asset_id, "asset_id")
    return f"{GENERATED_ROOT}/{production_family}/{asset_id}"


def _output_owner(
    production_family: str, asset_id: str, bundle_id: Any | None
) -> str:
    """Return the stable physical-output owner for an entry.

    One Skill invocation may deliver many independently usable runtime
    resources out of one physical production: a compact prop pack cuts several
    AtlasTextures from one atlas, and a UI or card kit compiles a Theme plus its
    StyleBoxTextures and icon AtlasTextures into one kit directory. Each of
    those outputs is separately worker-consumable, so each gets its own stable
    entry with a distinct ``asset_id``, while their files stay in the shared
    bundle directory. Families outside ``BUNDLE_FAMILIES`` deliver one runtime
    output per asset and cannot opt into this.
    """
    if bundle_id is None:
        return asset_id
    if production_family not in BUNDLE_FAMILIES:
        raise RuntimeContractError(
            "bundle_id is only supported for "
            f"{', '.join(sorted(BUNDLE_FAMILIES))} stable entries"
        )
    if not isinstance(bundle_id, str) or not bundle_id.strip():
        raise RuntimeContractError("bundle_id must be a non-empty string")
    bundle_id = safe_identifier(bundle_id, "bundle_id")
    prefix = f"{bundle_id}--"
    if not asset_id.startswith(prefix) or asset_id == prefix:
        raise RuntimeContractError(
            f"{production_family} asset_id must be '<bundle_id>--<logical_output_id>'"
        )
    safe_identifier(asset_id[len(prefix):], f"{production_family} logical_output_id")
    return bundle_id


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
        raise RuntimeContractError(
            f"{label} must not depend on the generation work/ workspace"
        )
    stable_dir = stable_output_dir(production_family, asset_id)
    # A clean res path never ends in ``/`` (``_check_res_path`` rejects an empty
    # last segment), so an exact-prefix match with the trailing slash guarantees
    # a real file strictly under the directory, not the directory itself.
    if not remainder.startswith(stable_dir + "/"):
        raise RuntimeContractError(f"{label} must be a file under res://{stable_dir}/")
    return value


def check_support_files(
    paths: Any,
    *,
    production_family: str,
    asset_id: str,
) -> list[str]:
    """Validate that every required support file is under the stable directory."""
    if not isinstance(paths, (list, tuple)):
        raise RuntimeContractError("support files must be a list of res:// paths")
    validated: list[str] = []
    for index, path in enumerate(paths):
        if not isinstance(path, str) or not path.strip():
            raise RuntimeContractError(f"support_files[{index}] must be a non-empty string")
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
        raise RuntimeContractError(
            f"{label} stable directory resolves outside the project root"
        )
    resolved = Path(target)
    if not resolved.is_absolute():
        resolved = root / resolved
    resolved = resolved.resolve()
    if resolved == stable or not resolved.is_relative_to(stable):
        raise RuntimeContractError(f"{label} must be written under {relative_dir}/")
    return resolved


def _validate_source_layout(
    data: dict[str, Any],
    *,
    production_family: str,
    asset_id: str,
    output_owner: str,
) -> tuple[str, str]:
    layout = data.get("source_layout")
    if not isinstance(layout, dict):
        raise RuntimeContractError("source_layout must be an object")
    _reject_legacy(layout)
    _reject_extra_keys(layout, SOURCE_LAYOUT_KEYS, "source_layout")
    layout_type = _non_empty_string(layout, "type", "source_layout.type")
    if layout_type not in SOURCE_LAYOUT_TYPES:
        raise RuntimeContractError(f"source_layout.type is not allowed: {layout_type}")
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
            asset_id=output_owner,
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
    output_owner: str,
) -> tuple[str, str] | None:
    artifact = data.get("godot_artifact")
    is_reference = layout_type in REFERENCE_LAYOUTS

    if artifact is None:
        if is_reference:
            return None
        if processing_status in ARTIFACT_REQUIRED_STATUSES:
            raise RuntimeContractError(
                f"godot_artifact is required when processing_status is {processing_status}"
            )
        return None

    if is_reference:
        raise RuntimeContractError(
            "godot_artifact must be absent for a reference source_layout"
        )
    if not isinstance(artifact, dict):
        raise RuntimeContractError("godot_artifact must be an object or null")
    _reject_legacy(artifact)
    _reject_extra_keys(artifact, GODOT_ARTIFACT_KEYS, "godot_artifact")

    artifact_type = _non_empty_string(artifact, "type", "godot_artifact.type")
    if not GODOT_TYPE_PATTERN.match(artifact_type):
        raise RuntimeContractError(
            "godot_artifact.type must be a Godot ClassDB type identifier"
        )
    allowed_types = LAYOUT_ARTIFACT_TYPES[layout_type]
    if artifact_type not in allowed_types:
        raise RuntimeContractError(
            f"godot_artifact.type for a {layout_type} source_layout must be "
            f"one of: {', '.join(allowed_types)}; not {artifact_type}"
        )
    artifact_path = _non_empty_string(artifact, "path", "godot_artifact.path")
    check_output_path(
        artifact_path,
        production_family=production_family,
        asset_id=output_owner,
        label="godot_artifact.path",
    )
    return artifact_type, artifact_path


def validate_entry(
    data: Any,
    *,
    project_root: Path | None = None,
    check_files: bool = False,
) -> dict[str, Any]:
    """Validate one runtime record object and return it unchanged."""
    if not isinstance(data, dict):
        raise RuntimeContractError("Stable entry must be a JSON object")

    _reject_legacy(data)

    if not is_schema_version(data.get("version")):
        raise RuntimeContractError(f"Stable entry version must be integer {SCHEMA_VERSION}")

    asset_id = _non_empty_string(data, "asset_id", "asset_id")
    _safe_identifier(asset_id, "asset_id")
    _safe_identifier(_non_empty_string(data, "tag", "tag"), "tag")

    family = _non_empty_string(data, "production_family", "production_family")
    if family not in PRODUCTION_FAMILIES:
        raise RuntimeContractError(f"production_family is not allowed: {family}")

    output_owner = _output_owner(family, asset_id, data.get("bundle_id"))

    processing_status = _non_empty_string(
        data, "processing_status", "processing_status"
    )
    if processing_status not in PROCESSING_STATUSES:
        raise RuntimeContractError(
            f"processing_status is not allowed: {processing_status}"
        )

    layout_type, layout_path = _validate_source_layout(
        data,
        production_family=family,
        asset_id=asset_id,
        output_owner=output_owner,
    )
    # Bind reference layout and reference family so neither can be used to
    # bypass the other's contract.
    if layout_type in REFERENCE_LAYOUTS and family not in REFERENCE_FAMILIES:
        raise RuntimeContractError(
            "a reference source_layout is only allowed for a reference family "
            f"({', '.join(sorted(REFERENCE_FAMILIES))})"
        )
    if family in REFERENCE_FAMILIES and layout_type not in REFERENCE_LAYOUTS:
        raise RuntimeContractError(
            f"production_family {family} must use a reference source_layout"
        )
    if (
        layout_type in REFERENCE_LAYOUTS
        and processing_status not in REFERENCE_PROCESSING_STATUSES
    ):
        allowed = ", ".join(sorted(REFERENCE_PROCESSING_STATUSES))
        raise RuntimeContractError(
            "processing_status for a reference source_layout must be one of: "
            f"{allowed}; not {processing_status}"
        )
    artifact = _validate_godot_artifact(
        data,
        layout_type=layout_type,
        processing_status=processing_status,
        production_family=family,
        asset_id=asset_id,
        output_owner=output_owner,
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
            raise RuntimeContractError(f"source_layout.path not found: {layout_path}")
        if artifact is not None:
            _, artifact_path = artifact
            artifact_file = _resolve_res_path(root, artifact_path)
            _assert_within_root(root, artifact_file, "godot_artifact.path")
            if check_files and not artifact_file.exists():
                raise RuntimeContractError(
                    f"godot_artifact.path not found: {artifact_path}"
                )
    elif check_files:
        raise RuntimeContractError("project_root is required to check files")

    return data


