#!/usr/bin/env python3
"""Bind a promotion to the build its validation examined.

Stable output paths are derived from ``asset_id``, so regenerating an asset
overwrites the very paths an older result names. Comparing paths therefore
proves nothing about *which* build sits there, and a result that passed L0-L4
for one build could promote a later, never-validated build to ``ready``.

A build record is the content fingerprint a ``compiled`` draft leaves in the
asset's support metadata. The promotion run recomputes it from disk and requires
an exact match.

What that does and does not prove
---------------------------------

It proves the inputs and artifact on disk are byte-identical to the ones the
last ``compiled`` run recorded, so a promotion cannot register an artifact that
was edited, replaced, or partially regenerated behind the builder's back.

It does **not** prove the build was the one L0-L4 examined. A Skill result
carries no build identity, and the record is written by the same builder that
compiles — so regenerating an asset and re-running the ``compiled`` builder
refreshes the record, after which a stale result promotes a never-validated
build. Closing that needs a build id in the record that the Skill result echoes
back; until the result contract carries one, treat this as drift detection
between compile and promote, not as proof of validation.

The validation record
---------------------

A *validation* record closes exactly that remaining gap for a family whose
Skill validates the artifact it will register. It is written by the family's
standalone validation runner, only after a fully passing ladder, and it
fingerprints the artifact the ladder actually examined. Registration recomputes
that fingerprint from disk and requires an exact match, so an asset regenerated
after validation cannot be registered against the older passing result: the
bytes on disk no longer hash to the ones L0-L4 saw.

The result contract still carries no build identity, so this does not tie a
*particular* result document to those bytes. It does prove the stronger thing a
worker depends on — the bytes being registered passed L0-L4 in this project.
Like every record here it is an ordinary project file, so it detects drift and
mistakes, not a producer determined to forge one.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

BUILD_RECORD_VERSION = 1
VALIDATION_RECORD_VERSION = 1

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


def validation_record_path(project_root: Path | str, asset_id: str) -> Path:
    """Return the fixed validation-record path for one asset.

    It sits with the family's other provenance under generation scratch, never
    beside the artifact: a ``single -> Texture2D`` asset has no support file,
    and nothing registered may point into ``.godotmaker/``.
    """
    return (
        Path(project_root)
        / ".godotmaker"
        / "asset-generation"
        / "reports"
        / f"{asset_id}_validation.json"
    )


def write_validation_record(
    project_root: Path | str,
    *,
    production_family: str,
    asset_id: str,
    artifact_path: str,
) -> dict[str, Any]:
    """Record the artifact bytes one fully passing L0-L4 run examined."""
    record = {
        "version": VALIDATION_RECORD_VERSION,
        "production_family": production_family,
        "asset_id": asset_id,
        "artifact": {
            "path": artifact_path,
            "sha256": digest(
                resolve_res(project_root, artifact_path), "validated artifact"
            ),
        },
    }
    path = validation_record_path(project_root, asset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def read_validation_record(
    project_root: Path | str, *, production_family: str, asset_id: str
) -> dict[str, Any]:
    """Load the record this asset's last passing validation run wrote."""
    path = validation_record_path(project_root, asset_id)
    if not path.is_file():
        raise BuildRecordError(
            "no validation record to register against: run this family's "
            "standalone validation on the asset and keep its record "
            f"(missing {path})"
        )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BuildRecordError(f"validation record is not valid JSON: {path}") from exc
    if (
        not isinstance(record, dict)
        or record.get("version") != VALIDATION_RECORD_VERSION
        or record.get("production_family") != production_family
        or record.get("asset_id") != asset_id
    ):
        raise BuildRecordError(
            f"{path} is not a v1 {production_family} validation record for "
            f"{asset_id}; rerun standalone validation before registering"
        )
    return record


def assert_validated_artifact(
    record: dict[str, Any], *, project_root: Path | str, artifact_path: str
) -> None:
    """Fail closed unless the artifact on disk is the one that passed L0-L4."""
    artifact = record.get("artifact")
    if not isinstance(artifact, dict) or artifact.get("path") != artifact_path:
        raise BuildRecordError(
            f"the validation record describes another artifact than {artifact_path}; "
            "rerun standalone validation before registering"
        )
    if digest(resolve_res(project_root, artifact_path), "validated artifact") != artifact.get(
        "sha256"
    ):
        raise BuildRecordError(
            f"{artifact_path} changed since it passed L0-L4; a regeneration "
            "overwrites the same stable path, so rerun standalone validation "
            "and register the build it examined"
        )


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
