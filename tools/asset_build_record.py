#!/usr/bin/env python3
"""Bind a promotion to the build its validation examined.

Stable output paths are derived from ``asset_id``, so regenerating an asset
overwrites the very paths an older result names. Comparing paths therefore
proves nothing about *which* build sits there, and a result that passed L0-L4
for one build could promote a later, never-validated build to ``ready``.

A build record is the content fingerprint a ``compiled`` draft leaves in the
asset's support metadata. The promotion run recomputes it from disk and requires
an exact match, so the artifact it registers is the same bytes L0-L4 examined.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

BUILD_RECORD_VERSION = 1

RES_PREFIX = "res://"


class BuildRecordError(Exception):
    """Raised when a build fingerprint cannot be computed or read."""


def digest(path: Path | str, label: str) -> str:
    """Return the sha256 of one build input or output."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError as exc:
        raise BuildRecordError(f"{label} is missing or unreadable: {path}") from exc


def resolve_res(project_root: Path | str, res_path: str) -> Path:
    """Resolve a ``res://`` path against the project root."""
    return Path(project_root) / res_path[len(RES_PREFIX):]


def support_metadata_path(
    project_root: Path | str, production_family: str, asset_id: str
) -> Path:
    """Return the fixed support-metadata path beside an asset's artifact."""
    return (
        Path(project_root)
        / "assets"
        / "generated"
        / production_family
        / asset_id
        / f"{asset_id}.json"
    )


def read_recorded_build(
    project_root: Path | str, production_family: str, asset_id: str
) -> dict[str, Any]:
    """Load the build fingerprint written by this asset's ``compiled`` run."""
    path = support_metadata_path(project_root, production_family, asset_id)
    if not path.is_file():
        raise BuildRecordError(
            "no compiled build to promote: run this builder without --result first, "
            f"then validate it (missing {path})"
        )
    try:
        support = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildRecordError(f"support metadata is not valid JSON: {path}") from exc
    recorded = support.get("build") if isinstance(support, dict) else None
    if not isinstance(recorded, dict) or recorded.get("version") != BUILD_RECORD_VERSION:
        raise BuildRecordError(
            "support metadata carries no v1 build fingerprint; rebuild the compiled "
            "entry and revalidate it before promoting"
        )
    return recorded


def assert_same_build(
    recorded: dict[str, Any], recomputed: dict[str, Any], *, inputs: str
) -> None:
    """Fail closed when the on-disk build differs from the validated one.

    ``inputs`` names the fingerprinted parts for the caller's family, so the
    diagnostic points at what to rebuild rather than at the comparison.
    """
    if recorded != recomputed:
        raise BuildRecordError(
            f"{inputs} changed since the compiled build that was validated; "
            "rebuild the compiled entry and rerun L0-L4 before promoting"
        )
